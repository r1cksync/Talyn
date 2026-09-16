from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Tenant(Entity):
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Organization(Entity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120))
    retention_days: Mapped[int] = mapped_column(default=30)
    max_minutes: Mapped[int] = mapped_column(default=3000)
    max_concurrent: Mapped[int] = mapped_column(default=10)
    used_minutes: Mapped[int] = mapped_column(default=0)
    active_sessions: Mapped[int] = mapped_column(default=0)
    usage_period: Mapped[str] = mapped_column(
        String(7), default=lambda: now().strftime("%Y-%m"), server_default="1970-01"
    )


class Membership(Tenant, Base):
    __tablename__ = "memberships"
    subject: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="owner")
    __table_args__ = (
        UniqueConstraint("org_id", "subject"),
        CheckConstraint("role IN ('owner','recruiter','reviewer')"),
    )


class AuthSession(Entity, Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), default="")
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    csrf: Mapped[str] = mapped_column(String(100))


class Job(Tenant, Base):
    __tablename__ = "jobs"
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    seniority: Mapped[str] = mapped_column(String(40))
    skills: Mapped[list] = mapped_column(JSON, default=list)
    duration_minutes: Mapped[int] = mapped_column(default=30)
    status: Mapped[str] = mapped_column(default="draft")
    __table_args__ = (CheckConstraint("duration_minutes BETWEEN 5 AND 60"),)


class Criterion(Tenant, Base):
    __tablename__ = "job_criteria"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1)
    anchors: Mapped[dict] = mapped_column(JSON, default=dict)


class Candidate(Tenant, Base):
    __tablename__ = "candidates"
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320))
    __table_args__ = (UniqueConstraint("org_id", "email"),)


class Application(Tenant, Base):
    __tablename__ = "applications"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(default="new")
    accommodation: Mapped[str] = mapped_column(Text, default="")
    recording_required: Mapped[bool] = mapped_column(default=True)
    revoked: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("job_id", "candidate_id"),)


class Document(Tenant, Base):
    __tablename__ = "documents"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(default="resume")
    status: Mapped[str] = mapped_column(default="pending")
    error: Mapped[str] = mapped_column(Text, default="")


class Extraction(Tenant, Base):
    __tablename__ = "extractions"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    claims: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)


class Plan(Tenant, Base):
    __tablename__ = "interview_plans"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    version: Mapped[int] = mapped_column(default=1)
    approved: Mapped[bool] = mapped_column(default=False)
    model_id: Mapped[str] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSON, default=list)


class Question(Tenant, Base):
    __tablename__ = "questions"
    plan_id: Mapped[str] = mapped_column(ForeignKey("interview_plans.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    competency: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(40))
    expected_evidence: Mapped[list] = mapped_column(JSON, default=list)
    time_limit_seconds: Mapped[int] = mapped_column(default=180)
    max_followups: Mapped[int] = mapped_column(default=1)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("plan_id", "position"),)


class RubricVersion(Tenant, Base):
    __tablename__ = "rubric_versions"
    plan_id: Mapped[str] = mapped_column(ForeignKey("interview_plans.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    dimensions: Mapped[list] = mapped_column(JSON)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (UniqueConstraint("plan_id", "version"),)


class Campaign(Tenant, Base):
    __tablename__ = "campaigns"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(default="launched")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("org_id", "idempotency_key"),)


class Invitation(Tenant, Base):
    __tablename__ = "invitations"
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(default=False)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailChallenge(Tenant, Base):
    __tablename__ = "email_challenges"
    invitation_id: Mapped[str] = mapped_column(ForeignKey("invitations.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    consumed: Mapped[bool] = mapped_column(default=False)


class InterviewSession(Tenant, Base):
    __tablename__ = "interview_sessions"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(default="ready")
    question_index: Mapped[int] = mapped_column(default=0)
    followups: Mapped[int] = mapped_column(default=0)
    followup_text: Mapped[str] = mapped_column(Text, default="")
    turn: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audio_quality: Mapped[str] = mapped_column(default="unknown")
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connection_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Transition(Tenant, Base):
    __tablename__ = "session_transitions"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    from_state: Mapped[str] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(100))


class TranscriptSegment(Tenant, Base):
    __tablename__ = "transcript_segments"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    result_id: Mapped[str] = mapped_column(String(150))
    speaker: Mapped[str] = mapped_column(default="candidate")
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(default=1)
    final: Mapped[bool] = mapped_column(default=False)
    quality: Mapped[str] = mapped_column(default="unknown")
    turn: Mapped[int] = mapped_column(default=0)
    __table_args__ = (UniqueConstraint("session_id", "result_id"), CheckConstraint("end_ms >= start_ms"))


class Answer(Tenant, Base):
    __tablename__ = "answers"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    turn: Mapped[int] = mapped_column(Integer)
    segment_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="answered")
    __table_args__ = (UniqueConstraint("session_id", "turn"),)


class RecordingObject(Tenant, Base):
    __tablename__ = "recording_objects"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    verified: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("session_id", "sequence"), CheckConstraint("sequence >= 0"))


class RecordingManifest(Tenant, Base):
    __tablename__ = "recording_manifests"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True)
    expected_clips: Mapped[int] = mapped_column(Integer)
    missing_sequences: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    finalized: Mapped[bool] = mapped_column(default=False)


class Consent(Tenant, Base):
    __tablename__ = "consents"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    policy_version: Mapped[str] = mapped_column(String(30))
    recording: Mapped[bool] = mapped_column(Boolean)
    transcription: Mapped[bool] = mapped_column(Boolean)
    ai_evaluation: Mapped[bool] = mapped_column(Boolean)
    device_check: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (UniqueConstraint("application_id", "policy_version"),)


class VideoObservation(Tenant, Base):
    __tablename__ = "video_observations"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(default=1)
    visible: Mapped[bool] = mapped_column(default=False)
    dismissed: Mapped[bool] = mapped_column(default=False)
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence_key: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Evaluation(Tenant, Base):
    __tablename__ = "evaluations"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    dimensions: Mapped[list] = mapped_column(JSON)
    completeness: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("session_id", "version"),)


class Evidence(Tenant, Base):
    __tablename__ = "evidence_references"
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    segment_id: Mapped[str] = mapped_column(ForeignKey("transcript_segments.id", ondelete="CASCADE"))
    dimension: Mapped[str] = mapped_column(String(100))
    quote: Mapped[str] = mapped_column(Text)


class Report(Tenant, Base):
    __tablename__ = "reports"
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    audience: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict] = mapped_column(JSON)
    manager_notes: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(default="pending")
    __table_args__ = (
        UniqueConstraint("session_id", "audience", "version"),
        CheckConstraint("audience IN ('manager','candidate')"),
    )


class EmailDelivery(Tenant, Base):
    __tablename__ = "email_deliveries"
    recipient: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload_ciphertext: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="queued")
    provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(String(100), default="")


class DeliveryEvent(Tenant, Base):
    __tablename__ = "delivery_events"
    delivery_id: Mapped[str] = mapped_column(ForeignKey("email_deliveries.id", ondelete="CASCADE"))
    provider_event_id: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(40))


class AuditLog(Tenant, Base):
    __tablename__ = "audit_logs"
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Usage(Tenant, Base):
    __tablename__ = "usage_records"
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    meter: Mapped[str] = mapped_column(String(50), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)


class AsyncJob(Tenant, Base):
    __tablename__ = "async_jobs"
    kind: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(String(100), default="")


class RateBucket(Entity, Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(150), unique=True)
    count: Mapped[int] = mapped_column(default=0)
    window: Mapped[int] = mapped_column(Integer)


Index("ix_jobs_ready", AsyncJob.status, AsyncJob.available_at)
