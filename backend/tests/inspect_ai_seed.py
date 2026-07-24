import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.monitor_target import MonitorTarget
from app.models.user import User


db = SessionLocal()
try:
    for user in db.query(User).order_by(User.id).all():
        events = db.query(AlertEvent).filter(AlertEvent.user_id == user.id).count()
        ai_events = db.query(AlertEvent).filter(AlertEvent.user_id == user.id, AlertEvent.rule_name.like("AI测试-%")).count()
        targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == user.id).count()
        ai_targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == user.id, MonitorTarget.name.like("AI测试-%")).count()
        print(f"user={user.id}:{user.username} events={events} ai_events={ai_events} targets={targets} ai_targets={ai_targets}")
finally:
    db.close()
