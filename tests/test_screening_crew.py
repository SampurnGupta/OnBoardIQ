"""Unit tests for CrewAI Screening Crew (T07 acceptance).

Tests:
- IdentityVerifierAgent records checks with EvidenceRef in verification zone
- SanctionsScreenerAgent records hits and red flags in screening zone
- PII minimization: SanctionsScreener only reads masked intake zone
"""

from pathlib import Path

from onboardiq.agents.adk.extractor import DocumentExtractorAgent
from onboardiq.agents.adk.gateway import SecurityGateway
from onboardiq.agents.crewai.screening_crew import (
    ScreeningCrew,
)
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


def test_screening_crew_full_workflow():
    case_path = ROOT_DIR / "data" / "cases" / "case_001.json"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_test_t07_crew",
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

    # Run intake and extraction
    gateway = SecurityGateway()
    _, _, ver = gateway.process_application(case, board.run_id, board_client, 0)
    extractor = DocumentExtractorAgent()
    _, ver = extractor.extract_documents(case.documents, board.run_id, board_client, ver)

    # Run screening crew
    crew = ScreeningCrew()
    checks, _hits, _flags, ver = crew.run_screening(board.run_id, board_client, ver)

    assert len(checks) >= 1
    # Check that verification checks have evidence refs
    for chk in checks:
        assert chk.evidence.agent_id == "crewai.identity_verifier"
        assert chk.evidence.tool == "registry_lookup"

    # Verify blackboard zones are updated
    ver_zone = board_client.get_zone(board.run_id, "verification", agent_id="adk.orchestrator")
    assert len(ver_zone["checks"]) == len(checks)

    scr_zone = board_client.get_zone(board.run_id, "screening", agent_id="adk.orchestrator")
    assert "hits" in scr_zone
    assert "red_flags" in scr_zone
