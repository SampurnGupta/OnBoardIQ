"""Execution script for Task T07: CrewAI Screening Crew standalone execution.

Runs:
- Identity Verifier checking mock registry
- Sanctions & PEP Screener classifying hits and generating RedFlags
- Verifies records written to Blackboard verification and screening zones
"""

from __future__ import annotations

from pathlib import Path

from onboardiq.agents.adk.extractor import DocumentExtractorAgent
from onboardiq.agents.adk.gateway import SecurityGateway
from onboardiq.agents.crewai.screening_crew import ScreeningCrew
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


def run_t07_standalone(case_id: str = "case_004"):
    print(f"=== Running T07 Screening Crew on {case_id} ===")

    # 1. Load generated benchmark case
    case_path = ROOT_DIR / "data" / "cases" / f"{case_id}.json"
    assert case_path.exists(), f"Case file {case_path} does not exist"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))
    print(f"Loaded Case: {case.case_id} - {case.declared_name} (Expected: {case.ground_truth.expected_tier.value.upper()})")

    # 2. Setup in-memory Blackboard
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id=f"run_t07_{case.case_id}",
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
    current_ver = 0

    # 3. Gateway & Extractor setup (prerequisites for screening)
    gateway = SecurityGateway()
    _, _, current_ver = gateway.process_application(case, board.run_id, board_client, current_ver)

    extractor = DocumentExtractorAgent()
    _, current_ver = extractor.extract_documents(case.documents, board.run_id, board_client, current_ver)

    # 4. Run CrewAI Screening Crew
    print("\n--- Running Screening Crew ---")
    crew = ScreeningCrew()
    checks, hits, flags, current_ver = crew.run_screening(
        run_id=board.run_id,
        board_client=board_client,
        current_version=current_ver,
    )

    print(f"\nIdentity Checks Recorded: {len(checks)}")
    for chk in checks:
        print(f" - [{chk.check_type}] passed={chk.passed} | {chk.detail}")

    print(f"\nScreening Hits Recorded: {len(hits)}")
    for hit in hits:
        print(f" - [{hit.list_name}] Matched: '{hit.matched_name}' (score={hit.match_score:.2f}, disp={hit.disposition})")
        print(f"   Reasoning: {hit.reasoning}")

    print(f"\nRed Flags Raised: {len(flags)}")
    for flg in flags:
        print(f" - Flag: {flg.flag_type} (sev={flg.severity}, raised_by={flg.raised_by})")

    # 5. Verify Blackboard zones directly
    ver_data = board_client.get_zone(board.run_id, "verification", agent_id="adk.orchestrator")
    scr_data = board_client.get_zone(board.run_id, "screening", agent_id="adk.orchestrator")

    assert len(ver_data.get("checks", [])) == len(checks)
    assert len(scr_data.get("hits", [])) == len(hits)
    print(f"\nAudit Log Events: {len(board_client.get_events(board.run_id))}")
    print("\n=== T07 Screening Crew Succeeded! ===")


if __name__ == "__main__":
    # Test on namesake case
    run_t07_standalone("case_004")
