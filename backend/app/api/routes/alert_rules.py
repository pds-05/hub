from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.alert_rule import AlertRule
from app.models.user import User
from app.schemas.alert_rule import AlertEvaluationRead, AlertRuleCreate, AlertRuleRead, AlertRuleUpdate
from app.schemas.common import MessageResponse
from app.services.prometheus_client import PrometheusClient, PrometheusUnavailableError, get_prometheus_client

router = APIRouter(prefix="/alert-rules", tags=["alert rules"])


def get_owned_rule(rule_id: int, db: Session, current_user: User) -> AlertRule:
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id, AlertRule.user_id == current_user.id, AlertRule.deleted_at.is_(None)).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


def compare_value(value: float, operator: str, threshold: float) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold
    if operator == "<=":
        return value <= threshold
    if operator == "<":
        return value < threshold
    if operator == "==":
        return value == threshold
    return False


@router.post("", response_model=AlertRuleRead)
def create_alert_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRule:
    rule = AlertRule(**payload.model_dump(), user_id=current_user.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[AlertRuleRead])
def list_alert_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertRule]:
    return list(db.query(AlertRule).filter(AlertRule.user_id == current_user.id, AlertRule.deleted_at.is_(None)).order_by(AlertRule.id.desc()).all())


@router.get("/{rule_id}", response_model=AlertRuleRead)
def get_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRule:
    return get_owned_rule(rule_id, db, current_user)


@router.put("/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRule:
    rule = get_owned_rule(rule_id, db, current_user)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", response_model=MessageResponse)
def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    rule = get_owned_rule(rule_id, db, current_user)
    rule.enabled = False
    rule.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return MessageResponse(message="Alert rule deleted")


@router.get("/evaluate/nodes", response_model=list[AlertEvaluationRead])
async def evaluate_node_alert_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    prometheus: PrometheusClient = Depends(get_prometheus_client),
) -> list[AlertEvaluationRead]:
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.user_id == current_user.id, AlertRule.deleted_at.is_(None), AlertRule.enabled.is_(True), AlertRule.scope == "node")
        .all()
    )
    try:
        nodes = await prometheus.all_node_metrics()
    except PrometheusUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    alerts: list[AlertEvaluationRead] = []
    for node in nodes:
        instance = node["instance"]
        metrics = node.get("metrics", {})
        for rule in rules:
            value = metrics.get(rule.metric)
            if not isinstance(value, (int, float)):
                continue
            if not compare_value(float(value), rule.operator, rule.threshold):
                continue
            alerts.append(
                AlertEvaluationRead(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    instance=instance,
                    level=rule.level,
                    metric=rule.metric,
                    operator=rule.operator,
                    value=float(value),
                    threshold=rule.threshold,
                    message=f"{instance} {rule.metric} {value} {rule.operator} {rule.threshold}",
                )
            )
    return alerts

