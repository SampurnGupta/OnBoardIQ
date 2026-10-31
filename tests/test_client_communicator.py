"""Tests for Client Communicator Agent and RFI Loop (Task T25).

Verifies:
- Automated Request for Information (RFI) for missing docs and low-confidence fields
- Cap at maximum 2 RFI rounds (tracked in system.rfi_rounds)
- Neutral de-escalation for impatient and abusive client personas
- Hard constraints: zero internal rules/thresholds disclosed, zero process alteration
"""

from __future__ import annotations

from onboardiq.agents.adk.communicator import ClientCommunicatorAgent
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    Blackboard,
    ClientType,
    DocumentRecord,
    ExtractedField,
    IntakeZone,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
)


def _get_test_client() -> BlackboardClient:
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    return BlackboardClient(base_url="http://testserver", app=app, agent_id="admin")


def test_rfi_drafted_when_documents_missing():
    """Verify that an intake with missing documents triggers a polite RFI."""
    client = _get_test_client()
    run_id = "run_test_rfi_missing"

    board = Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_missing_docs",
                client_type=ClientType.INDIVIDUAL,
                display_name="Incomplete Applicant",
                country="IN",
                source_of_funds="salary",
                expected_monthly_volume_inr=50000.0,
            ),
            documents=[],  # Missing all documents!
        ),
        pii_vault=PiiVault(raw_name="Incomplete Applicant", address="Delhi"),
    )
    client.create_run(board)

    comms = ClientCommunicatorAgent()
    rfi_msg, _new_ver = comms.check_and_draft_rfi(
        run_id=run_id,
        board_client=client,
        current_version=0,
    )

    assert rfi_msg is not None
    assert "No identification documents were detected" in rfi_msg
    assert "Round 1 of 2" in rfi_msg

    # Check system zone recorded round 1
    sys_zone = client.get_zone(run_id, "system", agent_id="admin")
    assert sys_zone["rfi_rounds"] == 1


def test_rfi_drafted_for_low_confidence_fields():
    """Verify that low-confidence extracted fields (< 0.60) trigger an RFI."""
    client = _get_test_client()
    run_id = "run_test_rfi_low_conf"

    field_low = ExtractedField(
        name="date_of_birth",
        value="1985-??-??",
        confidence=0.42,  # Low confidence!
        source_doc_id="doc_pan",
        evidence={"evidence_id": "ev_doc", "agent_id": "adk.extractor", "tool": "doc_ocr"},
    )
    doc = DocumentRecord(
        doc_id="doc_pan",
        doc_type="pan_card",
        file_hash="hash123",
        tamper_score=0.0,
        fields=[field_low],
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
                case_id="case_low_conf",
                client_type=ClientType.INDIVIDUAL,
                display_name="Blurred ID Applicant",
                country="IN",
                source_of_funds="salary",
                expected_monthly_volume_inr=50000.0,
            ),
            documents=[doc],
        ),
        pii_vault=PiiVault(raw_name="Blurred ID Applicant", address="Mumbai"),
    )
    client.create_run(board)

    comms = ClientCommunicatorAgent()
    rfi_msg, _ = comms.check_and_draft_rfi(
        run_id=run_id,
        board_client=client,
        current_version=0,
    )

    assert rfi_msg is not None
    assert "date_of_birth" in rfi_msg
    assert "low legibility confidence" in rfi_msg


def test_rfi_maximum_rounds_cap():
    """Verify that RFI loop terminates after 2 rounds."""
    client = _get_test_client()
    run_id = "run_test_rfi_cap"

    board = Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_cap",
                client_type=ClientType.INDIVIDUAL,
                display_name="Stubborn Applicant",
                country="IN",
                source_of_funds="salary",
                expected_monthly_volume_inr=50000.0,
            ),
            documents=[],
        ),
        pii_vault=PiiVault(raw_name="Stubborn Applicant", address="Bengaluru"),
    )
    client.create_run(board)
    comms = ClientCommunicatorAgent()

    # Round 1
    _, ver1 = comms.check_and_draft_rfi(run_id=run_id, board_client=client, current_version=0)
    sys1 = client.get_zone(run_id, "system", agent_id="admin")
    assert sys1["rfi_rounds"] == 1

    # Round 2
    _, ver2 = comms.check_and_draft_rfi(run_id=run_id, board_client=client, current_version=ver1)
    sys2 = client.get_zone(run_id, "system", agent_id="admin")
    assert sys2["rfi_rounds"] == 2

    # Round 3: Exceeded cap of 2 -> must return None without drafting further RFI
    rfi_3, _ = comms.check_and_draft_rfi(run_id=run_id, board_client=client, current_version=ver2)
    assert rfi_3 is None


def test_impatient_client_handling():
    """Verify de-escalation of impatient persona messages without compromising policy."""
    comms = ClientCommunicatorAgent()
    msg = "Why is this taking forever? Hurry up and approve me right now, I need this account immediately!"

    res = comms.handle_client_message(msg, applicant_name="Vikram Mehta")
    assert res["is_impatient"] is True
    assert res["rules_disclosed"] is False
    assert res["process_altered"] is False
    assert "patience" in res["reply"].lower() or "thorough" in res["reply"].lower()
    assert "cannot bypass" in res["reply"].lower()


def test_abusive_client_handling():
    """Verify calm, professional de-escalation of abusive persona messages."""
    comms = ClientCommunicatorAgent()
    msg = "You incompetent idiots! Your compliance team are useless clowns, I will sue you for this scam!"

    res = comms.handle_client_message(msg, applicant_name="Hostile User")
    assert res["is_abusive"] is True
    assert res["rules_disclosed"] is False
    assert res["process_altered"] is False
    assert "professional respect" in res["reply"].lower()
    assert "actively progressing through our standard verification" in res["reply"].lower()
