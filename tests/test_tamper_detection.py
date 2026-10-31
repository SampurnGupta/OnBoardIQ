"""Tests for Document Tamper Detection, Cross-Document Consistency, and Forger Persona (Task T26).

Verifies:
- doc_ocr computing low tamper score on authentic documents and high tamper score on tampered ones
- Precision and recall calculation on sample generated documents
- IdentityVerifier raising doc_tampering red flag on tamper_score >= 0.40
- IdentityVerifier cross-document consistency check raising identity_mismatch on field discrepancies
"""

from __future__ import annotations

from pathlib import Path

from onboardiq.agents.crewai.screening_crew import IdentityVerifierAgent
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.eval.dataset_gen import render_document_image
from onboardiq.mcp_server.tools.doc_ocr import extract_doc_ocr
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


def test_clean_vs_tampered_document_ocr(tmp_path: Path):
    """Verify clean document has low tamper score and forged document has high tamper score."""
    clean_path = tmp_path / "case_test_clean_pan.png"
    tampered_path = tmp_path / "case_test_tampered_pan.png"

    # Render clean document
    render_document_image(
        clean_path,
        "PAN Card",
        {"Full_Name": "Authentic User", "DOB": "1990-01-01", "PAN": "ABCDE1234F"},
        tampered=False,
    )

    # Render tampered document
    render_document_image(
        tampered_path,
        "PAN Card",
        {"Full_Name": "Forged User", "DOB": "1990-01-01", "PAN": "ABCDE1234F"},
        tampered=True,
    )

    clean_ocr = extract_doc_ocr(str(clean_path))
    tampered_ocr = extract_doc_ocr(str(tampered_path))

    assert clean_ocr.tamper_score < 0.20
    assert tampered_ocr.tamper_score >= 0.70


def test_tamper_detection_precision_and_recall(tmp_path: Path):
    """Compute precision and recall on a synthetic sample of 6 clean and 4 tampered documents."""
    y_true: list[int] = []
    y_pred: list[int] = []

    # Generate 6 clean docs
    for i in range(6):
        p = tmp_path / f"doc_clean_{i}.png"
        render_document_image(p, "ID Card", {"Name": f"User {i}", "ID": f"ID{i}"}, tampered=False)
        ocr = extract_doc_ocr(str(p))
        y_true.append(0)
        y_pred.append(1 if ocr.tamper_score >= 0.40 else 0)

    # Generate 4 tampered docs
    for i in range(4):
        p = tmp_path / f"doc_tampered_{i}.png"
        render_document_image(p, "ID Card", {"Name": f"Forged {i}", "ID": f"FORGE{i}"}, tampered=True)
        ocr = extract_doc_ocr(str(p))
        y_true.append(1)
        y_pred.append(1 if ocr.tamper_score >= 0.40 else 0)

    # Calculate metrics
    tp = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred, strict=False) if yt == 1 and yp == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    assert precision == 1.0
    assert recall == 1.0


def test_identity_verifier_raises_doc_tampering_red_flag():
    """Verify that IdentityVerifier flags a document with tamper_score >= 0.40 with doc_tampering."""
    client = _get_test_client()
    run_id = "run_test_tamper_flag"

    doc = DocumentRecord(
        doc_id="doc_forged_pan",
        doc_type="pan_card",
        file_hash="hash_forged",
        tamper_score=0.88,  # High tamper score!
        fields=[
            ExtractedField(
                name="full_name",
                value="Forged Identity",
                confidence=0.90,
                source_doc_id="doc_forged_pan",
                evidence={"evidence_id": "ev1", "agent_id": "adk.extractor", "tool": "doc_ocr"},
            )
        ],
    )

    board = Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.FORGER,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_forger",
                client_type=ClientType.INDIVIDUAL,
                display_name="Forged Identity",
                country="IN",
                source_of_funds="trade",
                expected_monthly_volume_inr=50000.0,
            ),
            documents=[doc],
        ),
        pii_vault=PiiVault(raw_name="Forged Identity", address="Mumbai"),
    )
    client.create_run(board)

    verifier = IdentityVerifierAgent()
    _checks, red_flags, _ = verifier.verify_identity(
        run_id=run_id,
        board_client=client,
        current_version=0,
    )

    # Must raise doc_tampering red flag
    tamper_flags = [rf for rf in red_flags if rf.flag_type == "doc_tampering"]
    assert len(tamper_flags) >= 1
    assert tamper_flags[0].severity == "high"


def test_identity_verifier_cross_document_discrepancy():
    """Verify that cross-document name mismatch raises identity_mismatch red flag."""
    client = _get_test_client()
    run_id = "run_test_cross_doc_mismatch"

    # Document 1: PAN Card with name 'Rohan Mehra'
    doc1 = DocumentRecord(
        doc_id="doc_pan",
        doc_type="pan_card",
        file_hash="hash1",
        tamper_score=0.05,
        fields=[
            ExtractedField(
                name="full_name",
                value="Rohan Mehra",
                confidence=0.95,
                source_doc_id="doc_pan",
                evidence={"evidence_id": "ev1", "agent_id": "adk.extractor", "tool": "doc_ocr"},
            )
        ],
    )

    # Document 2: Address Proof with completely different name 'Sunil Verma'
    doc2 = DocumentRecord(
        doc_id="doc_address",
        doc_type="address_proof",
        file_hash="hash2",
        tamper_score=0.05,
        fields=[
            ExtractedField(
                name="consumer_name",
                value="Sunil Verma",  # Mismatch!
                confidence=0.95,
                source_doc_id="doc_address",
                evidence={"evidence_id": "ev2", "agent_id": "adk.extractor", "tool": "doc_ocr"},
            )
        ],
    )

    board = Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.FORGER,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_mismatch",
                client_type=ClientType.INDIVIDUAL,
                display_name="Rohan Mehra",
                country="IN",
                source_of_funds="salary",
                expected_monthly_volume_inr=50000.0,
            ),
            documents=[doc1, doc2],
        ),
        pii_vault=PiiVault(raw_name="Rohan Mehra", address="Mumbai"),
    )
    client.create_run(board)

    verifier = IdentityVerifierAgent()
    checks, red_flags, _ = verifier.verify_identity(
        run_id=run_id,
        board_client=client,
        current_version=0,
    )

    # Must contain a cross_document check that failed
    cross_checks = [c for c in checks if c.check_type == "cross_document" and not c.passed]
    assert len(cross_checks) >= 1

    # Must raise identity_mismatch red flag
    mismatch_flags = [rf for rf in red_flags if rf.flag_type == "identity_mismatch"]
    assert len(mismatch_flags) >= 1
