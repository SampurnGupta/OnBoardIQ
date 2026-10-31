"""Execution script for Task T08: A2A Integration.

Demonstrates:
- Fetching and inspecting the published A2A Agent Card JSON
- Dispatching remote screening over A2A protocol from ADK Orchestrator
- Verifying the A2A call emits a StepTrace record with step_type="a2a"
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from onboardiq.agents.adk.extractor import DocumentExtractorAgent
from onboardiq.agents.adk.gateway import SecurityGateway
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


def run_t08_a2a_demo(case_id: str = "case_001"):
    print(f"=== Running Task T08: A2A Link Demonstration on {case_id} ===")

    # 1. Fetch and display published Agent Card
    a2a_client = TestClient(a2a_app)
    card_resp = a2a_client.get("/.well-known/agent.json")
    assert card_resp.status_code == 200
    agent_card = card_resp.json()

    print("\n--- Published A2A Agent Card ---")
    print(json.dumps(agent_card, indent=2))

    # 2. Setup in-memory Blackboard
    bb_app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=bb_app)
    a2a_app.state.board_client = board_client

    case_path = ROOT_DIR / "data" / "cases" / f"{case_id}.json"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))

    board = Blackboard(
        run_id=f"run_t08_{case.case_id}",
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

    # 3. Gateway and Extractor
    gateway = SecurityGateway()
    _, _, current_ver = gateway.process_application(case, board.run_id, board_client, current_ver)

    extractor = DocumentExtractorAgent()
    _, current_ver = extractor.extract_documents(case.documents, board.run_id, board_client, current_ver)

    # 4. Invoke CrewAI Screening via A2A
    print("\n--- Dispatching Remote Screening over A2A ---")
    # For in-memory testing we pass dummy transport to use TestClient
    a2a_res, current_ver = invoke_a2a_screening(
        run_id=board.run_id,
        current_version=current_ver,
        board_client=board_client,
        transport=a2a_client,  # type: ignore[arg-type]
    )

    print(f"A2A Call Status: {a2a_res.status}")
    print(f"Checks Performed: {a2a_res.checks_count}")
    print(f"Screening Hits: {a2a_res.hits_count}")
    print(f"Red Flags Raised: {a2a_res.red_flags_count}")
    print(f"New Board Version: {current_ver}")

    # 5. Verify StepTrace was recorded in system zone
    system_zone = board_client.get_zone(board.run_id, "system", agent_id="adk.orchestrator")
    traces = system_zone.get("traces", [])
    assert len(traces) >= 1
    a2a_trace = traces[-1]
    print("\n--- A2A Telemetry StepTrace Verified ---")
    print(f"Trace ID: {a2a_trace.get('trace_id')}")
    print(f"Step Type: {a2a_trace.get('step_type')} (expected 'a2a')")
    print(f"Latency: {a2a_trace.get('latency_ms')} ms")
    print(f"Framework: {a2a_trace.get('framework')}")

    assert a2a_trace.get("step_type") == "a2a"
    print("\n=== T08 A2A Link Succeeded! ===")


if __name__ == "__main__":
    run_t08_a2a_demo("case_001")
