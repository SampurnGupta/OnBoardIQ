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
from typing import Any

from faker import Faker
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

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
    tampered: bool = False,
) -> None:
    """Render a clean or tampered synthetic document image with Pillow for OCR processing."""
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

    if tampered:
        # Simulate physical forgery / digital splice
        patch_y = 105
        draw.rectangle([(175, patch_y), (360, patch_y + 26)], fill=(232, 235, 245), outline=(200, 40, 40), width=1)
        draw.text((180, patch_y + 6), "[ALTERED_ENTRY]", fill=(220, 20, 20), font=font)

        meta = PngImagePlugin.PngInfo()
        meta.add_text("Tampered", "True")
        meta.add_text("Software", "GNU Image Manipulation Program (Tampered)")
        image.save(output_path, "PNG", pnginfo=meta)
    else:
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

    # -------------------------------------------------------------
    # Case 011: Individual, Clean (Senior Architect)
    # -------------------------------------------------------------
    c011_id = "case_011"
    c011_name = "Sunita Narain Rao"
    c011_dob = "1985-06-18"
    c011_pan = "ABCSR1011K"
    c011_addr = "704 Skyline Towers, Indiranagar, Bengaluru 560038"
    render_document_image(
        DOCS_DIR / f"{c011_id}_pan.png",
        "Permanent Account Number Card",
        {"Full_Name": c011_name, "DOB": c011_dob, "PAN": c011_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c011_id}_address.png",
        "Electricity Bill",
        {"Consumer_Name": c011_name, "Billing_Address": c011_addr, "Bill_Date": "2026-08-10"},
    )
    insert_registry(c011_pan, c011_name, c011_dob, c011_addr)
    cases.append(
        LabelledCase(
            case_id=c011_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c011_name,
            declared_dob=c011_dob,
            declared_country="IN",
            declared_address=c011_addr,
            declared_source_of_funds="architectural_consulting_fees",
            expected_monthly_volume_inr=120000.0,
            documents=[f"data/docs/{c011_id}_pan.png", f"data/docs/{c011_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 012: Individual, Clean (Chartered Accountant)
    # -------------------------------------------------------------
    c012_id = "case_012"
    c012_name = "Rohan Vikram Deshmukh"
    c012_dob = "1982-12-04"
    c012_pan = "ABCRD1012L"
    c012_addr = "15/B Mayur Colony, Kothrud, Pune 411038"
    render_document_image(
        DOCS_DIR / f"{c012_id}_pan.png",
        "PAN Card",
        {"Full_Name": c012_name, "DOB": c012_dob, "PAN": c012_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c012_id}_address.png",
        "Bank Account Statement",
        {"Account_Holder": c012_name, "Address": c012_addr, "Statement_Date": "2026-09-01"},
    )
    insert_registry(c012_pan, c012_name, c012_dob, c012_addr)
    cases.append(
        LabelledCase(
            case_id=c012_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c012_name,
            declared_dob=c012_dob,
            declared_country="IN",
            declared_address=c012_addr,
            declared_source_of_funds="accounting_and_audit_practice",
            expected_monthly_volume_inr=250000.0,
            documents=[f"data/docs/{c012_id}_pan.png", f"data/docs/{c012_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 013: Individual, Clean (High School Principal)
    # -------------------------------------------------------------
    c013_id = "case_013"
    c013_name = "Kavita Mehra"
    c013_dob = "1978-03-29"
    c013_pan = "ABCKM1013M"
    c013_addr = "House 88, Sector 14, Chandigarh 160014"
    render_document_image(
        DOCS_DIR / f"{c013_id}_pan.png",
        "PAN Card",
        {"Full_Name": c013_name, "DOB": c013_dob, "PAN": c013_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c013_id}_address.png",
        "Water Supply Bill",
        {"Consumer_Name": c013_name, "Address": c013_addr, "Date": "2026-07-20"},
    )
    insert_registry(c013_pan, c013_name, c013_dob, c013_addr)
    cases.append(
        LabelledCase(
            case_id=c013_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c013_name,
            declared_dob=c013_dob,
            declared_country="IN",
            declared_address=c013_addr,
            declared_source_of_funds="education_sector_salary",
            expected_monthly_volume_inr=90000.0,
            documents=[f"data/docs/{c013_id}_pan.png", f"data/docs/{c013_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 014: Individual, Namesake False Positive (Vladimir A. Petrov)
    # -------------------------------------------------------------
    c014_id = "case_014"
    c014_name = "Vladimir A. Petrov"
    c014_dob = "1995-10-12"
    c014_pan = "ABCVP1014N"
    c014_addr = "Flat 301, Palm Grove, Whitefield, Bengaluru 560066"
    render_document_image(
        DOCS_DIR / f"{c014_id}_pan.png",
        "PAN Card",
        {"Full_Name": c014_name, "DOB": c014_dob, "PAN": c014_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c014_id}_address.png",
        "Rental Agreement Proof",
        {"Tenant_Name": c014_name, "Address": c014_addr, "Agreement_Date": "2026-01-15"},
    )
    insert_registry(c014_pan, c014_name, c014_dob, c014_addr)
    cases.append(
        LabelledCase(
            case_id=c014_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c014_name,
            declared_dob=c014_dob,
            declared_country="IN",
            declared_address=c014_addr,
            declared_source_of_funds="software_engineering_employment",
            expected_monthly_volume_inr=180000.0,
            documents=[f"data/docs/{c014_id}_pan.png", f"data/docs/{c014_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
                is_namesake_false_positive=True,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 015: Individual, Planted Single Flag: doc_tampering (Tanya Sen)
    # -------------------------------------------------------------
    c015_id = "case_015"
    c015_name = "Tanya Sen"
    c015_dob = "1993-07-22"
    c015_pan = "ABCTS1015P"
    c015_addr = "32 Salt Lake Sector V, Kolkata 700091"
    render_document_image(
        DOCS_DIR / f"{c015_id}_pan.png",
        "PAN Card",
        {"Full_Name": c015_name, "DOB": c015_dob, "PAN": c015_pan},
    )
    render_document_image(
        DOCS_DIR / f"{c015_id}_address.png",
        "Utility Statement",
        {"Customer": c015_name, "Address": c015_addr},
        tampered=True,
    )
    insert_registry(c015_pan, c015_name, c015_dob, c015_addr)
    cases.append(
        LabelledCase(
            case_id=c015_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c015_name,
            declared_dob=c015_dob,
            declared_country="IN",
            declared_address=c015_addr,
            declared_source_of_funds="freelance_content_marketing",
            expected_monthly_volume_inr=75000.0,
            documents=[f"data/docs/{c015_id}_pan.png", f"data/docs/{c015_id}_address.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["doc_tampering"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 016: Individual, Planted Single Flag: sanctions_hit (Slobodan Milosevic)
    # -------------------------------------------------------------
    c016_id = "case_016"
    c016_name = "Slobodan Milosevic"
    c016_dob = "1960-08-20"
    c016_pan = "ABCSM1016Q"
    c016_addr = "12 Danube Embankment, Belgrade, Serbia"
    render_document_image(
        DOCS_DIR / f"{c016_id}_pan.png",
        "National Passport & Tax ID",
        {"Full_Name": c016_name, "DOB": c016_dob, "ID": c016_pan},
    )
    insert_registry(c016_pan, c016_name, c016_dob, c016_addr, country="RS", status="BLOCKED")
    cases.append(
        LabelledCase(
            case_id=c016_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c016_name,
            declared_dob=c016_dob,
            declared_country="RS",
            declared_address=c016_addr,
            declared_source_of_funds="sovereign_wealth_investments",
            expected_monthly_volume_inr=5000000.0,
            documents=[f"data/docs/{c016_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["sanctions_hit"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 017: Individual, Planted Single Flag: pep (Marcus Vance)
    # -------------------------------------------------------------
    c017_id = "case_017"
    c017_name = "Marcus Vance"
    c017_dob = "1968-11-14"
    c017_pan = "ABCMV1017R"
    c017_addr = "450 Capitol Way, Washington DC 20001"
    render_document_image(
        DOCS_DIR / f"{c017_id}_pan.png",
        "Diplomatic / Congressional Identity Card",
        {"Full_Name": c017_name, "DOB": c017_dob, "Designation": "Senator", "ID": c017_pan},
    )
    insert_registry(c017_pan, c017_name, c017_dob, c017_addr, country="US")
    cases.append(
        LabelledCase(
            case_id=c017_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c017_name,
            declared_dob=c017_dob,
            declared_country="US",
            declared_address=c017_addr,
            declared_source_of_funds="public_service_and_book_royalties",
            expected_monthly_volume_inr=750000.0,
            documents=[f"data/docs/{c017_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.MEDIUM,
                expected_decision=Decision.APPROVE_EDD,
                planted_flags=["pep"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 018: Individual, Planted Single Flag: adverse_media (Deepak Singhania)
    # -------------------------------------------------------------
    c018_id = "case_018"
    c018_name = "Deepak Singhania"
    c018_dob = "1974-05-11"
    c018_pan = "ABCDS1018S"
    c018_addr = "Villa 12, Barakhamba Road, New Delhi 110001"
    render_document_image(
        DOCS_DIR / f"{c018_id}_pan.png",
        "PAN Card",
        {"Full_Name": c018_name, "DOB": c018_dob, "PAN": c018_pan},
    )
    insert_registry(c018_pan, c018_name, c018_dob, c018_addr)
    cases.append(
        LabelledCase(
            case_id=c018_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c018_name,
            declared_dob=c018_dob,
            declared_country="IN",
            declared_address=c018_addr,
            declared_source_of_funds="corporate_consulting_retainers",
            expected_monthly_volume_inr=600000.0,
            documents=[f"data/docs/{c018_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.MEDIUM,
                expected_decision=Decision.APPROVE_EDD,
                planted_flags=["adverse_media"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 019: Individual, Planted Single Flag: inconsistent_funds (Rahul Verma)
    # -------------------------------------------------------------
    c019_id = "case_019"
    c019_name = "Rahul Verma"
    c019_dob = "2004-09-08"
    c019_pan = "ABCRV1019T"
    c019_addr = "Hostel 3, University Enclave, Delhi 110007"
    render_document_image(
        DOCS_DIR / f"{c019_id}_pan.png",
        "Student ID & PAN Card",
        {"Full_Name": c019_name, "DOB": c019_dob, "Occupation": "Student", "PAN": c019_pan},
    )
    insert_registry(c019_pan, c019_name, c019_dob, c019_addr)
    cases.append(
        LabelledCase(
            case_id=c019_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c019_name,
            declared_dob=c019_dob,
            declared_country="IN",
            declared_address=c019_addr,
            declared_source_of_funds="unverified_high_frequency_crypto_arbitrage",
            expected_monthly_volume_inr=25000000.0,  # 2.5 Crore monthly volume for college student
            documents=[f"data/docs/{c019_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.MEDIUM,
                expected_decision=Decision.APPROVE_EDD,
                planted_flags=["inconsistent_funds"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 020: Individual, Planted Single Flag: doc_tampering (Naveen Jindal)
    # -------------------------------------------------------------
    c020_id = "case_020"
    c020_name = "Naveen Jindal"
    c020_dob = "1972-01-19"
    c020_pan = "ABCNJ1020U"
    c020_addr = "104 Civil Lines, Jaipur 302006"
    render_document_image(
        DOCS_DIR / f"{c020_id}_pan.png",
        "PAN Card",
        {"Full_Name": c020_name, "DOB": c020_dob, "PAN": c020_pan},
        tampered=True,
    )
    insert_registry(c020_pan, c020_name, c020_dob, c020_addr)
    cases.append(
        LabelledCase(
            case_id=c020_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c020_name,
            declared_dob=c020_dob,
            declared_country="IN",
            declared_address=c020_addr,
            declared_source_of_funds="mineral_trading_revenue",
            expected_monthly_volume_inr=400000.0,
            documents=[f"data/docs/{c020_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["doc_tampering"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 021: Individual, Planted Single Flag: identity_mismatch (Meenakshi Sundaram)
    # -------------------------------------------------------------
    c021_id = "case_021"
    c021_name = "Meenakshi Sundaram"
    c021_dob = "1988-10-30"
    c021_pan = "ABCMS1021V"
    c021_addr = "54 TTK Road, Alwarpet, Chennai 600018"
    # Document contains conflicting name
    render_document_image(
        DOCS_DIR / f"{c021_id}_pan.png",
        "PAN Card",
        {"Full_Name": "Sundaram Rajagopal", "DOB": "1975-02-14", "PAN": c021_pan},
    )
    insert_registry(c021_pan, "Sundaram Rajagopal", "1975-02-14", c021_addr)
    cases.append(
        LabelledCase(
            case_id=c021_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c021_name,
            declared_dob=c021_dob,
            declared_country="IN",
            declared_address=c021_addr,
            declared_source_of_funds="textile_boutique_income",
            expected_monthly_volume_inr=110000.0,
            documents=[f"data/docs/{c021_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["identity_mismatch"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 022: Individual, Multi-Flag High Risk: sanctions_hit + doc_tampering (Alexei Volkov)
    # -------------------------------------------------------------
    c022_id = "case_022"
    c022_name = "Alexei Volkov"
    c022_dob = "1976-04-17"
    c022_pan = "ABCAV1022W"
    c022_addr = "25 Tverskaya Street, Moscow, Russian Federation"
    render_document_image(
        DOCS_DIR / f"{c022_id}_pan.png",
        "Foreign National Tax ID",
        {"Full_Name": c022_name, "DOB": c022_dob, "ID": c022_pan},
        tampered=True,
    )
    insert_registry(c022_pan, c022_name, c022_dob, c022_addr, country="RU", status="BLOCKED")
    cases.append(
        LabelledCase(
            case_id=c022_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c022_name,
            declared_dob=c022_dob,
            declared_country="RU",
            declared_address=c022_addr,
            declared_source_of_funds="offshore_petrochemical_brokering",
            expected_monthly_volume_inr=15000000.0,
            documents=[f"data/docs/{c022_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["sanctions_hit", "doc_tampering"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 023: Individual, Multi-Flag High Risk: pep + adverse_media + inconsistent_funds (Vikramaditya Rao)
    # -------------------------------------------------------------
    c023_id = "case_023"
    c023_name = "Vikramaditya Rao"
    c023_dob = "1962-03-15"
    c023_pan = "ABCVR1023X"
    c023_addr = "Penthouse 10, Palace View Apartments, Bengaluru 560001"
    render_document_image(
        DOCS_DIR / f"{c023_id}_pan.png",
        "Diplomatic & Ministerial Credential",
        {"Full_Name": c023_name, "DOB": c023_dob, "Position": "Former Minister of Trade", "PAN": c023_pan},
    )
    insert_registry(c023_pan, c023_name, c023_dob, c023_addr)
    cases.append(
        LabelledCase(
            case_id=c023_id,
            client_type=ClientType.INDIVIDUAL,
            declared_name=c023_name,
            declared_dob=c023_dob,
            declared_country="IN",
            declared_address=c023_addr,
            declared_source_of_funds="panama_private_holding_dividends",
            expected_monthly_volume_inr=18000000.0,
            documents=[f"data/docs/{c023_id}_pan.png"],
            ground_truth=GroundTruth(
                expected_tier=RiskTier.HIGH,
                expected_decision=Decision.ESCALATE,
                planted_flags=["pep", "adverse_media", "inconsistent_funds"],
                is_namesake_false_positive=False,
            ),
        )
    )

    # -------------------------------------------------------------
    # Case 024: Company, Clean (Bharat Engineering Works Pvt Ltd)
    # -------------------------------------------------------------
    c024_id = "case_024"
    c024_name = "Bharat Engineering Works Pvt Ltd"
    c024_cin = "U28100DL2018PTC334455"
    c024_addr = "Plot 45, Okhla Industrial Area Phase III, New Delhi 110020"
    render_document_image(
        DOCS_DIR / f"{c024_id}_incorporation.png",
        "Certificate of Incorporation",
        {"Company_Name": c024_name, "CIN": c024_cin, "Registered_Office": c024_addr},
    )
    insert_registry(c024_cin, c024_name, "2018-05-12", c024_addr, status="ACTIVE")
    c024_chart = {
        "entity": c024_name,
        "owners": [
            {"name": "Devendra Sharma", "pct": 60.0, "path": [c024_name, "Devendra Sharma"]},
            {"name": "Sunita Sharma", "pct": 40.0, "path": [c024_name, "Sunita Sharma"]},
        ],
    }
    cases.append(
        LabelledCase(
            case_id=c024_id,
            client_type=ClientType.COMPANY,
            declared_name=c024_name,
            declared_country="IN",
            declared_address=c024_addr,
            declared_source_of_funds="industrial_machinery_manufacturing_turnover",
            expected_monthly_volume_inr=3500000.0,
            documents=[f"data/docs/{c024_id}_incorporation.png"],
            ownership_chart=c024_chart,
            ground_truth=GroundTruth(
                expected_tier=RiskTier.LOW,
                expected_decision=Decision.APPROVE,
                planted_flags=[],
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


def summarize_dataset(cases: list[LabelledCase] | None = None) -> dict[str, Any]:
    """Compute and format statistical breakdown of the dataset."""
    if cases is None:
        cases = []
        for case_file in sorted(CASES_DIR.glob("case_*.json")):
            with open(case_file, encoding="utf-8") as f:
                cases.append(LabelledCase.model_validate_json(f.read()))

    total = len(cases)
    client_types: dict[str, int] = {}
    expected_decisions: dict[str, int] = {}
    expected_tiers: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    namesakes = 0

    for c in cases:
        ct = c.client_type.value
        client_types[ct] = client_types.get(ct, 0) + 1

        dec = c.ground_truth.expected_decision.value
        expected_decisions[dec] = expected_decisions.get(dec, 0) + 1

        tr = c.ground_truth.expected_tier.value
        expected_tiers[tr] = expected_tiers.get(tr, 0) + 1

        if c.ground_truth.is_namesake_false_positive:
            namesakes += 1

        for flag in c.ground_truth.planted_flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    summary = {
        "total_cases": total,
        "client_types": client_types,
        "expected_decisions": expected_decisions,
        "expected_tiers": expected_tiers,
        "flag_distribution": flag_counts,
        "namesake_false_positives": namesakes,
    }
    return summary


def print_dataset_statistics(summary: dict[str, Any]) -> None:
    """Print markdown formatted dataset summary table."""
    print("\n" + "=" * 70)
    print("ONBOARDIQ EVALUATION DATASET: COMPOSITION & SUMMARY STATISTICS")
    print("=" * 70)
    print(f"Total Labelled Cases: {summary['total_cases']}")
    print(f"Client Types: {summary['client_types']}")
    print(f"Expected Decisions: {summary['expected_decisions']}")
    print(f"Risk Tiers: {summary['expected_tiers']}")
    print(f"Namesake False Positives: {summary['namesake_false_positives']}")
    print("\nPlanted Red Flag Distribution:")
    for flag, cnt in sorted(summary["flag_distribution"].items(), key=lambda x: -x[1]):
        print(f"  - {flag:<22}: {cnt} case(s)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    generated = generate_all_cases()
    stats = summarize_dataset(generated)
    print_dataset_statistics(stats)
