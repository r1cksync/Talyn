"""Transactional outbox dispatcher + durable worker. SQS messages carry IDs, never PII."""

import hashlib
import json
import logging
import shutil
import subprocess
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from .adapters import aws, deliver_email, storage
from .checkpoints import checkpoint_store
from .config import settings
from .db import SessionLocal
from .document_extract import isolated_extract
from .models import (
    Application,
    AsyncJob,
    AuditLog,
    AuthSession,
    Candidate,
    DeliveryEvent,
    Document,
    EmailDelivery,
    EmailChallenge,
    Extraction,
    InterviewSession,
    Invitation,
    RateBucket,
    RecordingObject,
    Usage,
    VideoObservation,
    now,
)
from .outbox import audit, enqueue, meter, queue_email
from .security import aware, decrypt, owned
from .services import evaluate_application, finish_session, prepare_application

logger = logging.getLogger("talyn.worker")


def extract_document(org_id, document_id):
    with SessionLocal() as db:
        document = owned(db, Document, document_id, org_id)
        if document.status == "ready":
            return
        key, size, sha, kind, app_id = (
            document.object_key,
            document.size,
            document.sha256,
            document.content_type,
            document.application_id,
        )
    try:
        data = storage.verify(key, size, sha, settings().max_document_bytes)
        result = isolated_extract(data, kind)
        pages = result.pop("page_count")
        if len(result["text"].strip()) < 30:
            if kind != "application/pdf" or settings().mode != "aws":
                raise ValueError("No usable text. Supply a text PDF or DOCX; scanned PDFs need AWS Textract.")
            if pages > settings().max_textract_pages:
                raise ValueError("Scanned PDF exceeds bounded Textract page limit")
            textract = aws("textract")
            job_id = textract.start_document_text_detection(
                DocumentLocation={"S3Object": {"Bucket": settings().bucket, "Name": key}},
                ClientRequestToken=hashlib.sha256((key + sha).encode()).hexdigest(),
            )["JobId"]
            response = None
            for _ in range(12):
                response = textract.get_document_text_detection(JobId=job_id)
                if response["JobStatus"] != "IN_PROGRESS":
                    break
                time.sleep(5)
            if response["JobStatus"] != "SUCCEEDED":
                raise ValueError("Textract is still processing or failed; retry this bounded job")
            blocks = response["Blocks"]
            while response.get("NextToken"):
                response = textract.get_document_text_detection(JobId=job_id, NextToken=response["NextToken"])
                blocks.extend(response["Blocks"])
            sources = [
                {"ref": f"page:{b.get('Page', 1)}:line:{i}", "text": b["Text"]}
                for i, b in enumerate(blocks)
                if b["BlockType"] == "LINE"
            ]
            result = {
                "text": "\n".join(s["text"] for s in sources),
                "sources": sources,
                "warnings": ["Extracted with OCR; review for recognition errors."],
            }
            if len(result["text"].strip()) < 30 or len(result["text"]) > 150000:
                raise ValueError("OCR extraction is empty or exceeds limits")
            with SessionLocal.begin() as db:
                meter(db, org_id, app_id, "textract_pages", pages, "textract:" + document_id)
        with SessionLocal.begin() as db:
            doc = owned(db, Document, document_id, org_id)
            if not db.scalar(
                select(Extraction.id).where(Extraction.document_id == doc.id, Extraction.org_id == org_id)
            ):
                db.add(Extraction(org_id=org_id, document_id=doc.id, **result))
            doc.status, doc.error = "ready", ""
            meter(db, org_id, app_id, "storage_bytes", size, "document-storage:" + doc.id)
    except Exception:
        with SessionLocal.begin() as db:
            doc = owned(db, Document, document_id, org_id)
            doc.status, doc.error = "error", "Extraction failed: check file type, size, encryption, and readable text."
        raise


def verify_recording(org_id, recording_id):
    with SessionLocal() as db:
        obj = owned(db, RecordingObject, recording_id, org_id)
        if obj.verified:
            return
        data = storage.verify(obj.object_key, obj.size, obj.sha256, settings().max_recording_bytes)
        if obj.content_type == "video/webm" and not data.startswith(b"\x1a\x45\xdf\xa3"):
            raise ValueError("Missing WebM header: each clip must be independently playable")
        if obj.content_type == "video/mp4" and data[4:8] != b"ftyp":
            raise ValueError("Missing MP4 header")
        binary = shutil.which("ffmpeg")
        if not binary:
            import imageio_ffmpeg

            binary = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [binary, "-v", "error", "-xerror", "-i", "pipe:0", "-t", "36", "-map", "0:v:0", "-f", "null", "-"],
            input=data,
            capture_output=True,
            timeout=45,
        )
        if result.returncode:
            raise ValueError("Recording is not independently decodable")
        session = owned(db, InterviewSession, obj.session_id, org_id)
        app_id, size = session.application_id, obj.size
    with SessionLocal.begin() as db:
        obj = owned(db, RecordingObject, recording_id, org_id)
        obj.verified = True
        meter(db, org_id, app_id, "storage_bytes", size, "recording-storage:" + obj.id)


def observe_frame(org_id, session_id, dedupe_key):
    offset = int(dedupe_key.rsplit(":", 1)[1])
    with SessionLocal() as db:
        session = owned(db, InterviewSession, session_id, org_id)
        app = owned(db, Application, session.application_id, org_id)
        if app.revoked:
            return
        key = f"{org_id}/{session.application_id}/frames/{offset}.jpg"
    if settings().mode == "demo":
        faces = [{"Confidence": 99, "Pose": {"Yaw": 0, "Pitch": 0}}]
    else:
        # DEFAULT excludes emotion, gender, age, etc. No indexing or face identity APIs are used.
        faces = aws("rekognition").detect_faces(
            Image={"S3Object": {"Bucket": settings().bucket, "Name": key}}, Attributes=["DEFAULT"]
        )["FaceDetails"]
    kinds = []
    if not faces:
        kinds.append(("no_face_detected", 0.0))  # No face is a detector result, not a calibrated probability.
    elif len(faces) > 1:
        kinds.append(("multiple_faces_detected", min(f["Confidence"] for f in faces)))
    elif abs(faces[0].get("Pose", {}).get("Yaw", 0)) > 35 or abs(faces[0].get("Pose", {}).get("Pitch", 0)) > 30:
        kinds.append(("head_orientation_away", faces[0]["Confidence"]))
    with SessionLocal.begin() as db:
        for kind, confidence in kinds:
            prior = db.scalar(
                select(VideoObservation)
                .where(
                    VideoObservation.session_id == session_id,
                    VideoObservation.org_id == org_id,
                    VideoObservation.kind == kind,
                )
                .order_by(VideoObservation.end_ms.desc())
            )
            if prior and offset <= prior.end_ms:
                continue
            if prior and offset - prior.end_ms <= settings().frame_interval_seconds * 1500:
                prior.end_ms = offset
                prior.sample_count += 1
                prior.visible = (
                    prior.sample_count >= 2
                    and prior.end_ms - prior.start_ms >= settings().frame_interval_seconds * 1000
                )
                prior.confidence = min(prior.confidence, confidence)
            else:
                db.add(
                    VideoObservation(
                        org_id=org_id,
                        session_id=session_id,
                        kind=kind,
                        start_ms=offset,
                        end_ms=offset,
                        confidence=confidence,
                        evidence_key=key,
                    )
                )


def send_delivery(org_id, delivery_id):
    with SessionLocal.begin() as db:
        delivery = owned(db, EmailDelivery, delivery_id, org_id, lock=True)
        if delivery.status in {"sent", "simulated", "bounced", "complained", "delivered", "suppressed"}:
            return
        suppressed = db.scalar(
            select(EmailDelivery.id).where(
                EmailDelivery.org_id == org_id,
                EmailDelivery.recipient == delivery.recipient,
                EmailDelivery.status.in_(["bounced", "complained"]),
            )
        )
        if suppressed:
            delivery.status = "suppressed"
            return
        delivery.status, delivery.attempts = "sending", delivery.attempts + 1
        recipient = delivery.recipient
        payload = json.loads(decrypt(delivery.payload_ciphertext))
    provider_id = deliver_email(recipient, payload["subject"], payload["body"])
    # A process failure after SES acceptance and before this transaction can cause a duplicate on retry.
    with SessionLocal.begin() as db:
        delivery = owned(db, EmailDelivery, delivery_id, org_id)
        delivery.status = "simulated" if settings().mode == "demo" else "sent"
        delivery.provider_id, delivery.error = provider_id, ""
        meter(db, org_id, None, "emails", 1, "email-usage:" + delivery.id)


def delete_application(org_id, app_id):
    with SessionLocal() as db:
        app = db.scalar(select(Application).where(Application.id == app_id, Application.org_id == org_id))
        if not app:
            return
        if not app.revoked:
            raise ValueError("Deletion requires revocation first")
        candidate_id = app.candidate_id
        docs = list(db.scalars(select(Document.id).where(Document.application_id == app.id, Document.org_id == org_id)))
        sessions = list(
            db.scalars(
                select(InterviewSession.id).where(
                    InterviewSession.application_id == app.id, InterviewSession.org_id == org_id
                )
            )
        )
        invites = list(
            db.scalars(select(Invitation.id).where(Invitation.application_id == app.id, Invitation.org_id == org_id))
        )
        challenges = list(
            db.scalars(
                select(EmailChallenge.id).where(
                    EmailChallenge.org_id == org_id, EmailChallenge.invitation_id.in_(invites)
                )
            )
        )
    storage.delete_prefix(f"{org_id}/{app_id}/")
    with checkpoint_store() as saver:
        threads = set()
        for checkpoint in saver.list(None):
            identifier = checkpoint.config["configurable"]["thread_id"]
            if identifier.startswith(f"{org_id}:{app_id}:"):
                threads.add(identifier)
        for identifier in threads:
            saver.delete_thread(identifier)
    with SessionLocal.begin() as db:
        db.execute(delete(AuthSession).where(AuthSession.application_id == app_id, AuthSession.org_id == org_id))
        deliveries = db.scalars(select(EmailDelivery).where(EmailDelivery.org_id == org_id)).all()
        for delivery in deliveries:
            if app_id in delivery.dedupe_key or any(i in delivery.dedupe_key for i in invites + challenges):
                db.execute(delete(AsyncJob).where(AsyncJob.org_id == org_id, AsyncJob.target_id == delivery.id))
                db.delete(delivery)
        db.execute(delete(Usage).where(Usage.application_id == app_id, Usage.org_id == org_id))
        db.execute(
            delete(AsyncJob).where(
                AsyncJob.org_id == org_id, AsyncJob.target_id.in_([app_id] + docs + sessions), AsyncJob.kind != "delete"
            )
        )
        db.execute(delete(Application).where(Application.id == app_id, Application.org_id == org_id))
        if not db.scalar(
            select(Application.id).where(Application.candidate_id == candidate_id, Application.org_id == org_id)
        ):
            db.execute(delete(Candidate).where(Candidate.id == candidate_id, Candidate.org_id == org_id))
        audit(
            db,
            org_id,
            "worker",
            "application.deleted",
            app_id,
            {"object_versions_removed": True, "checkpoints_removed": True},
        )


def process_job(job_id):
    with SessionLocal.begin() as db:
        job = db.get(AsyncJob, job_id)
        if not job or job.status in {"done", "dead"} or aware(job.available_at) > now():
            return False
        acquired = db.execute(
            update(AsyncJob)
            .where(
                AsyncJob.id == job_id,
                or_(AsyncJob.locked_until.is_(None), AsyncJob.locked_until < now()),
                AsyncJob.status.in_(["pending", "running"]),
            )
            .values(status="running", locked_until=now() + timedelta(minutes=5), attempts=AsyncJob.attempts + 1)
        )
        if not acquired.rowcount:
            return False
        db.refresh(job)
        kind, target_id, org_id, key = job.kind, job.target_id, job.org_id, job.dedupe_key
    try:
        handlers = {
            "extract": extract_document,
            "prepare": prepare_application,
            "email": send_delivery,
            "evaluate": evaluate_application,
            "verify_recording": verify_recording,
            "delete": delete_application,
        }
        if kind == "frame":
            observe_frame(org_id, target_id, key)
        elif kind == "delete_document":
            with SessionLocal.begin() as db:
                doc = owned(db, Document, target_id, org_id)
                storage.delete_prefix(doc.object_key)
                db.delete(doc)
        else:
            handlers[kind](org_id, target_id)
        with SessionLocal.begin() as db:
            job = db.get(AsyncJob, job_id)
            if job:
                job.status, job.locked_until, job.error = "done", None, ""
        return True
    except Exception as exc:
        logger.warning("job_failed kind=%s error_type=%s", kind, type(exc).__name__)
        with SessionLocal.begin() as db:
            job = db.get(AsyncJob, job_id)
            if job:
                job.status = "dead" if job.attempts >= 3 else "pending"
                job.locked_until, job.published_at = None, None
                job.available_at = now() + timedelta(seconds=min(60, 2**job.attempts))
                job.error = type(exc).__name__ + ": inspect operational guidance"
                if kind == "email":
                    delivery = db.get(EmailDelivery, target_id)
                    if delivery:
                        delivery.status, delivery.error = "failed", job.error
        return False


def sweep():
    with SessionLocal.begin() as db:
        active = db.scalars(
            select(InterviewSession)
            .where(InterviewSession.status == "active", InterviewSession.deadline_at < now())
            .with_for_update(skip_locked=True)
        ).all()
        for session in active:
            finish_session(db, session, "server_deadline")
        expired = db.scalars(
            select(Application).where(Application.delete_after < now(), Application.status != "deleting")
        ).all()
        for app in expired:
            app.revoked, app.status = True, "deleting"
            enqueue(db, app.org_id, "delete", app.id, "delete:" + app.id)
        invites = db.scalars(
            select(Invitation).where(
                Invitation.revoked.is_(False),
                Invitation.consumed_at.is_(None),
                Invitation.expires_at > now(),
                Invitation.expires_at < now() + timedelta(days=1),
                Invitation.last_reminder_at.is_(None),
            )
        ).all()
        for invite in invites:
            app = owned(db, Application, invite.application_id, invite.org_id)
            person = owned(db, Candidate, app.candidate_id, invite.org_id)
            queue_email(
                db,
                invite.org_id,
                person.email,
                "reminder",
                "reminder:" + invite.id,
                "Your interview invitation expires soon",
                "Your Talyn interview invitation expires within 24 hours. Use the secure link in your original invitation email or contact the hiring team for accommodations.",
            )
            invite.last_reminder_at = now()
        db.execute(delete(RateBucket).where(RateBucket.created_at < now() - timedelta(days=1)))
        db.execute(delete(AuthSession).where(AuthSession.expires_at < now() - timedelta(days=1)))
        db.execute(delete(AuditLog).where(AuditLog.delete_after < now()))
        db.execute(delete(EmailDelivery).where(EmailDelivery.delete_after < now()))


def dispatch():
    with SessionLocal() as db:
        jobs = db.scalars(
            select(AsyncJob)
            .where(
                AsyncJob.status.in_(["pending", "running"]),
                AsyncJob.available_at <= now(),
                or_(AsyncJob.locked_until.is_(None), AsyncJob.locked_until < now()),
            )
            .order_by(AsyncJob.created_at)
            .limit(20)
        ).all()
        items = [(j.id, j.org_id, j.published_at) for j in jobs]
    for identifier, org_id, published_at in items:
        if settings().mode == "demo":
            process_job(identifier)
        elif not published_at or aware(published_at) < now() - timedelta(minutes=6):
            aws("sqs").send_message(
                QueueUrl=settings().queue_url, MessageBody=json.dumps({"job_id": identifier, "org_id": org_id})
            )
            with SessionLocal.begin() as db:
                job = db.get(AsyncJob, identifier)
                if job:
                    job.published_at = now()


def receive_delivery_events():
    if not settings().event_queue_url:
        return
    sqs = aws("sqs")
    for message in sqs.receive_message(
        QueueUrl=settings().event_queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
    ).get("Messages", []):
        envelope = json.loads(message["Body"])
        # SES publishes this plain-text setup notification before JSON events.
        # The queue policy admits only our SES SNS topic; acknowledge this exact
        # control message without associating it with a customer delivery.
        if envelope.get("Message") == "Successfully validated SNS topic for Amazon SES event publishing.":
            sqs.delete_message(QueueUrl=settings().event_queue_url, ReceiptHandle=message["ReceiptHandle"])
            continue
        event = json.loads(envelope["Message"]) if "Message" in envelope else envelope
        provider_id = event.get("mail", {}).get("messageId")
        if not provider_id:
            raise ValueError("SES delivery event requires a provider message ID")
        kind = event.get("eventType", event.get("notificationType", "unknown")).lower()
        with SessionLocal.begin() as db:
            delivery = db.scalar(select(EmailDelivery).where(EmailDelivery.provider_id == provider_id))
            if delivery and not db.scalar(
                select(DeliveryEvent.id).where(DeliveryEvent.provider_event_id == message["MessageId"])
            ):
                db.add(
                    DeliveryEvent(
                        org_id=delivery.org_id,
                        delivery_id=delivery.id,
                        provider_event_id=message["MessageId"],
                        kind=kind,
                    )
                )
                # Delayed/duplicate delivery events must never undo suppression.
                if delivery.status not in {"bounced", "complained"}:
                    delivery.status = {"bounce": "bounced", "complaint": "complained", "delivery": "delivered"}.get(
                        kind, delivery.status
                    )
        sqs.delete_message(QueueUrl=settings().event_queue_url, ReceiptHandle=message["ReceiptHandle"])


def run_once():
    sweep()
    dispatch()
    if settings().mode == "aws":
        sqs = aws("sqs")
        messages = sqs.receive_message(
            QueueUrl=settings().queue_url, MaxNumberOfMessages=5, WaitTimeSeconds=5, VisibilityTimeout=300
        ).get("Messages", [])
        for message in messages:
            payload = json.loads(message["Body"])
            if payload.get("kind") == "sweep":
                sweep()
                sqs.delete_message(QueueUrl=settings().queue_url, ReceiptHandle=message["ReceiptHandle"])
                continue
            with SessionLocal() as db:
                job = db.get(AsyncJob, payload.get("job_id"))
                valid = bool(job and job.org_id == payload.get("org_id"))
            if valid:
                process_job(payload["job_id"])
                with SessionLocal() as db:
                    job = db.get(AsyncJob, payload["job_id"])
                    done = not job or job.status == "done"
                if done:
                    sqs.delete_message(QueueUrl=settings().queue_url, ReceiptHandle=message["ReceiptHandle"])
        receive_delivery_events()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    while True:
        try:
            run_once()
        except Exception as exc:
            logger.error("worker_cycle_failed error_type=%s", type(exc).__name__)
        time.sleep(2)


if __name__ == "__main__":
    main()
