"""Execution script for Task T06: Gateway + Extractor on a benchmark case.

Demonstrates:
- Gateway splitting raw applicant into PiiVault and MaskedProfile
- Extractor processing documents via OCR and recording DocumentRecord items
- Live Blackboard inspection
"""

from __future__ import annotations

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


def run_t06_pipeline(case_id: str = "case_001"):
    print(f"=== Running T06 Pipeline on {case_id} ===")

    # 1. Load generated benchmark case
    case_path = ROOT_DIR / "data" / "cases" / f"{case_id}.json"
    assert case_path.exists(), f"Case file {case_path} does not exist"
    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))
    print(f"Loaded applicant: {case.declared_name} ({case.client_type.value})")

    # 2. Setup Blackboard in-memory for testing
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    # Initialize empty run blackboard
    initial_board = Blackboard(
        run_id=f"run_t06_{case.case_id}",
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
        pii_vault=PiiVault(
            raw_name=case.declared_name,
            address=case.declared_address,
        ),
    )
    board_client.create_run(initial_board)
    current_ver = 0

    # 3. Security Gateway: Split PII & Mask Profile
    print("\n--- Step 1: Security Gateway ---")
    gateway = SecurityGateway(agent_id="adk.gateway")
    masked_profile, pii_vault, current_ver = gateway.process_application(
        case=case,
        run_id=initial_board.run_id,
        board_client=board_client,
        current_version=current_ver,
    )
    print(f"Gateway Masked Profile: display_name='{masked_profile.display_name}', age_band={masked_profile.age_band}")
    print(f"PII Vault created: raw_name='{pii_vault.raw_name}', address='{pii_vault.address}'")

    # 4. Document Extractor: Extract OCR fields with EvidenceRef
    print("\n--- Step 2: Document Extractor Agent ---")
    extractor = DocumentExtractorAgent(agent_id="adk.extractor")
    doc_records, current_ver = extractor.extract_documents(
        doc_paths=case.documents,
        run_id=initial_board.run_id,
        board_client=board_client,
        current_version=current_ver,
    )
    print(f"Extracted {len(doc_records)} documents:")
    for doc in doc_records:
        print(f" - [{doc.doc_type}] doc_id={doc.doc_id}: {len(doc.fields)} fields extracted")
        for f in doc.fields:
            print(f"     {f.name}: {f.value} (conf={f.confidence:.2f}, ev={f.evidence.evidence_id[:8]}...)")

    # 5. Read and inspect final Blackboard state
    print("\n--- Final Blackboard Zones ---")
    intake_data = board_client.get_zone(initial_board.run_id, "intake", agent_id="adk.orchestrator")
    system_data = board_client.get_zone(initial_board.run_id, "system", agent_id="adk.orchestrator")
    events = board_client.get_events(initial_board.run_id)

    print(f"Current Version: {current_ver}")
    print(f"Total Audit Events: {len(events)}")
    print(f"System Guardrail Events: {len(system_data.get('guardrail_events', []))}")
    print(f"Intake Documents Registered: {len(intake_data.get('documents', []))}")
    print("\n=== T06 Pipeline Succeeded! ===")


if __name__ == "__main__":
    run_t06_pipeline("case_001")
