import json
from datetime import timedelta

from sqlalchemy import select

from .models import AsyncJob, AuditLog, EmailDelivery, Usage, now
from .security import encrypt


def enqueue(db, org_id, kind, target_id, key):
    existing = db.scalar(select(AsyncJob).where(AsyncJob.dedupe_key == key))
    if existing:
        return existing
    job = AsyncJob(org_id=org_id, kind=kind, target_id=target_id, dedupe_key=key)
    db.add(job)
    db.flush()
    return job


def queue_email(db, org_id, recipient, kind, key, subject, body):
    existing = db.scalar(select(EmailDelivery).where(EmailDelivery.dedupe_key == key))
    if existing:
        return existing
    delivery = EmailDelivery(
        org_id=org_id,
        recipient=recipient,
        kind=kind,
        dedupe_key=key,
        payload_ciphertext=encrypt(json.dumps({"subject": subject, "body": body})),
        delete_after=now() + timedelta(days=30),
    )
    db.add(delivery)
    db.flush()
    enqueue(db, org_id, "email", delivery.id, "email:" + key)
    return delivery


def meter(db, org_id, application_id, name, amount, key):
    if not db.scalar(select(Usage.id).where(Usage.dedupe_key == key)):
        db.add(Usage(org_id=org_id, application_id=application_id, meter=name, quantity=amount, dedupe_key=key))


def audit(db, org_id, actor, action, target_id, details=None):
    db.add(
        AuditLog(
            org_id=org_id,
            actor=actor,
            action=action,
            target_id=target_id,
            details=details or {},
            delete_after=now() + timedelta(days=90),
        )
    )
