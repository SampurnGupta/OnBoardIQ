"""Smoke test script for FastMCP tool server capabilities.

Verifies that all tools can be called directly on sample case data.
"""

from __future__ import annotations

import json
from pathlib import Path

from onboardiq.mcp_server.tools.doc_ocr import extract_doc_ocr
from onboardiq.mcp_server.tools.registry_lookup import lookup_registry
from onboardiq.mcp_server.tools.sanctions_screen import screen_sanctions

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_smoke_test():
    print("=== OnboardIQ MCP Tools Smoke Test ===")

    # 1. Test Registry Lookup
    print("\n1. Testing 'registry_lookup':")
    reg_clean = lookup_registry("ABCPS1001A")
    print(f" - Clean ID (ABCPS1001A): found={reg_clean.found}, name={reg_clean.record.full_name if reg_clean.record else None}")
    assert reg_clean.found is True

    reg_missing = lookup_registry("UNKNOWN_ID_999")
    print(f" - Non-existent ID: found={reg_missing.found}, detail={reg_missing.detail}")
    assert reg_missing.found is False

    # 2. Test Sanctions Screening
    print("\n2. Testing 'sanctions_screen':")
    # True match
    s_hit = screen_sanctions("Viktor Darkovich")
    print(f" - Target 'Viktor Darkovich': total candidates={s_hit.total_candidates}")
    assert s_hit.total_candidates >= 1
    top_hit = s_hit.candidates[0]
    print(f"   Top candidate: {top_hit.matched_name} | score: {top_hit.match_score} | disposition: {top_hit.disposition}")
    assert top_hit.match_score >= 0.95

    # Namesake / fuzzy match
    s_namesake = screen_sanctions("Victor Darko")
    print(f" - Namesake 'Victor Darko': total candidates={s_namesake.total_candidates}")
    assert s_namesake.total_candidates >= 1
    print(f"   Top candidate: {s_namesake.candidates[0].matched_name} | score: {s_namesake.candidates[0].match_score}")

    # Clean name
    s_clean = screen_sanctions("Priya Rajesh Sharma")
    print(f" - Clean 'Priya Rajesh Sharma': candidates={s_clean.total_candidates}")

    # 3. Test Document OCR
    print("\n3. Testing 'doc_ocr':")
    sample_doc = "data/docs/case_001_pan.png"
    ocr_res = extract_doc_ocr(sample_doc)
    print(f" - Doc path: {sample_doc}")
    print(f" - Extracted Doc ID: {ocr_res.doc_id}, Type: {ocr_res.doc_type}")
    print(f" - Fields: {json.dumps(ocr_res.fields)}")
    assert ocr_res.doc_type == "pan_card"
    assert "full_name" in ocr_res.fields or "pan" in ocr_res.fields

    print("\n=== Smoke Test Passed Successfully! ===")


if __name__ == "__main__":
    run_smoke_test()

