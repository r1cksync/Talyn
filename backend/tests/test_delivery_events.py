import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import worker
from app.db import SessionLocal
from app.models import DeliveryEvent, EmailDelivery
from conftest import manager_login


def test_ses_validation_and_out_of_order_delivery_keep_suppression(client, monkeypatch):
    org = manager_login(client)
    with SessionLocal.begin() as db:
        delivery = EmailDelivery(
            org_id=org["id"],
            recipient="bounce@simulator.amazonses.com",
            kind="invitation",
            dedupe_key="synthetic-ses-test",
            payload_ciphertext="unused",
            provider_id="synthetic-provider-id",
        )
        db.add(delivery)
        db.flush()
        identifier = delivery.id
    validation = {"Message": "Successfully validated SNS topic for Amazon SES event publishing."}
    bounce = {"Message": json.dumps({"eventType": "Bounce", "mail": {"messageId": "synthetic-provider-id"}})}
    delivered = {"eventType": "Delivery", "mail": {"messageId": "synthetic-provider-id"}}
    messages = [
        {"MessageId": name, "ReceiptHandle": str(index), "Body": json.dumps(payload)}
        for index, (name, payload) in enumerate(
            [("validation", validation), ("bounce", bounce), ("delivered", delivered), ("bounce", bounce)]
        )
    ]
    acknowledged = []
    queue = SimpleNamespace(
        receive_message=lambda **kwargs: {"Messages": messages},
        delete_message=lambda **kwargs: acknowledged.append(kwargs["ReceiptHandle"]),
    )
    monkeypatch.setattr(worker, "aws", lambda service: queue)
    monkeypatch.setattr(worker, "settings", lambda: SimpleNamespace(event_queue_url="synthetic-queue"))
    worker.receive_delivery_events()
    assert acknowledged == ["0", "1", "2", "3"]
    with SessionLocal() as db:
        assert db.get(EmailDelivery, identifier).status == "bounced"
        events = db.scalars(select(DeliveryEvent).where(DeliveryEvent.delivery_id == identifier)).all()
        assert {event.kind for event in events} == {"bounce", "delivery"}
        assert len(events) == 2


def test_unidentified_ses_event_is_not_acknowledged(monkeypatch):
    acknowledged = []
    queue = SimpleNamespace(
        receive_message=lambda **kwargs: {"Messages": [{"Body": '{"eventType":"Delivery"}'}]},
        delete_message=lambda **kwargs: acknowledged.append(kwargs),
    )
    monkeypatch.setattr(worker, "aws", lambda service: queue)
    monkeypatch.setattr(worker, "settings", lambda: SimpleNamespace(event_queue_url="synthetic-queue"))
    with pytest.raises(ValueError, match="provider message ID"):
        worker.receive_delivery_events()
    assert not acknowledged
