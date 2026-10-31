"""Tests for Task T31: Streamlit UI module imports and helper functions."""

from __future__ import annotations

from onboardiq.ui.app import get_shared_client, load_cases


def test_ui_cases_loaded():
    """Verify load_cases returns benchmark cases for UI display."""
    cases = load_cases()
    assert len(cases) >= 20, f"UI must load >= 20 benchmark cases, found {len(cases)}"
    assert "case_001" in cases
    assert "case_008" in cases


def test_ui_shared_client():
    """Verify get_shared_client instantiates a valid BlackboardClient."""
    client = get_shared_client()
    assert client is not None
    assert client.base_url == "http://testserver"

