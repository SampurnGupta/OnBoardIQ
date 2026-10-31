"""FastMCP Tool — Adverse News Search.

Supports two backends:
1. Local reproducible news corpus in data/news/corpus.json (default).
2. Optional live search API chosen by env var (NEWS_SEARCH_BACKEND=live or NEWS_API_KEY).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

CORPUS_PATH = Path("data/news/corpus.json")


def _search_local_corpus(
    query: str,
    threshold: float = 0.65,
) -> list[dict[str, Any]]:
    """Search local JSON news corpus with fuzzy matching."""
    if not CORPUS_PATH.exists():
        return []

    try:
        with open(CORPUS_PATH, encoding="utf-8") as f:
            articles: list[dict[str, Any]] = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    hits: list[dict[str, Any]] = []
    q_norm = query.strip().lower()

    for art in articles:
        subject = art.get("subject_name", "")
        aliases = art.get("alias_names", [])
        title = art.get("title", "")

        # Compute max match score across subject name, aliases, and title
        scores = [
            fuzz.token_sort_ratio(q_norm, subject.lower()) / 100.0,
            fuzz.token_set_ratio(q_norm, title.lower()) / 100.0,
        ]
        for alias in aliases:
            scores.append(fuzz.token_sort_ratio(q_norm, alias.lower()) / 100.0)

        best_score = max(scores) if scores else 0.0

        if best_score >= threshold:
            hits.append(
                {
                    "article_id": art.get("article_id", "news_unknown"),
                    "title": art.get("title", ""),
                    "source_url": art.get("source_url", ""),
                    "published_date": art.get("published_date", ""),
                    "category": art.get("category", "other"),
                    "match_score": round(best_score, 3),
                    "summary": art.get("summary", ""),
                    "location": art.get("location", ""),
                    "risk_level": art.get("risk_level", "medium"),
                    "backend": "local_corpus",
                }
            )

    hits.sort(key=lambda x: x["match_score"], reverse=True)
    return hits


def _search_live_api(
    query: str,
    api_key: str,
) -> list[dict[str, Any]]:
    """Optional live news search API backend."""
    import httpx

    # NewsAPI endpoint fallback
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": f'"{query}" AND (fraud OR "money laundering" OR corruption OR investigation)',
        "apiKey": api_key,
        "pageSize": 5,
        "sortBy": "relevancy",
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("articles", [])
                hits = []
                for i, art in enumerate(articles):
                    hits.append(
                        {
                            "article_id": f"live_news_{i+1}",
                            "title": art.get("title", ""),
                            "source_url": art.get("url", ""),
                            "published_date": art.get("publishedAt", ""),
                            "category": "other",
                            "match_score": 0.85,
                            "summary": art.get("description", "") or art.get("title", ""),
                            "location": "Global",
                            "risk_level": "medium",
                            "backend": "live_api",
                        }
                    )
                return hits
    except (httpx.HTTPError, OSError):
        # Fall back gracefully to local corpus on network error
        return _search_local_corpus(query)
    return _search_local_corpus(query)


def news_search(
    query: str,
    threshold: float = 0.65,
) -> dict[str, Any]:
    """Search for adverse news articles regarding an individual or corporate subject.

    Args:
        query: Name of the person or entity to search (never provide raw ID numbers).
        threshold: Minimum fuzzy similarity threshold (default 0.65).

    Returns:
        dict containing 'query', 'count', and list of 'articles'.
    """
    backend = os.getenv("NEWS_SEARCH_BACKEND", "local").lower()
    api_key = os.getenv("NEWS_API_KEY", "")

    if backend == "live" and api_key:
        articles = _search_live_api(query, api_key)
    else:
        articles = _search_local_corpus(query, threshold=threshold)

    return {
        "query": query,
        "count": len(articles),
        "articles": articles,
    }

