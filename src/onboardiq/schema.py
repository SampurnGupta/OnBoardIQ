"""Shared Pydantic contract for OnboardIQ.

Every agent reads and writes these types on the blackboard. Do not change field
names or validators without updating docs/03_ARCHITECTURE.md and the tests.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def now() -> datetime:
    return datetime.now(UTC)


# ---------- Enums ----------
class ClientType(str, Enum):
    INDIVIDUAL = "individual"
    COMPANY = "company"


class Mode(str, Enum):
    BLACKBOARD = "blackboard"
    HYBRID_P2P = "hybrid_p2p"


class Pattern(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class Reasoning(str, Enum):
    REACT = "react"
    PLAIN = "plain"


class Persona(str, Enum):
    COOPERATIVE = "cooperative"
    IMPATIENT = "impatient"    # pressures staff, claims urgency
    ABUSIVE = "abusive"        # toxic language, threats
    FORGER = "forger"          # tampered or inconsistent documents
    INJECTING = "injecting"    # hidden instructions in forms or documents


class Phase(str, Enum):
    INTAKE = "intake"
    EXTRACTION = "extraction"
    SCREENING = "screening"
    RISK = "risk"
    REVIEW = "review"
    DECISION = "decision"
    CLOSED = "closed"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Decision(str, Enum):
    APPROVE = "approve"
    APPROVE_EDD = "approve_with_enhanced_monitoring"
    REQUEST_INFO = "request_info"
    ESCALATE = "escalate_to_human"
    REJECT = "reject"  # only after human confirmation


# ---------- Run configuration ----------
class RunConfig(BaseModel):
    """One evaluation run. The eval runner sweeps these."""
    case_id: str
    mode: Mode = Mode.BLACKBOARD
    pattern: Pattern = Pattern.SEQUENTIAL
    reasoning: Reasoning = Reasoning.PLAIN
    persona: Persona = Persona.COOPERATIVE
    seed: int = 0
    guardrails_enabled: bool = True


# ---------- Provenance ----------
class EvidenceRef(BaseModel):
    evidence_id: str
    agent_id: str
    tool: str | None = None
    record_id: str | None = None
    created_at: datetime = Field(default_factory=now)


# ---------- Intake ----------
class MaskedProfile(BaseModel):
    """What non-privileged agents are allowed to see."""
    case_id: str
    client_type: ClientType
    display_name: str
    country: str
    age_band: str | None = None  # e.g. "30-39"
    id_last4: str | None = None
    occupation: str | None = None
    source_of_funds: str
    expected_monthly_volume_inr: float = Field(ge=0)


class PiiVault(BaseModel):
    """Restricted zone. Only gateway, extractor and identity verifier may read."""
    raw_name: str
    dob: str | None = None
    id_numbers: dict[str, str] = Field(default_factory=dict)  # e.g. {"pan": "..."}
    address: str
    raw_document_text: dict[str, str] = Field(default_factory=dict)  # doc_id -> OCR text


# ---------- Documents and verification ----------
class ExtractedField(BaseModel):
    name: str  # e.g. "full_name", "dob", "address"
    value: str
    confidence: float = Field(ge=0, le=1)
    source_doc_id: str
    evidence: EvidenceRef


class DocumentRecord(BaseModel):
    doc_id: str
    doc_type: Literal[
        "pan_card", "passport", "address_proof",
        "incorporation_cert", "ownership_chart", "other",
    ]
    file_hash: str
    tamper_score: float = Field(default=0.0, ge=0, le=1)  # higher = more suspicious
    fields: list[ExtractedField] = Field(default_factory=list)


class IdentityCheck(BaseModel):
    check_id: str
    check_type: Literal[
        "name_match", "dob_match", "address_match", "registry_lookup", "cross_document",
    ]
    passed: bool
    similarity: float | None = Field(default=None, ge=0, le=1)
    detail: str
    evidence: EvidenceRef


# ---------- Screening ----------
class ScreeningHit(BaseModel):
    hit_id: str
    subject: str  # applicant or a beneficial owner
    list_name: Literal["OFAC_SDN", "UN_CONSOLIDATED", "PEP", "INTERNAL_WATCH"]
    matched_name: str
    match_score: float = Field(ge=0, le=1)
    disposition: Literal["true_match", "likely_match", "false_positive", "unresolved"]
    reasoning: str
    evidence: EvidenceRef


class MediaFinding(BaseModel):
    finding_id: str
    summary: str  # paraphrased; do not copy article text
    source_url: str
    category: Literal["fraud", "money_laundering", "corruption", "other", "none"]
    relevance: float = Field(ge=0, le=1)  # is it really this person?
    evidence: EvidenceRef


class UBOEntry(BaseModel):
    owner_name: str
    ownership_pct: float = Field(ge=0, le=100)
    path: list[str]  # chain of entities to the owner
    verified: bool
    evidence: EvidenceRef


class RedFlag(BaseModel):
    flag_id: str
    flag_type: Literal[
        "doc_tampering", "identity_mismatch", "sanctions_hit", "pep",
        "adverse_media", "opaque_ownership", "inconsistent_funds",
        "social_engineering", "injection_attempt",
    ]
    severity: Literal["low", "medium", "high"]
    raised_by: str
    evidence_ids: list[str]


# ---------- Risk and decision ----------
class RiskFactor(BaseModel):
    name: str
    contribution: float  # points added to the score
    evidence_ids: list[str]


class RiskAssessment(BaseModel):
    score: float = Field(ge=0, le=100)
    tier: RiskTier
    ml_probability_high: float = Field(ge=0, le=1)
    model_version: str
    factors: list[RiskFactor]


class DecisionDraft(BaseModel):
    decision: Decision
    rationale: str = Field(max_length=1200)
    evidence_ids: list[str]
    requires_human: bool
    revision: int = 0

    @model_validator(mode="after")
    def must_be_justified(self) -> DecisionDraft:
        if self.decision in (Decision.REJECT, Decision.ESCALATE) and not self.evidence_ids:
            raise ValueError("reject or escalate requires evidence")
        if self.decision == Decision.REJECT and not self.requires_human:
            raise ValueError("rejection must be human-confirmed")
        return self


class PolicyCheck(BaseModel):
    rule_id: str
    passed: bool
    note: str


class Challenge(BaseModel):
    challenge_id: str
    point: str
    resolved: bool = False
    resolution: str | None = None


# ---------- Security and telemetry ----------
class GuardrailEvent(BaseModel):
    event_id: str
    stage: Literal[
        "input", "document_text", "tool_input", "tool_output",
        "model_output", "blackboard_access",
    ]
    category: Literal[
        "toxicity", "prompt_injection", "social_engineering", "pii_leak",
        "schema_violation", "access_denied", "clean",
    ]
    action: Literal["allowed", "masked", "blocked"]
    agent_id: str
    score: float = Field(ge=0, le=1)
    detail: str = ""
    created_at: datetime = Field(default_factory=now)


class StepTrace(BaseModel):
    """One model, tool, guardrail, A2A or blackboard step by one agent (feeds heatmaps)."""
    trace_id: str
    agent_id: str
    framework: Literal["crewai", "adk"]
    phase: Phase
    step_type: Literal["model", "tool", "guardrail", "a2a", "blackboard"]
    name: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    created_at: datetime = Field(default_factory=now)


# ---------- Zones and blackboard root ----------
class IntakeZone(BaseModel):
    profile: MaskedProfile
    documents: list[DocumentRecord] = Field(default_factory=list)


class VerificationZone(BaseModel):
    checks: list[IdentityCheck] = Field(default_factory=list)


class ScreeningZone(BaseModel):
    hits: list[ScreeningHit] = Field(default_factory=list)
    media: list[MediaFinding] = Field(default_factory=list)
    ubos: list[UBOEntry] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)


class RiskZone(BaseModel):
    assessment: RiskAssessment | None = None
    draft: DecisionDraft | None = None


class ReviewZone(BaseModel):
    policy_checks: list[PolicyCheck] = Field(default_factory=list)
    challenges: list[Challenge] = Field(default_factory=list)
    final_decision: Decision | None = None
    human_override: str | None = None


class SystemZone(BaseModel):
    guardrail_events: list[GuardrailEvent] = Field(default_factory=list)
    traces: list[StepTrace] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rfi_rounds: int = 0


class Blackboard(BaseModel):
    run_id: str
    version: int = 0  # optimistic concurrency
    mode: Mode
    pattern: Pattern
    reasoning: Reasoning
    persona: Persona
    phase: Phase = Phase.INTAKE
    intake: IntakeZone
    pii_vault: PiiVault  # restricted zone
    verification: VerificationZone = Field(default_factory=VerificationZone)
    screening: ScreeningZone = Field(default_factory=ScreeningZone)
    risk: RiskZone = Field(default_factory=RiskZone)
    review: ReviewZone = Field(default_factory=ReviewZone)
    system: SystemZone = Field(default_factory=SystemZone)


# ---------- Evaluation dataset ----------
class GroundTruth(BaseModel):
    expected_tier: RiskTier
    expected_decision: Decision
    planted_flags: list[str] = Field(default_factory=list)
    is_namesake_false_positive: bool = False


class LabelledCase(BaseModel):
    case_id: str
    client_type: ClientType
    declared_name: str
    declared_dob: str | None = None
    declared_country: str
    declared_address: str
    declared_source_of_funds: str
    expected_monthly_volume_inr: float = Field(ge=0)
    documents: list[str] = Field(default_factory=list)
    ownership_chart: dict | None = None
    ground_truth: GroundTruth


# ---------- Final structured output ----------
class AgentMetrics(BaseModel):
    agent_id: str
    total_latency_ms: float
    tokens: int
    cost_usd: float
    tool_calls: int
    errors: int
    guardrail_triggers: int


class OnboardingReport(BaseModel):
    run_id: str
    case_id: str
    mode: Mode
    pattern: Pattern
    reasoning: Reasoning
    persona: Persona
    decision: Decision
    risk_tier: RiskTier
    risk_score: float
    red_flags: list[RedFlag]
    sanctions_or_pep_hits: int
    decision_rationale: str
    evidence_trail: list[EvidenceRef]
    pii_leak_detected: bool
    injection_succeeded: bool
    guardrail_events: int
    total_cost_usd: float
    total_runtime_s: float
    per_agent: list[AgentMetrics]
    summary_markdown: str
