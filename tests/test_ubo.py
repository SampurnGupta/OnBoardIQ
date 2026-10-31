"""Tests for corporate UBO graph analysis and ownership path screening.

Per docs/06_IMPLEMENTATION_PLAN.md T15:
- Clean company case: case_007 (Apex Global Logistics Pvt Ltd)
- Sanctioned owner case: case_008 (Nordic Import Export LLP -> Viktor Darkovich)
- Opaque ownership case: case_009 (Horizon Holdings -> BVI Shadow Trust)
"""

from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.mcp_server.tools.ubo_graph import resolve_ubo_graph
from onboardiq.schema import Decision, LabelledCase, RiskTier, RunConfig


def test_ubo_graph_tool_direct():
    """Unit test for ubo_graph tool directly."""
    clean_chart = {
        "entity": "Clean Corp",
        "owners": [
            {"name": "Owner A", "pct": 70.0, "path": ["Clean Corp", "Owner A"]},
            {"name": "Owner B", "pct": 30.0, "path": ["Clean Corp", "Owner B"]},
        ],
    }
    clean_res = resolve_ubo_graph(clean_chart)
    assert not clean_res.is_opaque
    assert len(clean_res.ubos) == 2
    assert clean_res.ubos[0].owner_name == "Owner A"
    assert clean_res.ubos[0].ownership_pct == 70.0

    # Opaque chart
    opaque_chart = {
        "entity": "Shell Co",
        "owners": [
            {
                "name": "Panama Shadow Nominee Ltd",
                "pct": 100.0,
                "path": ["Shell Co", "Panama Shadow Nominee Ltd"],
            }
        ],
    }
    opaque_res = resolve_ubo_graph(opaque_chart)
    assert opaque_res.is_opaque
    assert len(opaque_res.opaque_reasons) > 0


def test_company_clean_case():
    """Clean company case: case_007 resolves owners and approves cleanly."""
    case_path = Path("data/cases/case_007.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)
    orch = Orchestrator()

    report = orch.run_case(case=case, board_client=client, config=RunConfig(case_id=case.case_id))

    assert report.decision == Decision.APPROVE
    assert report.risk_tier == RiskTier.LOW
    assert len(report.red_flags) == 0

    # Check that UBOs were written to blackboard screening zone
    board = client.get_run(report.run_id, agent_id="adk.orchestrator")
    assert len(board.screening.ubos) == 2
    owner_names = {u.owner_name for u in board.screening.ubos}
    assert "Manoj Deshmukh" in owner_names
    assert "Sneha Deshmukh" in owner_names


def test_company_sanctioned_owner():
    """Sanctioned owner case: case_008 detects Viktor Darkovich (45%) on OFAC and escalates."""
    case_path = Path("data/cases/case_008.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)
    orch = Orchestrator()

    report = orch.run_case(case=case, board_client=client, config=RunConfig(case_id=case.case_id))

    assert report.decision == Decision.ESCALATE
    assert report.risk_tier == RiskTier.HIGH
    flag_types = [rf.flag_type for rf in report.red_flags]
    assert "sanctions_hit" in flag_types

    board = client.get_run(report.run_id, agent_id="adk.orchestrator")
    assert len(board.screening.ubos) == 2
    assert any(h.matched_name == "Viktor Darkovich" for h in board.screening.hits)


def test_company_opaque_ownership():
    """Opaque ownership case: case_009 flags BVI Shadow Trust and raises opaque_ownership."""
    case_path = Path("data/cases/case_009.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)
    orch = Orchestrator()

    report = orch.run_case(case=case, board_client=client, config=RunConfig(case_id=case.case_id))

    flag_types = [rf.flag_type for rf in report.red_flags]
    assert "opaque_ownership" in flag_types
    # Medium risk tier expected for enhanced monitoring
    assert report.risk_tier in (RiskTier.MEDIUM, RiskTier.HIGH)
