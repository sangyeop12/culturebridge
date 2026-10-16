from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class LearningLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class LearningGoal(StrEnum):
    OBSERVE = "observe"
    COMPARE = "compare"
    RELIGION = "religion"
    VERIFY = "verify"


class ComparisonScope(StrEnum):
    OVERSEAS = "overseas"
    DOMESTIC = "domestic"


class LearningAmount(StrEnum):
    BRIEF = "brief"
    STANDARD = "standard"
    DEEP = "deep"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SourceRecord(BaseModel):
    id: str
    title: str
    organization: str
    url: HttpUrl
    retrieved_at: date
    license_note: str | None = None
    summary: str = ""
    scope_note: str = ""


class HeritageSummary(BaseModel):
    id: str
    name: str
    country: str
    period: str
    location: str
    summary: str


class HeritageDetail(HeritageSummary):
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    structure: str
    material: str
    religious_context: str
    source_ids: list[str]


class RelatedHeritage(BaseModel):
    heritage: HeritageSummary
    reason: str
    score: float = Field(ge=0, le=1)
    criteria: list[str] = Field(default_factory=list)


class ComparisonRequest(BaseModel):
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = Field(default="", max_length=200)
    amount: LearningAmount = LearningAmount.STANDARD
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS
    left_id: str
    right_id: str
    level: LearningLevel = LearningLevel.BEGINNER

    @model_validator(mode="after")
    def different_heritages(self) -> "ComparisonRequest":
        from culturebridge.services.heritage_identity_service import canonical_id

        if canonical_id(self.left_id) == canonical_id(self.right_id):
            raise ValueError("서로 다른 문화유산을 선택해야 합니다.")
        return self


class ComparisonPoint(BaseModel):
    category: str
    left: str
    right: str
    explanation: str
    source_ids: list[str] = Field(default_factory=list)


class CollectedSource(BaseModel):
    id: str
    heritage_id: str
    title: str
    organization: str
    source_url: HttpUrl
    feed_url: HttpUrl
    retrieved_at: datetime | None = None
    content: str = ""
    status: str = Field(pattern=r"^(fresh|cached|stale|unavailable)$")
    scope_note: str
    license_url: HttpUrl | None = None
    content_kind: Literal["individual_text", "listed_text", "group_text", "metadata"] = "metadata"


class ExtractedField(BaseModel):
    heritage_id: str
    category: Literal["시대", "구조", "재료", "종교적 배경"]
    value: str | None = None
    source_id: str | None = None
    evidence_quote: str = ""
    source_url: HttpUrl | None = None
    verification_status: VerificationStatus = VerificationStatus.INSUFFICIENT_EVIDENCE
    method: Literal["local", "gemini"] = "local"
    note: str
    date_event: str | None = None


class CommonEvidence(BaseModel):
    statement: str
    category: str
    left_evidence: ExtractedField
    right_evidence: ExtractedField
    verification_status: VerificationStatus = VerificationStatus.NEEDS_REVIEW
    context_note: str = "양쪽 원문 표현의 후보입니다. 의미·대상 범위는 추가 검토가 필요합니다."
    method: Literal["local", "gemini"] = "local"


class ComparisonResult(BaseModel):
    learning_version: int = 0
    comparison_scope: ComparisonScope | None = None
    saved_id: str | None = None
    learning_goal: str = ""
    collected_sources: list[CollectedSource] = Field(default_factory=list)
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    basis: Literal["curated", "extracted"] = "curated"
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = ""
    amount: LearningAmount = LearningAmount.STANDARD
    learning_notices: list[str] = Field(default_factory=list)
    curriculum: list[str] = Field(default_factory=list)
    common_evidence: list[CommonEvidence] = Field(default_factory=list)
    left: HeritageSummary
    right: HeritageSummary
    level: LearningLevel
    common_points: list[str]
    differences: list[ComparisonPoint]
    source_ids: list[str]
    verification_status: VerificationStatus
    verification_note: str


class SavedComparison(BaseModel):
    id: str
    created_at: datetime
    comparison: ComparisonResult
    sources: list[SourceRecord]


class SavedComparisonSummary(BaseModel):
    id: str
    created_at: datetime
    left_name: str
    right_name: str
    level: LearningLevel


class ExplorationRequest(BaseModel):
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS
    heritage_id: str
    comparison_id: str | None = None
    level: LearningLevel = LearningLevel.BEGINNER
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = Field(default="", max_length=200)
    amount: LearningAmount = LearningAmount.STANDARD

    @model_validator(mode="after")
    def different_comparison_target(self) -> "ExplorationRequest":
        if self.comparison_id == self.heritage_id:
            raise ValueError("서로 다른 문화유산을 선택해야 합니다.")
        return self


class ExplorationResult(BaseModel):
    heritage_id: str
    comparison_id: str
    level: LearningLevel
    curriculum: list[str]
    candidates: list[RelatedHeritage]
    comparison: ComparisonResult
    verification_status: VerificationStatus
    verification_note: str
    collected_sources: list[CollectedSource] = Field(default_factory=list)
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = ""
    amount: LearningAmount = LearningAmount.STANDARD
    retry_count: int = 0
    execution_trace: list[str] = Field(default_factory=list)
    quiz: "QuizPreview | None" = None
    quiz_notice: str = ""


class QuestionRequest(BaseModel):
    history: list["ConversationTurn"] = Field(default_factory=list, max_length=6)
    left_id: str
    right_id: str
    question: str = Field(min_length=2, max_length=500)
    level: LearningLevel = LearningLevel.BEGINNER
    comparison_id: str | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("질문을 두 글자 이상 입력해야 합니다.")
        return normalized

    @model_validator(mode="after")
    def different_heritages(self) -> "QuestionRequest":
        if self.left_id == self.right_id:
            raise ValueError("서로 다른 문화유산을 선택해야 합니다.")
        return self


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=1500)


class AnswerCitation(BaseModel):
    sentence: str = Field(min_length=1, max_length=1000)
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=10, max_length=2000)


class QuestionAnswer(BaseModel):
    citations: list[AnswerCitation] = Field(default_factory=list)
    question: str
    answer: str
    source_ids: list[str]
    verification_status: VerificationStatus
    verification_note: str
    used_ai: bool
    sources: list[SourceRecord] = Field(default_factory=list)


class ClaimRequest(ComparisonRequest):
    comparison_id: str | None = None
    claim: str = Field(min_length=2, max_length=500)

    @field_validator("claim")
    @classmethod
    def normalize_claim(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("주장을 두 글자 이상 입력해야 합니다.")
        return normalized


class ClaimEvidence(BaseModel):
    heritage_id: str
    category: str
    fact: str
    source_ids: list[str]
    evidence_quote: str = ""
    source_url: HttpUrl | None = None
    relation: Literal["supports", "contradicts", "related"] = "related"


class ClaimResult(BaseModel):
    claim: str
    verification_status: VerificationStatus
    explanation: str
    evidence: list[ClaimEvidence]
    sources: list[SourceRecord]
    scope_note: str
    basis: Literal["curated", "official_snapshot"] = "curated"
    comparison_id: str | None = None
    used_ai: bool = False
    assessment: Literal[
        "source_match", "support_candidate", "contradiction_candidate", "mixed", "insufficient"
    ] = "insufficient"
    unsupported_parts: list[str] = Field(default_factory=list)
    retry_count: int = 0
    execution_trace: list[str] = Field(default_factory=list)
    collected_sources: list[CollectedSource] = Field(default_factory=list)


class QuizChoice(BaseModel):
    id: int = Field(ge=0, le=3)
    text: str


class QuizItem(BaseModel):
    id: str
    question: str
    choices: list[QuizChoice]
    correct_index: int = Field(ge=0, le=3, exclude=True)
    explanation: str = Field(exclude=True)


class QuizRequest(BaseModel):
    left_id: str
    right_id: str
    level: LearningLevel = LearningLevel.BEGINNER
    comparison_id: str | None = None

    @model_validator(mode="after")
    def different_heritages(self) -> "QuizRequest":
        if self.left_id == self.right_id:
            raise ValueError("서로 다른 문화유산을 선택해야 합니다.")
        return self


class QuizResponse(BaseModel):
    quiz_id: str
    level: LearningLevel = LearningLevel.BEGINNER
    learning_goal: str = ""
    items: list[QuizItem]
    comparison_id: str | None = None
    basis: Literal["curated", "extracted"] = "curated"
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class QuizAttemptRequest(BaseModel):
    quiz_id: str
    answers: list[int] = Field(min_length=1, max_length=5)


class QuizPreviewItem(BaseModel):
    id: str
    question: str
    choices: list[QuizChoice]


class QuizPreview(QuizResponse):
    items: list[QuizPreviewItem]


class QuizReviewItem(BaseModel):
    number: int
    question: str
    selected: str
    correct_answer: str
    activity: str
    quote: str = ""
    source_url: HttpUrl | None = None


class QuizAttemptResult(BaseModel):
    history_id: int | None = None
    review_items: list[QuizReviewItem] = Field(default_factory=list)
    quiz_id: str
    score: int
    total: int
    explanations: list[str]
    evidence: list[ExtractedField] = Field(default_factory=list)
    review_steps: list[str] = Field(default_factory=list)


ExplorationResult.model_rebuild()
QuestionRequest.model_rebuild()
