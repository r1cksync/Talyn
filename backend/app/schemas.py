from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class VerifyRegistration(StrictModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=10)


class OrgInput(StrictModel):
    name: str = Field(min_length=2, max_length=120)


class MemberInput(StrictModel):
    email: EmailStr
    role: Literal["recruiter", "reviewer"]


class CriterionInput(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=3, max_length=2000)
    weight: float = Field(default=1, gt=0, le=10)
    anchors: dict[str, str] = Field(
        default_factory=lambda: {
            "1": "Limited relevant evidence",
            "2": "Partial evidence",
            "3": "Meets the criterion with a concrete example",
            "4": "Strong reasoning and tradeoffs",
            "5": "Exceptional depth and evidence",
        }
    )


class JobInput(StrictModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=20, max_length=20000)
    seniority: str = Field(default="Mid-level", max_length=40)
    skills: list[str] = Field(min_length=1, max_length=20)
    duration_minutes: int = Field(default=30, ge=5, le=60)
    criteria: list[CriterionInput] = Field(min_length=1, max_length=10)


class CandidateInput(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr


class DocumentInput(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    size: int = Field(gt=0, le=10485760)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Literal["resume", "cover_letter"] = "resume"


class QuestionInput(StrictModel):
    text: str = Field(min_length=10, max_length=1500)
    competency: str = Field(max_length=100)
    kind: Literal["core", "personalized", "behavioral", "situational"]
    expected_evidence: list[str] = Field(min_length=1, max_length=8)
    time_limit_seconds: int = Field(default=180, ge=30, le=600)
    max_followups: int = Field(default=1, ge=0, le=1)
    source_refs: list[str] = Field(default_factory=list, max_length=10)


class PlanOutput(StrictModel):
    questions: list[QuestionInput] = Field(min_length=2, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class PlanEdit(StrictModel):
    questions: list[QuestionInput] = Field(min_length=2, max_length=10)
    dimensions: list[CriterionInput] = Field(min_length=1, max_length=10)
    approve: bool = True
    version: int = Field(ge=1)


class ExtractedClaims(StrictModel):
    skills: list[str] = Field(default_factory=list, max_length=50)
    experience: list[str] = Field(default_factory=list, max_length=30)
    projects: list[str] = Field(default_factory=list, max_length=30)
    education: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=100)


class CampaignInput(StrictModel):
    application_ids: list[str] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=10, max_length=100)


class InviteInput(StrictModel):
    token: str = Field(min_length=32, max_length=200)


class ChallengeInput(StrictModel):
    challenge_id: str
    code: str = Field(pattern=r"^\d{6}$")


class ConsentInput(StrictModel):
    policy_version: Literal["2026-09-v1", "2026-09-v2-groq"]
    recording: bool
    transcription: bool
    ai_evaluation: bool
    device_check: bool


class TurnInput(StrictModel):
    turn: int = Field(ge=0)


class DemoAnswer(StrictModel):
    text: str = Field(min_length=1, max_length=10000)
    result_id: str = Field(min_length=1, max_length=100)
    final: bool = True


class ClipInput(StrictModel):
    sequence: int = Field(ge=0, le=1000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(gt=0, le=20971520)
    content_type: Literal["video/webm", "video/mp4"]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class ManifestInput(StrictModel):
    expected_clips: int = Field(ge=0, le=1001)


class EvidenceInput(StrictModel):
    segment_id: str
    quote: str = Field(min_length=1, max_length=2000)


class DimensionScore(StrictModel):
    name: str
    score: int | None = Field(ge=1, le=5)
    explanation: str = Field(max_length=2000)
    evidence: list[EvidenceInput] = Field(max_length=10)
    missing_evidence: list[str] = Field(max_length=10)
    insufficient_evidence: bool


class EvaluationOutput(StrictModel):
    dimensions: list[DimensionScore] = Field(min_length=1, max_length=10)
    summary: str = Field(max_length=3000)
    strengths: list[str] = Field(max_length=10)
    further_assessment: list[str] = Field(max_length=10)


class FollowupOutput(StrictModel):
    needs_followup: bool
    question: str = Field(max_length=600)


class ManagerReport(StrictModel):
    synthetic: bool
    summary: str
    dimensions: list[DimensionScore]
    strengths: list[str]
    further_assessment: list[str]
    incomplete_sections: list[str]
    ai_generated: bool = True


class CandidateReport(StrictModel):
    synthetic: bool
    competencies: list[str]
    strengths: list[str]
    suggestions: list[str]
    feedback: str
    ai_generated: bool = True


class NoteInput(StrictModel):
    notes: str = Field(max_length=10000)
    decision: Literal["pending", "advance", "hold", "decline"]


class ExplanationInput(StrictModel):
    explanation: str = Field(max_length=2000)


class AccommodationInput(StrictModel):
    request: str = Field(min_length=1, max_length=2000)


class OrgSettingsInput(StrictModel):
    retention_days: int = Field(ge=1, le=365)
