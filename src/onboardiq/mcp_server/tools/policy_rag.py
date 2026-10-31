"""FastMCP Tool — Policy RAG.

Retrieves compliance policy rules from data/policy.md using keyword and fuzzy semantic search.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

POLICY_PATH = Path("data/policy.md")


def _load_policy_rules() -> list[dict[str, str]]:
    """Parse data/policy.md into structured rules."""
    if not POLICY_PATH.exists():
        return []

    content = POLICY_PATH.read_text(encoding="utf-8")
    rules: list[dict[str, str]] = []

    # Regex matches: 1. **Rule X — Title:** Description
    pattern = re.compile(r"^\d+\.\s+\*\*(Rule\s+\d+)\s+—\s+([^:]+):\*\*\s+(.+)$", re.MULTILINE)
    for match in pattern.finditer(content):
        rule_id = match.group(1).strip()
        title = match.group(2).strip()
        body = match.group(3).strip()
        rules.append({
            "rule_id": rule_id,
            "title": title,
            "text": body,
            "full_rule": f"{rule_id}: {title} — {body}",
        })

    return rules


def query_policy(
    query: str,
    rule_id: str | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    """Query institutional KYC/AML policy rules.

    Args:
        query: Natural language query (e.g., 'sanctions escalation', 'PEP EDD', 'rejection rule').
        rule_id: Optional specific rule number or ID (e.g., 'Rule 2' or '2').
        top_k: Maximum number of relevant rules to return.

    Returns:
        dict containing 'query', 'count', and list of 'matches'.
    """
    rules = _load_policy_rules()
    if not rules:
        return {"query": query, "count": 0, "matches": []}

    # If specific rule_id requested
    if rule_id:
        normalized_id = rule_id.lower().replace("rule", "").strip()
        for r in rules:
            r_num = r["rule_id"].lower().replace("rule", "").strip()
            if r_num == normalized_id or r["rule_id"].lower() == rule_id.lower():
                return {
                    "query": query,
                    "count": 1,
                    "matches": [{**r, "score": 1.0}],
                }

    q_lower = query.lower()
    scored_matches: list[dict[str, Any]] = []

    for r in rules:
        rule_text = f"{r['title']} {r['text']}".lower()
        score = fuzz.token_set_ratio(q_lower, rule_text) / 100.0

        # Exact keyword boosters for key compliance domains
        keywords = {
            "sanction": ["Rule 2"],
            "pep": ["Rule 3"],
            "reject": ["Rule 4"],
            "auto-reject": ["Rule 4"],
            "tamper": ["Rule 6"],
            "media": ["Rule 7"],
            "ubo": ["Rule 8", "Rule 9"],
            "ownership": ["Rule 8", "Rule 9"],
            "volume": ["Rule 11"],
            "evidence": ["Rule 13"],
            "injection": ["Rule 14"],
        }
        for kw, target_rules in keywords.items():
            if kw in q_lower and r["rule_id"] in target_rules:
                score = max(score, 0.95)

        if score >= 0.35:
            scored_matches.append({
                "rule_id": r["rule_id"],
                "title": r["title"],
                "text": r["text"],
                "score": round(score, 3),
            })

    scored_matches.sort(key=lambda x: x["score"], reverse=True)
    results = scored_matches[:top_k]

    return {
        "query": query,
        "count": len(results),
        "matches": results,
    }

