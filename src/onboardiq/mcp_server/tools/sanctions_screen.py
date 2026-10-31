"""Sanctions and PEP screening tool using RapidFuzz.

Screens candidate names against public/synthetic lists and computes match scores.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

LISTS_DIR = Path(__file__).resolve().parents[4] / "data" / "lists"
DEFAULT_SANCTIONS_CSV = LISTS_DIR / "sanctions_sample.csv"
DEFAULT_PEP_CSV = LISTS_DIR / "pep_sample.csv"


class CandidateMatch(BaseModel):
    list_name: str
    matched_name: str
    match_score: float = Field(ge=0.0, le=1.0, description="Similarity score between 0.0 and 1.0")
    country: str | None = None
    entry_type: str = "individual"
    disposition: Literal["true_match", "likely_match", "false_positive", "unresolved"] = "unresolved"
    reasoning: str = ""


class SanctionsScreenInput(BaseModel):
    name: str = Field(description="Name of the applicant or beneficial owner to screen")
    country: str | None = Field(default=None, description="Country filter or context")
    threshold: float = Field(default=0.65, ge=0.0, le=1.0, description="Minimum similarity score")


class SanctionsScreenOutput(BaseModel):
    query_name: str
    total_candidates: int
    candidates: list[CandidateMatch]


def screen_sanctions(
    name: str,
    country: str | None = None,
    threshold: float = 0.65,
    sanctions_path: Path | None = None,
    pep_path: Path | None = None,
) -> SanctionsScreenOutput:
    """Fuzzy screen target name across sanctions and PEP lists."""
    sanctions_csv = sanctions_path or DEFAULT_SANCTIONS_CSV
    pep_csv = pep_path or DEFAULT_PEP_CSV

    query = name.strip()
    candidates: list[CandidateMatch] = []

    # 1. Screen Sanctions List
    if sanctions_csv.exists():
        with sanctions_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entry_name = row["entry_name"].strip()
                # Compute token sort ratio and standard ratio
                score_sort = fuzz.token_sort_ratio(query.lower(), entry_name.lower()) / 100.0
                score_ratio = fuzz.ratio(query.lower(), entry_name.lower()) / 100.0
                best_score = max(score_sort, score_ratio)

                if best_score >= threshold:
                    # Disposition heuristic based on score
                    if best_score >= 0.95:
                        disp = "true_match"
                        reason = f"Exact or near-exact match ({best_score:.2f}) against {row['list_name']}"
                    elif best_score >= 0.80:
                        disp = "likely_match"
                        reason = f"Strong fuzzy similarity ({best_score:.2f}) against {row['list_name']}"
                    else:
                        disp = "likely_match" if not country or country == row.get("country") else "false_positive"
                        reason = f"Partial name similarity ({best_score:.2f}) against {row['list_name']}"

                    candidates.append(
                        CandidateMatch(
                            list_name=row.get("list_name", "SANCTIONS"),
                            matched_name=entry_name,
                            match_score=round(best_score, 3),
                            country=row.get("country"),
                            entry_type=row.get("entry_type", "individual"),
                            disposition=disp,
                            reasoning=reason,
                        )
                    )

    # 2. Screen PEP List
    if pep_csv.exists():
        with pep_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pep_name = row["name"].strip()
                score_sort = fuzz.token_sort_ratio(query.lower(), pep_name.lower()) / 100.0
                score_ratio = fuzz.ratio(query.lower(), pep_name.lower()) / 100.0
                best_score = max(score_sort, score_ratio)

                if best_score >= threshold:
                    disp = "true_match" if best_score >= 0.95 else ("likely_match" if best_score >= 0.80 else "false_positive")
                    candidates.append(
                        CandidateMatch(
                            list_name="PEP",
                            matched_name=pep_name,
                            match_score=round(best_score, 3),
                            country=row.get("country"),
                            entry_type="individual",
                            disposition=disp,
                            reasoning=f"PEP match ({best_score:.2f}) for position: {row.get('position', 'Official')}",
                        )
                    )

    # Sort descending by match score
    candidates.sort(key=lambda x: x.match_score, reverse=True)

    return SanctionsScreenOutput(
        query_name=query,
        total_candidates=len(candidates),
        candidates=candidates,
    )
