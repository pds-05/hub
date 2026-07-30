from sqlalchemy import inspect, text

from app.db.session import Base, engine
from app.models.alert_event import AlertEvent
from app.models.alert_event_activity import AlertEventActivity
from app.models.alert_rule import AlertRule
from app.models.cluster_agent import ClusterAgentHeartbeat, ClusterAgentReport
from app.models.grafana_platform_credential import GrafanaPlatformCredential
from app.models.grafana_target_dashboard import GrafanaTargetDashboard
from app.models.grafana_user_context import GrafanaUserContext
from app.models.managed_cluster import ManagedCluster
from app.models.monitor_target import MonitorTarget
from app.models.notification_channel import NotificationChannel
from app.models.notification_record import NotificationRecord
from app.models.target_check_result import TargetCheckResult
from app.models.user import User


def init_db() -> None:
    # Import models before create_all so SQLAlchemy knows their tables.
    _ = (
        AlertEvent,
        AlertEventActivity,
        AlertRule,
        ClusterAgentHeartbeat,
        ClusterAgentReport,
        GrafanaPlatformCredential,
        GrafanaTargetDashboard,
        GrafanaUserContext,
        ManagedCluster,
        MonitorTarget,
        NotificationChannel,
        NotificationRecord,
        TargetCheckResult,
        User,
    )
    Base.metadata.create_all(bind=engine)
    migrate_monitor_targets_user_id()
    migrate_monitor_targets_expected_keyword()
    migrate_monitor_targets_exporter_kind()
    migrate_target_check_results_details()
    migrate_alert_events_handling_status()
    migrate_alert_rules_deleted_at()
    migrate_soft_delete_columns()
    migrate_users_role()


def migrate_monitor_targets_user_id() -> None:
    inspector = inspect(engine)
    if "monitor_targets" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("monitor_targets")}
    if "user_id" in columns:
        return

    with engine.begin() as conn:
        first_user_id = conn.execute(text("select id from users order by id limit 1")).scalar()
        if first_user_id is None:
            return
        conn.execute(text("alter table monitor_targets add column user_id integer"))
        conn.execute(text("update monitor_targets set user_id = :user_id where user_id is null"), {"user_id": first_user_id})
        conn.execute(text("alter table monitor_targets alter column user_id set not null"))
        conn.execute(text("create index if not exists ix_monitor_targets_user_id on monitor_targets (user_id)"))


def migrate_monitor_targets_expected_keyword() -> None:
    inspector = inspect(engine)
    if "monitor_targets" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("monitor_targets")}
    if "expected_keyword" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("alter table monitor_targets add column expected_keyword varchar(200)"))


def migrate_monitor_targets_exporter_kind() -> None:
    inspector = inspect(engine)
    if "monitor_targets" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("monitor_targets")}
    if "exporter_kind" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("alter table monitor_targets add column exporter_kind varchar(50)"))
        conn.execute(text("update monitor_targets set exporter_kind = 'node' where target_type = 'exporter' and exporter_kind is null"))


def migrate_target_check_results_details() -> None:
    inspector = inspect(engine)
    if "target_check_results" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("target_check_results")}
    if "details" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("alter table target_check_results add column details json"))


def migrate_alert_events_handling_status() -> None:
    inspector = inspect(engine)
    if "alert_events" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("alert_events")}
    if "handling_status" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("alter table alert_events add column handling_status varchar(30) not null default 'new'"))
        conn.execute(text("update alert_events set handling_status = 'resolved' where status = 'resolved'"))
        conn.execute(text("update alert_events set handling_status = 'acknowledged' where status = 'active' and acknowledged = true"))
        conn.execute(text("create index if not exists ix_alert_events_handling_status on alert_events (handling_status)"))


def migrate_alert_rules_deleted_at() -> None:
    inspector = inspect(engine)
    if "alert_rules" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("alert_rules")}
    if "deleted_at" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("alter table alert_rules add column deleted_at timestamp with time zone"))
        conn.execute(text("create index if not exists ix_alert_rules_deleted_at on alert_rules (deleted_at)"))


def migrate_soft_delete_columns() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    for table_name in ("monitor_targets", "notification_channels", "alert_events"):
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "deleted_at" in columns:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"alter table {table_name} add column deleted_at timestamp with time zone"))
            conn.execute(text(f"create index if not exists ix_{table_name}_deleted_at on {table_name} (deleted_at)"))


def migrate_users_role() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "role" not in columns:
            conn.execute(text("alter table users add column role varchar(20) not null default 'user'"))
        conn.execute(text("update users set role = 'root' where username = 'admin'"))
        conn.execute(text("update users set role = 'user' where role is null or role = ''"))
