"""Unit tests for A2A Service & Agent Card (T08 acceptance)."""

from pathlib import Path

from fastapi.testclient import TestClient

from onboardiq.agents.crewai.a2a_server import app as a2a_app
from onboardiq.agents.crewai.a2a_server import invoke_a2a_screening
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app as bb_app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    Blackboard,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
)

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_a2a_agent_card_discovery():
    client = TestClient(a2a_app)
    resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "crewai-screening-crew"
    assert card["framework"] == "CrewAI"
    assert len(card["skills"]) >= 1


def test_a2a_screening_remote_call():
    case_path = ROOT_DIR / "data" / "cases" / "case_001.json"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))

    bb_app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=bb_app)
    a2a_app.state.board_client = board_client

    board = Blackboard(
        run_id="run_test_t08",
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id=case.case_id,
                client_type=case.client_type,
                display_name=case.declared_name,
                country=case.declared_country,
                source_of_funds=case.declared_source_of_funds,
                expected_monthly_volume_inr=case.expected_monthly_volume_inr,
            )
        ),
        pii_vault=PiiVault(raw_name=case.declared_name, address=case.declared_address),
    )
    board_client.create_run(board)

    a2a_client = TestClient(a2a_app)
    res, new_ver = invoke_a2a_screening(
        run_id=board.run_id,
        current_version=0,
        board_client=board_client,
        transport=a2a_client,  # type: ignore[arg-type]
    )

    assert res.status == "success"
    assert new_ver > 0

    # Verify StepTrace with step_type="a2a" exists
    system_zone = board_client.get_zone(board.run_id, "system", agent_id="adk.orchestrator")
    assert any(t["step_type"] == "a2a" for t in system_zone["traces"])

