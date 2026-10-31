"""Tests for Compliance Reviewer Agent and Policy Reflection Loop (Task T24).

Verifies:
- policy_rag tool retrieval
- Reviewer passing clean case on first attempt (revision 0)
- Reviewer forcing revision when draft violates policy (reflection loop to revision 1)
- Maximum 2 revision loops constraint
"""

from __future__ import annotations

from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.agents.adk.reviewer import ComplianceReviewerAgent
from onboardiq.agents.adk.risk import RiskScoringAgent
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.mcp_server.tools.policy_rag import query_policy
from onboardiq.schema import (
    Blackboard,
    ClientType,
    Decision,
    DecisionDraft,
    EvidenceRef,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
    RunConfig,
    ScreeningHit,
    ScreeningZone,
)


def _get_test_client() -> BlackboardClient:
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    return BlackboardClient(base_url="http://testserver", app=app, agent_id="admin")


def test_policy_rag_tool():
    """Verify policy_rag retrieves exact and semantic policy rules from data/policy.md."""
    # 1. Query by rule_id
    res_r2 = query_policy(query="", rule_id="Rule 2")
    assert res_r2["count"] == 1
    assert "Sanctions" in res_r2["matches"][0]["title"]

    # 2. Query by keyword: auto-reject
    res_reject = query_policy(query="auto-reject")
    assert res_reject["count"] >= 1
    assert any("Rule 4" in m["rule_id"] for m in res_reject["matches"])

    # 3. Query by keyword: PEP
    res_pep = query_policy(query="PEP requirements")
    assert res_pep["count"] >= 1
    assert any("Rule 3" in m["rule_id"] for m in res_pep["matches"])


def test_reviewer_passes_clean_case_first_attempt():
    """Verify that a compliant draft passes review on the first attempt without revision (revision=0)."""
    client = _get_test_client()
    orch = Orchestrator()

    case_path = Path("data/cases/case_001.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    cfg = RunConfig(case_id=case.case_id, mode=Mode.BLACKBOARD, pattern=Pattern.SEQUENTIAL)
    report = orch.run_case(case=case, board_client=client, run_id="run_test_review_clean", config=cfg)

    bb = client.get_run("run_test_review_clean", agent_id="admin")
    assert report.decision == Decision.APPROVE
    assert bb.review.final_decision == Decision.APPROVE
    # All policy checks passed
    assert len(bb.review.policy_checks) >= 5
    assert all(pc.passed for pc in bb.review.policy_checks)
    # Zero challenges issued
    assert len(bb.review.challenges) == 0


def test_reviewer_forces_revision_on_policy_violation():
    """Verify that when a draft proposes APPROVE for a case with a true sanctions hit,

    the Reviewer raises a Challenge and forces RiskScorer to revise to ESCALATE.
    """
    client = _get_test_client()
    run_id = "run_test_reflection_loop"

    # Create blackboard with a sanctions hit in screening zone
    ev = EvidenceRef(evidence_id="ev_sanction_test", agent_id="crewai.sanctions_screener", tool="sanctions_screen")
    hit = ScreeningHit(
        hit_id="hit_001",
        subject="NonCompliant Applicant",
        list_name="OFAC_SDN",
        matched_name="Sanctioned Individual",
        match_score=0.98,
        disposition="true_match",
        reasoning="Exact SDN list match",
        evidence=ev,
    )

    board = Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_synth",
                client_type=ClientType.INDIVIDUAL,
                display_name="NonCompliant Applicant",
                country="RU",
                source_of_funds="trade",
                expected_monthly_volume_inr=100000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="NonCompliant Applicant", address="Moscow"),
        screening=ScreeningZone(hits=[hit]),
    )
    client.create_run(board)

    # Intentionally plant a flawed draft proposing APPROVE despite sanctions hit
    flawed_draft = DecisionDraft(
        decision=Decision.APPROVE,
        rationale="Flawed agent proposed approval despite sanctions hit.",
        evidence_ids=[],
        requires_human=False,
        revision=0,
    )
    client.append_event_with_retry(
        run_id=run_id,
        zone="risk",
        payload={"draft": flawed_draft.model_dump(mode="json")},
        expected_version=0,
        op="update",
        agent_id="admin",
    )

    reviewer = ComplianceReviewerAgent()
    risk_scorer = RiskScoringAgent()

    # Run reviewer with risk scorer reflection loop
    _policy_checks, challenges, final_decision, _ = reviewer.review_case(
        run_id=run_id,
        board_client=client,
        current_version=1,
        risk_scorer=risk_scorer,
    )

    # 1. Verification that challenge was raised
    assert len(challenges) >= 1
    assert any("Rule 2 Violation" in c.point for c in challenges)

    # 2. Verification that reflection loop forced revision
    revised_risk = client.get_zone(run_id, "risk", agent_id="admin")
    revised_draft = DecisionDraft.model_validate(revised_risk["draft"])
    assert revised_draft.revision == 1
    assert revised_draft.decision == Decision.ESCALATE
    assert revised_draft.requires_human is True
    assert final_decision == Decision.ESCALATE

    # 3. Verification that challenge was resolved in review zone
    review_zone = client.get_zone(run_id, "review", agent_id="admin")
    assert all(c.get("resolved") is True for c in review_zone["challenges"])
