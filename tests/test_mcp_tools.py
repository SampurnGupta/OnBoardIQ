"""Unit tests for MCP server tools (T05 acceptance).

Tests:
- sanctions_screen exact match, fuzzy namesake, and clean queries
- registry_lookup on active and non-existent records
- doc_ocr extraction on sample document images
"""

from onboardiq.mcp_server.tools.doc_ocr import extract_doc_ocr
from onboardiq.mcp_server.tools.registry_lookup import lookup_registry
from onboardiq.mcp_server.tools.sanctions_screen import screen_sanctions


def test_sanctions_exact_hit():
    res = screen_sanctions("Viktor Darkovich", threshold=0.7)
    assert res.total_candidates >= 1
    top = res.candidates[0]
    assert top.matched_name == "Viktor Darkovich"
    assert top.match_score >= 0.95
    assert top.disposition == "true_match"


def test_sanctions_fuzzy_namesake():
    # 'Victor Darko' vs 'Viktor Darkovich' / 'Victor Darko'
    res = screen_sanctions("Victor Darko", threshold=0.7)
    assert res.total_candidates >= 1
    scores = [c.match_score for c in res.candidates]
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_sanctions_clean_name():
    # A totally clean name with high threshold should return 0 candidates
    res = screen_sanctions("Totally Unique Clean Name 12345", threshold=0.85)
    assert res.total_candidates == 0


def test_pep_screening():
    res = screen_sanctions("Vikramaditya Rao", threshold=0.8)
    assert res.total_candidates >= 1
    assert any(c.list_name == "PEP" for c in res.candidates)


def test_registry_lookup_success():
    res = lookup_registry("ABCPS1001A")
    assert res.found is True
    assert res.record is not None
    assert res.record.full_name == "Priya Rajesh Sharma"
    assert res.record.status == "ACTIVE"


def test_registry_lookup_not_found():
    res = lookup_registry("NONEXISTENT_XYZ_999")
    assert res.found is False
    assert res.record is None


def test_doc_ocr_pan():
    res = extract_doc_ocr("data/docs/case_001_pan.png")
    assert res.doc_id == "case_001_pan"
    assert res.doc_type == "pan_card"
    assert res.tamper_score == 0.0
    assert len(res.fields) > 0

