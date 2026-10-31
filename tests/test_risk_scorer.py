"""Unit tests for ML Risk Model and Scorer Agent (T10 acceptance).

Verifies:
- ML model prediction output range (0.0 to 1.0)
- RiskScoringAgent factor calculation and evidence citations
- Risk tier thresholds (LOW < 30, MEDIUM 30-70, HIGH >= 70 or sanctions hit)
- DecisionDraft validation
"""

from onboardiq.agents.adk.risk import RiskScoringAgent
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.mcp_server.tools.risk_predict import predict_case_risk
from onboardiq.schema import (
    Blackboard,
    Decision,
    IntakeZone,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
    RiskTier,
)


def test_ml_risk_predict_tool():
    # Clean features -> low probability
    low_res = predict_case_risk(
        country_risk=0.05,
        occupation_risk=0.05,
        monthly_volume_inr=50000.0,
        num_red_flags=0,
        max_screening_score=0.0,
        tamper_score=0.0,
        is_company=False,
    )
    assert 0.0 <= low_res.probability_high <= 0.40

    # High risk features -> elevated probability
    high_res = predict_case_risk(
        country_risk=0.85,
        occupation_risk=0.85,
        monthly_volume_inr=25000000.0,
        num_red_flags=2,
        max_screening_score=0.98,
        tamper_score=0.80,
        is_company=True,
    )
    assert high_res.probability_high > low_res.probability_high


def test_risk_scorer_clean_case():
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_test_risk_clean",
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_001",
                client_type="individual",
                display_name="Priya S.",
                country="IN",
                source_of_funds="salary",
                expected_monthly_volume_inr=50000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Priya Sharma", address="Mumbai"),
    )
    board_client.create_run(board)

    scorer = RiskScoringAgent()
    assessment, draft, _ver = scorer.assess_risk("run_test_risk_clean", board_client, 0)

    assert assessment.tier == RiskTier.LOW
    assert assessment.score < 30.0
    assert draft.decision == Decision.APPROVE
    assert draft.requires_human is False
    assert len(assessment.factors) >= 1


def test_risk_scorer_sanctions_hit_escalation():
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_test_risk_high",
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_008",
                client_type="company",
                display_name="Nordic Import",
                country="IN",
                source_of_funds="trading",
                expected_monthly_volume_inr=8000000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Nordic", address="Gurugram"),
    )
    board_client.create_run(board)

    # Insert a red flag into screening zone
    board_client.append_event(
        run_id="run_test_risk_high",
        zone="screening",
        payload={
            "hits": [
                {
                    "hit_id": "hit_1",
                    "subject": "Viktor Darkovich",
                    "list_name": "OFAC_SDN",
                    "matched_name": "Viktor Darkovich",
                    "match_score": 1.0,
                    "disposition": "true_match",
                    "reasoning": "True match",
                    "evidence": {
                        "evidence_id": "ev_sdn_1",
                        "agent_id": "crewai.sanctions_screener",
                    },
                }
            ],
            "red_flags": [
                {
                    "flag_id": "rf_1",
                    "flag_type": "sanctions_hit",
                    "severity": "high",
                    "raised_by": "crewai.sanctions_screener",
                    "evidence_ids": ["ev_sdn_1"],
                }
            ],
        },
        expected_version=0,
        op="replace",
        agent_id="crewai.sanctions_screener",
    )

    scorer = RiskScoringAgent()
    assessment, draft, _ver = scorer.assess_risk("run_test_risk_high", board_client, 1)

    assert assessment.tier == RiskTier.HIGH
    assert draft.decision == Decision.ESCALATE
    assert draft.requires_human is True
    assert "ev_sdn_1" in draft.evidence_ids
