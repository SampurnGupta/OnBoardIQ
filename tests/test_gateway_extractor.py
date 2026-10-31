"""Unit tests for ADK Gateway and Extractor agents (T06 acceptance)."""

from pathlib import Path

from onboardiq.agents.adk.extractor import DocumentExtractorAgent
from onboardiq.agents.adk.gateway import SecurityGateway
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
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


def test_gateway_and_extractor_pipeline():
    case_path = ROOT_DIR / "data" / "cases" / "case_001.json"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_test_t06",
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

    gateway = SecurityGateway()
    masked, pii, ver = gateway.process_application(case, board.run_id, board_client, current_version=0)
    assert masked.display_name == "Priya S."
    assert pii.raw_name == "Priya Rajesh Sharma"

    extractor = DocumentExtractorAgent()
    docs, ver = extractor.extract_documents(case.documents, board.run_id, board_client, current_version=ver)
    assert len(docs) == 2
    assert docs[0].doc_type == "pan_card"
    assert len(docs[0].fields) >= 2

    # Check that events and documents are logged in blackboard
    intake = board_client.get_zone(board.run_id, "intake", agent_id="adk.orchestrator")
    assert len(intake["documents"]) == 2
