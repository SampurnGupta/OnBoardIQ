"""Acceptance tests for T04: Synthetic Data Generator.

Verifies:
- All generated case files parse strictly as LabelledCase
- All referenced document images exist and can be opened
- Registry database contains records for clean cases
- Reference sanctions and PEP lists are well-formed
"""

import csv
import sqlite3
from pathlib import Path

from PIL import Image

from onboardiq.eval.dataset_gen import CASES_DIR, DATA_DIR, REGISTRY_DB_PATH
from onboardiq.schema import ClientType, LabelledCase, RiskTier


def test_ten_cases_exist_and_validate():
    case_files = sorted(CASES_DIR.glob("case_*.json"))
    assert len(case_files) == 10, f"Expected 10 case files, found {len(case_files)}"

    individual_count = 0
    company_count = 0

    for cf in case_files:
        content = cf.read_text(encoding="utf-8")
        case = LabelledCase.model_validate_json(content)
        assert case.case_id == cf.stem
        assert case.expected_monthly_volume_inr >= 0
        assert case.ground_truth.expected_tier in (RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH)

        if case.client_type == ClientType.INDIVIDUAL:
            individual_count += 1
        elif case.client_type == ClientType.COMPANY:
            company_count += 1
            assert case.ownership_chart is not None

    assert individual_count == 6
    assert company_count == 4


def test_all_referenced_documents_exist_and_open():
    case_files = sorted(CASES_DIR.glob("case_*.json"))
    root_dir = Path(__file__).resolve().parents[1]

    for cf in case_files:
        case = LabelledCase.model_validate_json(cf.read_text(encoding="utf-8"))
        assert len(case.documents) >= 1
        for doc_rel_path in case.documents:
            doc_file = root_dir / doc_rel_path
            assert doc_file.exists(), f"Document {doc_rel_path} does not exist"

            # Verify image can be opened and has positive dimensions
            with Image.open(doc_file) as img:
                assert img.width > 0
                assert img.height > 0


def test_registry_database_contains_clean_cases():
    assert REGISTRY_DB_PATH.exists()
    conn = sqlite3.connect(REGISTRY_DB_PATH)
    with conn:
        cursor = conn.execute("SELECT COUNT(*) FROM registry_records")
        count = cursor.fetchone()[0]
        assert count >= 6  # Records for individuals & companies

        # Verify clean case_001 is registered
        c001_cursor = conn.execute(
            "SELECT full_name, status FROM registry_records WHERE id_number = 'ABCPS1001A'"
        )
        row = c001_cursor.fetchone()
        assert row is not None
        assert row[0] == "Priya Rajesh Sharma"
        assert row[1] == "ACTIVE"


def test_sample_sanctions_and_pep_lists():
    sanctions_file = DATA_DIR / "lists" / "sanctions_sample.csv"
    assert sanctions_file.exists()
    with sanctions_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) >= 5
        assert "entry_name" in rows[0]
        assert "list_name" in rows[0]

    pep_file = DATA_DIR / "lists" / "pep_sample.csv"
    assert pep_file.exists()
    with pep_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        pep_rows = list(reader)
        assert len(pep_rows) >= 3
        assert "position" in pep_rows[0]

