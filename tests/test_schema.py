"""Tests for src/onboardiq/schema.py — T02 acceptance.

Covers:
- DecisionDraft validators (reject needs human, escalate needs evidence, valid cases)
- PiiVault defaults
- Full Blackboard round-trip through model_dump_json / model_validate_json
- RunConfig defaults
- LabelledCase validation
"""

import pytest
from pydantic import ValidationError

from onboardiq.schema import (
    Blackboard,
    ClientType,
    Decision,
    DecisionDraft,
    EvidenceRef,
    GroundTruth,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    Phase,
    PiiVault,
    Reasoning,
    RiskTier,
    RunConfig,
)

# ---------- DecisionDraft validators ----------


class TestDecisionDraft:
    def test_reject_requires_human(self):
        """Rejection without human confirmation must fail."""
        with pytest.raises(ValidationError, match="human-confirmed"):
            DecisionDraft(
                decision=Decision.REJECT,
                rationale="suspicious",
                evidence_ids=["e1"],
                requires_human=False,
            )

    def test_escalate_requires_evidence(self):
        """Escalation with empty evidence must fail."""
        with pytest.raises(ValidationError, match="requires evidence"):
            DecisionDraft(
                decision=Decision.ESCALATE,
                rationale="sanctions near-match",
                evidence_ids=[],
                requires_human=True,
            )

    def test_reject_with_empty_evidence_fails(self):
        """Rejection also requires evidence."""
        with pytest.raises(ValidationError, match="requires evidence"):
            DecisionDraft(
                decision=Decision.REJECT,
                rationale="bad actor",
                evidence_ids=[],
                requires_human=True,
            )

    def test_valid_escalation(self):
        d = DecisionDraft(
            decision=Decision.ESCALATE,
            rationale="sanctions near-match",
            evidence_ids=["e1"],
            requires_human=True,
        )
        assert d.requires_human is True
        assert d.revision == 0

    def test_valid_approve(self):
        """Approve does not require evidence or human flag."""
        d = DecisionDraft(
            decision=Decision.APPROVE,
            rationale="all clear",
            evidence_ids=[],
            requires_human=False,
        )
        assert d.decision == Decision.APPROVE

    def test_valid_reject_with_human(self):
        """Reject with human confirmation and evidence is fine."""
        d = DecisionDraft(
            decision=Decision.REJECT,
            rationale="confirmed fraud",
            evidence_ids=["e1", "e2"],
            requires_human=True,
        )
        assert d.decision == Decision.REJECT
        assert d.requires_human is True

    def test_rationale_max_length(self):
        """Rationale exceeding 1200 chars must fail."""
        with pytest.raises(ValidationError):
            DecisionDraft(
                decision=Decision.APPROVE,
                rationale="x" * 1201,
                evidence_ids=[],
                requires_human=False,
            )


# ---------- PiiVault defaults ----------


class TestPiiVault:
    def test_defaults(self):
        """PiiVault requires raw_name and address; others default."""
        vault = PiiVault(raw_name="Alice Smith", address="123 Main St")
        assert vault.dob is None
        assert vault.id_numbers == {}
        assert vault.raw_document_text == {}

    def test_with_all_fields(self):
        vault = PiiVault(
            raw_name="Bob Jones",
            dob="1990-05-15",
            address="456 Elm Ave",
            id_numbers={"pan": "ABCDE1234F"},
            raw_document_text={"doc1": "OCR text here"},
        )
        assert vault.raw_name == "Bob Jones"
        assert vault.id_numbers["pan"] == "ABCDE1234F"


# ---------- RunConfig defaults ----------


class TestRunConfig:
    def test_defaults(self):
        """RunConfig with only case_id should fill sensible defaults."""
        cfg = RunConfig(case_id="case_001")
        assert cfg.mode == Mode.BLACKBOARD
        assert cfg.pattern == Pattern.SEQUENTIAL
        assert cfg.reasoning == Reasoning.PLAIN
        assert cfg.persona == Persona.COOPERATIVE
        assert cfg.seed == 0
        assert cfg.guardrails_enabled is True

    def test_custom_config(self):
        cfg = RunConfig(
            case_id="case_042",
            mode=Mode.HYBRID_P2P,
            pattern=Pattern.PARALLEL,
            reasoning=Reasoning.REACT,
            persona=Persona.INJECTING,
            seed=42,
            guardrails_enabled=False,
        )
        assert cfg.mode == Mode.HYBRID_P2P
        assert cfg.persona == Persona.INJECTING
        assert cfg.guardrails_enabled is False


# ---------- LabelledCase validation ----------


class TestLabelledCase:
    def test_valid_individual(self):
        case = LabelledCase(
            case_id="case_001",
            client_type=ClientType.INDIVIDUAL,
            declared_name="Priya Sharma",
            declared_dob="1988-03-12",
            declared_country="IN",
            declared_address="42 MG Road, Mumbai",
            declared_source_of_funds="salary",
            expected_monthly_volume_inr=50000,
            documents=["data/docs/case_001_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
            ),
        )
        assert case.client_type == ClientType.INDIVIDUAL
        assert case.ground_truth.is_namesake_false_positive is False

    def test_valid_company(self):
        case = LabelledCase(
            case_id="case_020",
            client_type=ClientType.COMPANY,
            declared_name="Acme Holdings Pvt Ltd",
            declared_country="IN",
            declared_address="1 Corporate Park, Delhi",
            declared_source_of_funds="business_revenue",
            expected_monthly_volume_inr=500000,
            ownership_chart={"Acme Holdings": {"Owner A": 60, "Owner B": 40}},
            ground_truth=GroundTruth(
                expected_tier=RiskTier.MEDIUM,
                expected_decision=Decision.APPROVE_EDD,
                planted_flags=["opaque_ownership"],
            ),
        )
        assert case.ownership_chart is not None

    def test_negative_volume_fails(self):
        with pytest.raises(ValidationError):
            LabelledCase(
                case_id="bad",
                client_type=ClientType.INDIVIDUAL,
                declared_name="X",
                declared_country="IN",
                declared_address="Y",
                declared_source_of_funds="unknown",
                expected_monthly_volume_inr=-100,
                ground_truth=GroundTruth(
                    expected_tier=RiskTier.LOW,
                    expected_decision=Decision.APPROVE,
                ),
            )

    def test_missing_ground_truth_fails(self):
        with pytest.raises(ValidationError):
            LabelledCase(
                case_id="bad",
                client_type=ClientType.INDIVIDUAL,
                declared_name="X",
                declared_country="IN",
                declared_address="Y",
                declared_source_of_funds="z",
                expected_monthly_volume_inr=1000,
                # ground_truth is required — omitting it
            )


# ---------- Blackboard round-trip ----------


def _make_blackboard() -> Blackboard:
    """Build a minimal but complete Blackboard for round-trip tests."""
    profile = MaskedProfile(
        case_id="case_rt",
        client_type=ClientType.INDIVIDUAL,
        display_name="Test User",
        country="IN",
        source_of_funds="salary",
        expected_monthly_volume_inr=25000,
    )
    vault = PiiVault(
        raw_name="Test User Real Name",
        dob="1990-01-01",
        address="100 Test Lane",
        id_numbers={"pan": "AAAA1111BB"},
    )
    return Blackboard(
        run_id="run_rt_001",
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(profile=profile),
        pii_vault=vault,
    )


class TestBlackboardRoundTrip:
    def test_json_round_trip(self):
        """Blackboard -> JSON string -> Blackboard produces identical data."""
        board = _make_blackboard()
        json_str = board.model_dump_json()
        restored = Blackboard.model_validate_json(json_str)

        assert restored.run_id == board.run_id
        assert restored.mode == board.mode
        assert restored.pattern == board.pattern
        assert restored.phase == Phase.INTAKE
        assert restored.intake.profile.display_name == "Test User"
        assert restored.pii_vault.raw_name == "Test User Real Name"
        assert restored.pii_vault.id_numbers["pan"] == "AAAA1111BB"
        assert restored.version == 0
        assert restored.verification.checks == []
        assert restored.screening.hits == []
        assert restored.risk.assessment is None
        assert restored.review.final_decision is None
        assert restored.system.traces == []

    def test_dict_round_trip(self):
        """Blackboard -> dict -> Blackboard via model_validate."""
        board = _make_blackboard()
        data = board.model_dump()
        restored = Blackboard.model_validate(data)
        assert restored == board

    def test_version_and_phase(self):
        """Version starts at 0 and phase starts at INTAKE."""
        board = _make_blackboard()
        assert board.version == 0
        assert board.phase == Phase.INTAKE


# ---------- EvidenceRef ----------


class TestEvidenceRef:
    def test_minimal(self):
        ref = EvidenceRef(evidence_id="ev001", agent_id="adk.extractor")
        assert ref.tool is None
        assert ref.record_id is None
        assert ref.created_at is not None

    def test_with_tool(self):
        ref = EvidenceRef(
            evidence_id="ev002",
            agent_id="crewai.sanctions_screener",
            tool="sanctions_screen",
            record_id="hit_001",
        )
        assert ref.tool == "sanctions_screen"
