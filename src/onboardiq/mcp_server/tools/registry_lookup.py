"""Mock registry lookup tool via SQLite.

Queries data/registry.db to verify declared ID numbers and retrieve official records.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "data" / "registry.db"


class RegistryLookupInput(BaseModel):
    id_number: str = Field(description="Identification number (PAN, Passport, CIN, etc.)")


class RegistryRecord(BaseModel):
    id_number: str
    full_name: str
    dob: str | None = None
    address: str
    country: str
    status: str


class RegistryLookupOutput(BaseModel):
    found: bool
    record: RegistryRecord | None = None
    detail: str


def lookup_registry(id_number: str, db_path: Path | str | None = None) -> RegistryLookupOutput:
    """Execute registry lookup against SQLite mock registry."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    clean_id = id_number.strip().upper()

    if not path.exists():
        return RegistryLookupOutput(
            found=False,
            record=None,
            detail=f"Registry database not found at {path}",
        )

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            cursor = conn.execute(
                """
                SELECT id_number, full_name, dob, address, country, status
                FROM registry_records
                WHERE UPPER(id_number) = ?
                """,
                (clean_id,),
            )
            row = cursor.fetchone()
            if not row:
                return RegistryLookupOutput(
                    found=False,
                    record=None,
                    detail=f"No registry record found for ID '{id_number}'",
                )

            record = RegistryRecord(
                id_number=row["id_number"],
                full_name=row["full_name"],
                dob=row["dob"],
                address=row["address"],
                country=row["country"],
                status=row["status"],
            )
            return RegistryLookupOutput(
                found=True,
                record=record,
                detail=f"Verified registry record found for '{record.full_name}' (status: {record.status})",
            )
    finally:
        conn.close()
