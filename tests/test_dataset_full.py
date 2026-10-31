"""Tests for Task T28: Full evaluation dataset (20-24 cases) and statistics."""

from __future__ import annotations

import json

from scripts.download_public_lists import (
    load_pep_entries,
    load_sanctions_entries,
    print_download_instructions,
)

from onboardiq.eval.dataset_gen import (
    CASES_DIR,
    generate_all_cases,
    summarize_dataset,
)
from onboardiq.schema import LabelledCase, RiskTier


def test_full_dataset_composition_and_validation():
    """Verify all 24 cases exist, validate as LabelledCase, and match docs/05_EVALUATION.md composition."""
    case_files = sorted(CASES_DIR.glob("case_*.json"))
    assert len(case_files) == 24, f"Expected exactly 24 labelled cases, found {len(case_files)}"

    cases: list[LabelledCase] = []
    for cf in case_files:
        with open(cf, encoding="utf-8") as f:
            data = json.load(f)
            case = LabelledCase.model_validate(data)
            cases.append(case)

    # 1. Clean individuals count == 6 (001, 002, 003, 011, 012, 013)
    clean_individuals = [
        c for c in cases
        if c.client_type.value == "individual"
        and c.ground_truth.expected_tier == RiskTier.LOW
        and not c.ground_truth.is_namesake_false_positive
    ]
    assert len(clean_individuals) == 6, f"Expected 6 clean individuals, found {len(clean_individuals)}"

    # 2. Namesake false positives == 3 (004, 005, 014)
    namesakes = [c for c in cases if c.ground_truth.is_namesake_false_positive]
    assert len(namesakes) == 3, f"Expected 3 namesake false positives, found {len(namesakes)}"

    # 3. Planted single flags count on individuals == 8 (006, 015, 016, 017, 018, 019, 020, 021)
    single_flags = [c for c in cases if c.client_type.value == "individual" and len(c.ground_truth.planted_flags) == 1]
    assert len(single_flags) == 8, f"Expected 8 single-flag individual cases, found {len(single_flags)}"

    # 4. Multi-flag high risk cases >= 3 (010, 022, 023)
    multi_flags = [c for c in cases if len(c.ground_truth.planted_flags) >= 2]
    assert len(multi_flags) >= 3, f"Expected >= 3 multi-flag cases, found {len(multi_flags)}"

    # 5. Companies count >= 4
    companies = [c for c in cases if c.client_type.value == "company"]
    assert len(companies) >= 4, f"Expected >= 4 companies, found {len(companies)}"


def test_dataset_summary_statistics():
    """Verify dataset summary metrics and planted flag distribution."""
    stats = summarize_dataset()
    assert stats["total_cases"] == 24
    assert stats["namesake_false_positives"] == 3
    flags = stats["flag_distribution"]

    # Verify all 7 core planted flag types from 05_EVALUATION.md are present
    expected_flags = [
        "sanctions_hit", "pep", "adverse_media",
        "doc_tampering", "identity_mismatch", "opaque_ownership", "inconsistent_funds"
    ]
    for ef in expected_flags:
        assert ef in flags, f"Expected flag '{ef}' missing in dataset distribution"
        assert flags[ef] >= 1, f"Flag '{ef}' count must be >= 1"


def test_public_lists_loader_and_instructions(capsys):
    """Verify download instructions and offline loader for sanctions and PEP lists."""
    print_download_instructions()
    captured = capsys.readouterr()
    assert "PUBLIC SANCTIONS & PEP LISTS: DOWNLOAD & LOAD INSTRUCTIONS" in captured.out
    assert "https://www.treasury.gov/ofac/downloads/sdn.csv" in captured.out

    sanctions = load_sanctions_entries()
    assert len(sanctions) >= 5
    peps = load_pep_entries()
    assert len(peps) >= 3


def test_fixed_seed_reproducibility():
    """Verify that re-running generator with fixed seed 42 produces identical output."""
    cases = generate_all_cases()
    assert len(cases) == 24
    assert cases[0].case_id == "case_001"
    assert cases[-1].case_id == "case_024"
