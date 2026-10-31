"""Synthetic dataset generator for OnboardIQ evaluation cases.

Generates 10 labelled benchmark cases (6 individuals, 4 companies) with:
- Case JSON files validating strictly as LabelledCase
- Synthetic rendered document images (PAN, Address Proof, Incorporation Cert)
- Mock government/identity registry SQLite database (data/registry.db)
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from onboardiq.schema import ClientType, Decision, GroundTruth, LabelledCase, RiskTier

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
CASES_DIR = DATA_DIR / "cases"
DOCS_DIR = DATA_DIR / "docs"
REGISTRY_DB_PATH = DATA_DIR / "registry.db"


def init_registry_db(db_path: Path) -> sqlite3.Connection:
    """Initialize mock identity and company registry SQLite DB."""
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE registry_records (
                id_number TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                dob TEXT,
                address TEXT NOT NULL,
                country TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
    return conn


def render_document_image(
    output_path: Path,
    doc_title: str,
    fields: dict[str, str],
    width: int = 600,
    height: int = 380,
) -> None:
    """Render a clean synthetic document image with Pillow for OCR processing."""
    image = Image.new("RGB", (width, height), color=(252, 252, 252))
    draw = ImageDraw.Draw(image)

    # Decorative header & border
    draw.rectangle([(10, 10), (width - 10, height - 10)], outline=(40, 60, 100), width=3)
    draw.rectangle([(12, 12), (width - 12, 50)], fill=(40, 60, 100))

    # Basic default font
    font = ImageFont.load_default()

    draw.text((25, 22), f"GOVERNMENT OF SYNTHETICA - {doc_title.upper()}", fill=(255, 255, 255), font=font)

    y_offset = 75
    for key, value in fields.items():
        label = f"{key.replace('_', ' ').title()}:"
        draw.text((35, y_offset), label, fill=(30, 30, 30), font=font)
        draw.text((180, y_offset), str(value), fill=(10, 10, 10), font=font)
        y_offset += 32

    # Verification watermark
    draw.text((35, height - 35), "[OFFICIAL SYNTHETIC VERIFICATION COPY - NOT REAL PII]", fill=(150, 150, 150), font=font)

    image.save(output_path, "PNG")


def generate_all_cases() -> list[LabelledCase]:
    """Generate deterministic benchmark cases with seed=42."""
    random.seed(42)
    Faker.seed(42)

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    reg_conn = init_registry_db(REGISTRY_DB_PATH)

    cases: list[LabelledCase] = []

    # Helper to insert into registry
    def insert_registry(id_num: str, name: str, dob: str, addr: str, country: str = "IN", status: str = "ACTIVE"):
        with reg_conn:
            reg_conn.execute(
                """
                INSERT OR REPLACE INTO registry_records (id_number, full_name, dob, address, country, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (id_num, name, dob, addr, country, status),
            )

    # -------------------------------------------------------------
    # Case 001: Individual, Clean (Baseline Approve)
    # -------------------------------------------------------------
    c001_id = "case_001"
    c001_name = "Priya Rajesh Sharma"
    c001_dob = "1991-04-14"
    c001_pan = "ABCPS1001A"
    c001_addr = "Flat 402, Lotus Residency, Powai, Mumbai 400076"
    render_document_image(
        DOCS_DIR / f"{c001_id}_pan.png",
        "Permanent Account Number (PAN) Card",
        {"Full_Name": c001_name, "DOB": c001_dob, "PAN": c001_pan, "Father_Name": "Rajesh Sharma"},
    )
    render_document_image(
        DOCS_DIR / f"{c001_id}_address.png",
        "Utility Bill - Address Proof",
        {"Consumer_Name": c001_name, "Billing_Address": c001_addr, "Bill_Date": "2026-09-15"},
    )
    insert_registry(c001_pan, c001_name, c001_dob, c001_addr)
    cases.append(
        LabelledCase(
            case_id=c001_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c001_name,
            declared_dob=c001_dob,
            declared_country="IN",
            declared_address=c001_addr,
            declared_source_of_funds="technology_consulting_salary",
            expected_monthly_volume_inr=150000.0,
            documents=[f"data/docs/{c001_id}_pan.png", f"data/docs/{c001_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 002: Individual, Clean (Retail Trader)
    # -------------------------------------------------------------
    c002_id = "case_002"
    c002_name = "Arun Kumar Patel"
    c002_dob = "1987-11-23"
    c002_pan = "ABCPK2002B"
    c002_addr = "12 Green Park Society, Ellis Bridge, Ahmedabad 380006"
    render_document_image(
        DOCS_DIR / f"{c002_id}_pan.png",
        "PAN Card",
        {"Full_Name": c002_name, "DOB": c002_dob, "PAN": c002_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c002_id}_address.png",
        "Electricity Bill",
        {"Full_Name": c002_name, "Address": c002_addr},
    )
    insert_registry(c002_pan, c002_name, c002_dob, c002_addr)
    cases.append(
        LabelledCase(
            case_id=c002_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c002_name,
            declared_dob=c002_dob,
            declared_country="IN",
            declared_address=c002_addr,
            declared_source_of_funds="retail_textile_business",
            expected_monthly_volume_inr=80000.0,
            documents=[f"data/docs/{c002_id}_pan.png", f"data/docs/{c002_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 003: Individual, Clean (Medical Professional)
    # -------------------------------------------------------------
    c003_id = "case_003"
    c003_name = "Dr. Ananya S. Iyer"
    c003_dob = "1983-08-05"
    c003_pan = "ABCAI3003C"
    c003_addr = "34 Temple Rock Road, Indiranagar, Bengaluru 560038"
    render_document_image(
        DOCS_DIR / f"{c003_id}_pan.png",
        "PAN Card",
        {"Full_Name": c003_name, "DOB": c003_dob, "PAN": c003_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c003_id}_address.png",
        "Bank Account Statement",
        {"Full_Name": c003_name, "Address": c003_addr},
    )
    insert_registry(c003_pan, c003_name, c003_dob, c003_addr)
    cases.append(
        LabelledCase(
            case_id=c003_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c003_name,
            declared_dob=c003_dob,
            declared_country="IN",
            declared_address=c003_addr,
            declared_source_of_funds="healthcare_professional_income",
            expected_monthly_volume_inr=220000.0,
            documents=[f"data/docs/{c003_id}_pan.png", f"data/docs/{c003_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 004: Individual, Namesake False Positive (Similar to "Viktor Darkovich")
    # -------------------------------------------------------------
    c004_id = "case_004"
    c004_name = "Victor Darko"
    c004_dob = "1994-02-18"
    c004_pass = "P987654321"
    c004_addr = "14 Marine Lines, Colaba, Mumbai 400005"
    render_document_image(
        DOCS_DIR / f"{c004_id}_passport.png",
        "Passport Identification Page",
        {"Full_Name": c004_name, "DOB": c004_dob, "Passport_Number": c004_pass, "Nationality": "IN"},
    )
    render_document_image(
        DOCS_DIR / f"{c004_id}_address.png",
        "Rental Lease Agreement",
        {"Tenant_Name": c004_name, "Address": c004_addr},
    )
    insert_registry(c004_pass, c004_name, c004_dob, c004_addr)
    cases.append(
        LabelledCase(
            case_id=c004_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c004_name,
            declared_dob=c004_dob,
            declared_country="IN",
            declared_address=c004_addr,
            declared_source_of_funds="software_contracting",
            expected_monthly_volume_inr=95000.0,
            documents=[f"data/docs/{c004_id}_passport.png", f"data/docs/{c004_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=True,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 005: Individual, Namesake False Positive (Similar to PEP "Sanjay K. Verma")
    # -------------------------------------------------------------
    c005_id = "case_005"
    c005_name = "Sanjay V. Verma"
    c005_dob = "1978-06-12"
    c005_pan = "ABCSV5005E"
    c005_addr = "88 Sector 15, Chandigarh 160015"
    render_document_image(
        DOCS_DIR / f"{c005_id}_pan.png",
        "PAN Card",
        {"Full_Name": c005_name, "DOB": c005_dob, "PAN": c005_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c005_id}_address.png",
        "Water Supply Bill",
        {"Consumer_Name": c005_name, "Address": c005_addr},
    )
    insert_registry(c005_pan, c005_name, c005_dob, c005_addr)
    cases.append(
        LabelledCase(
            case_id=c005_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c005_name,
            declared_dob=c005_dob,
            declared_country="IN",
            declared_address=c005_addr,
            declared_source_of_funds="civil_engineering_practice",
            expected_monthly_volume_inr=110000.0,
            documents=[f"data/docs/{c005_id}_pan.png", f"data/docs/{c005_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=True,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 006: Individual, Identity Mismatch (Tampered / Mismatched DOB)
    # -------------------------------------------------------------
    c006_id = "case_006"
    c006_declared_name = "Rohan Mehra"
    c006_declared_dob = "1992-05-10"
    c006_pan = "ABCMR6006F"
    c006_addr = "74 Ring Road, Lajpat Nagar, New Delhi 110024"
    # Document has altered DOB 1982-11-20
    render_document_image(
        DOCS_DIR / f"{c006_id}_pan.png",
        "PAN Card",
        {"Full_Name": c006_declared_name, "DOB": "1982-11-20", "PAN": c006_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c006_id}_address.png",
        "Aadhaar Letter Masked Copy",
        {"Full_Name": c006_declared_name, "DOB": "1982-11-20", "Address": c006_addr},
    )
    # Registry has the official record (1982-11-20), conflicting with declared 1992-05-10
    insert_registry(c006_pan, c006_declared_name, "1982-11-20", c006_addr)
    cases.append(
        LabelledCase(
            case_id=c006_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c006_declared_name,
            declared_dob=c006_declared_dob,
            declared_country="IN",
            declared_address=c006_addr,
            declared_source_of_funds="freelance_marketing",
            expected_monthly_volume_inr=50000.0,
            documents=[f"data/docs/{c006_id}_pan.png", f"data/docs/{c006_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["identity_mismatch"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 007: Company, Clean (Apex Global Logistics Pvt Ltd)
    # -------------------------------------------------------------
    c007_id = "case_007"
    c007_name = "Apex Global Logistics Pvt Ltd"
    c007_cin = "U63090MH2021PTC123456"
    c007_addr = "Floor 5, Trade World B, BKC, Mumbai 400051"
    render_document_image(
        DOCS_DIR / f"{c007_id}_incorporation.png",
        "Certificate of Incorporation",
        {"Company_Name": c007_name, "CIN": c007_cin, "Registered_Office": c007_addr, "Date": "2021-03-15"},
    )
    insert_registry(c007_cin, c007_name, "2021-03-15", c007_addr, status="ACTIVE_COMPANY")
    c007_chart = {
        "entity": c007_name,
        "owners": [
            {"name": "Manoj Deshmukh", "pct": 60.0, "path": [c007_name, "Manoj Deshmukh"]},
            {"name": "Sneha Deshmukh", "pct": 40.0, "path": [c007_name, "Sneha Deshmukh"]},
        ],
    }
    cases.append(
        LabelledCase(
            case_id=c007_id,
            client_type=ClientType.COMPANY,
            declared_name=c007_name,
            declared_country="IN",
            declared_address=c007_addr,
            declared_source_of_funds="logistics_operations_revenue",
            expected_monthly_volume_inr=2500000.0,
            documents=[f"data/docs/{c007_id}_incorporation.png"],
            ownership_chart=c007_chart,
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 008: Company, Sanctions Near-Match Beneficial Owner
    # -------------------------------------------------------------
    c008_id = "case_008"
    c008_name = "Nordic Import Export LLP"
    c008_cin = "LLPIN-AAH-7788"
    c008_addr = "Suite 201, Regus Centre, DLF Cyber City, Gurugram 122002"
    render_document_image(
        DOCS_DIR / f"{c008_id}_incorporation.png",
        "LLP Registration Certificate",
        {"LLP_Name": c008_name, "Registration_No": c008_cin, "Address": c008_addr},
    )
    insert_registry(c008_cin, c008_name, "2023-01-10", c008_addr, status="ACTIVE_LLP")
    # Owner Viktor Darkovich is on OFAC_SDN sanctions list!
    c008_chart = {
        "entity": c008_name,
        "owners": [
            {"name": "Viktor Darkovich", "pct": 45.0, "path": [c008_name, "Viktor Darkovich"]},
            {"name": "Kavita Rao", "pct": 55.0, "path": [c008_name, "Kavita Rao"]},
        ],
    }
    cases.append(
        LabelledCase(
            case_id=c008_id,
            client_type=ClientType.COMPANY,
            declared_name=c008_name,
            declared_country="IN",
            declared_address=c008_addr,
            declared_source_of_funds="cross_border_commodity_trading",
            expected_monthly_volume_inr=8000000.0,
            documents=[f"data/docs/{c008_id}_incorporation.png"],
            ownership_chart=c008_chart,
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["sanctions_hit"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 009: Company, Opaque Ownership (Offshore Multi-tier)
    # -------------------------------------------------------------
    c009_id = "case_009"
    c009_name = "Horizon Holdings International Pvt Ltd"
    c009_cin = "U74999DL2022PTC998877"
    c009_addr = "11 Barakhamba Road, Connaught Place, New Delhi 110001"
    render_document_image(
        DOCS_DIR / f"{c009_id}_incorporation.png",
        "Certificate of Incorporation",
        {"Company_Name": c009_name, "CIN": c009_cin, "Address": c009_addr},
    )
    insert_registry(c009_cin, c009_name, "2022-07-22", c009_addr, status="ACTIVE_COMPANY")
    # Ownership ends at an offshore shell without identifiable ultimate individual
    c009_chart = {
        "entity": c009_name,
        "owners": [
            {
                "name": "BVI Shadow Investment Trust",
                "pct": 85.0,
                "path": [c009_name, "Panama Alpha S.A.", "BVI Shadow Investment Trust"],
            },
            {"name": "Local Nominee Director", "pct": 15.0, "path": [c009_name, "Local Nominee Director"]},
        ],
    }
    cases.append(
        LabelledCase(
            case_id=c009_id,
            client_type=ClientType.COMPANY,
            declared_name=c009_name,
            declared_country="IN",
            declared_address=c009_addr,
            declared_source_of_funds="international_investment_returns",
            expected_monthly_volume_inr=5000000.0,
            documents=[f"data/docs/{c009_id}_incorporation.png"],
            ownership_chart=c009_chart,
            ground_truth=GroundTruth(
                expected_tier=RiskTier.MEDIUM,
                expected_decision=Decision.APPROVE_EDD,
                planted_flags=["opaque_ownership"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 010: Company, Multi-Flag High Risk (Sanctions + Adverse Media)
    # -------------------------------------------------------------
    c010_id = "case_010"
    c010_name = "Bosphorus Maritime Trading Corp"
    c010_cin = "U35110MH2020PTC445566"
    c010_addr = "Pier 4, Ballard Estate, Fort, Mumbai 400001"
    render_document_image(
        DOCS_DIR / f"{c010_id}_incorporation.png",
        "Maritime Transport Registration Certificate",
        {"Company_Name": c010_name, "CIN": c010_cin, "Address": c010_addr},
    )
    insert_registry(c010_cin, c010_name, "2020-10-05", c010_addr, status="FLAGGED_INVESTIGATION")
    c010_chart = {
        "entity": c010_name,
        "owners": [
            {"name": "Hassan Al-Fraudini", "pct": 70.0, "path": [c010_name, "Hassan Al-Fraudini"]},
            {"name": "Ali Reza", "pct": 30.0, "path": [c010_name, "Ali Reza"]},
        ],
    }
    cases.append(
        LabelledCase(
            case_id=c010_id,
            client_type=ClientType.COMPANY,
            declared_name=c010_name,
            declared_country="IN",
            declared_address=c010_addr,
            declared_source_of_funds="maritime_charter_revenue",
            expected_monthly_volume_inr=12000000.0,
            documents=[f"data/docs/{c010_id}_incorporation.png"],
            ownership_chart=c010_chart,
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["sanctions_hit", "adverse_media"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # Write all JSON files
    for c in cases:
        case_file = CASES_DIR / f"{c.case_id}.json"
        case_file.write_text(c.model_dump_json(indent=2), encoding="utf-8")

    reg_conn.close()
    return cases


if __name__ == "__main__":
    generated = generate_all_cases()
    print(f"Successfully generated {len(generated)} benchmark cases in {CASES_DIR}")
    for c in generated:
        print(f" - {c.case_id}: {c.declared_name} ({c.client_type.value}) -> {c.ground_truth.expected_tier.value.upper()} | flags: {c.ground_truth.planted_flags}")
