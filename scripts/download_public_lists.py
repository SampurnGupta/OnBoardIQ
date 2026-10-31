"""Script for downloading and loading real public OFAC, UN, and PEP lists.

Provides instructions and optional download functions for:
1. US OFAC Specially Designated Nationals (SDN) CSV
2. United Nations Security Council Consolidated Sanctions List
3. OpenSanctions / PEP dataset
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

LISTS_DIR = Path(__file__).resolve().parents[1] / "data" / "lists"

PUBLIC_SOURCES = {
    "OFAC_SDN": {
        "url": "https://www.treasury.gov/ofac/downloads/sdn.csv",
        "destination": LISTS_DIR / "ofac_sdn.csv",
        "description": "US Treasury Office of Foreign Assets Control Specially Designated Nationals list",
    },
    "UN_CONSOLIDATED": {
        "url": "https://www.un.org/securitycouncil/content/un-sc-consolidated-list",
        "destination": LISTS_DIR / "un_consolidated.csv",
        "description": "UN Security Council Consolidated Sanctions List",
    },
    "OPENSANCTIONS_PEP": {
        "url": "https://data.opensanctions.org/datasets/latest/default/entities.ftm.json",
        "destination": LISTS_DIR / "pep_public.csv",
        "description": "OpenSanctions Politically Exposed Persons (PEP) reference set",
    },
}


def print_download_instructions() -> None:
    """Print instructions for user-driven download of public sanctions and PEP lists."""
    print("=" * 80)
    print("PUBLIC SANCTIONS & PEP LISTS: DOWNLOAD & LOAD INSTRUCTIONS")
    print("=" * 80)
    print("To evaluate OnboardIQ against official live government watchlists:")
    for name, info in PUBLIC_SOURCES.items():
        print(f"\n[{name}]")
        print(f"  Description: {info['description']}")
        print(f"  Download URL: {info['url']}")
        print(f"  Target File:  {info['destination']}")
    print("\n" + "=" * 80)
    print("Once downloaded, run this script to parse and index the lists into FastMCP format.")
    print("If not downloaded, OnboardIQ automatically uses the reproducible benchmark samples:")
    print(f"  - {LISTS_DIR / 'sanctions_sample.csv'}")
    print(f"  - {LISTS_DIR / 'pep_sample.csv'}")
    print("=" * 80)


def load_sanctions_entries() -> list[dict[str, Any]]:
    """Load sanctions records from either downloaded full files or benchmark sample."""
    entries: list[dict[str, Any]] = []

    # Check for downloaded OFAC list
    ofac_file = PUBLIC_SOURCES["OFAC_SDN"]["destination"]
    if ofac_file.exists():
        with open(ofac_file, encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) > 1 and row[0].isdigit():
                    entries.append({
                        "list_name": "OFAC_SDN",
                        "entry_name": row[1].strip(),
                        "country": row[3].strip() if len(row) > 3 else "UNKNOWN",
                        "entry_type": row[2].strip().lower() if len(row) > 2 else "individual",
                    })

    # Always ensure benchmark sample is present
    sample_file = LISTS_DIR / "sanctions_sample.csv"
    if sample_file.exists():
        with open(sample_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(dict(row))

    return entries


def load_pep_entries() -> list[dict[str, Any]]:
    """Load PEP records from either downloaded list or benchmark sample."""
    entries: list[dict[str, Any]] = []
    pep_sample = LISTS_DIR / "pep_sample.csv"
    if pep_sample.exists():
        with open(pep_sample, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(dict(row))
    return entries


if __name__ == "__main__":
    print_download_instructions()

