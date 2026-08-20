"""Rule based relevance scoring and theme assignment."""
from __future__ import annotations

import re
from typing import Any

_CACHE: dict[str, re.Pattern[str]] = {}


def _pattern(keyword: str) -> re.Pattern[str]:
    if keyword not in _CACHE:
        _CACHE[keyword] = re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
    return _CACHE[keyword]


def _haystack(paper: dict[str, Any]) -> str:
    return f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()


def score(paper: dict[str, Any], cfg: dict[str, Any]) -> tuple[int, list[str]]:
    text = _haystack(paper)
    total = 0
    matched: list[str] = []

    for keyword, weight in (cfg.get("keywords") or {}).items():
        if _pattern(keyword).search(text):
            total += int(weight)
            matched.append(keyword)

    cat_weights = cfg.get("categories") or {}
    for category in paper.get("categories", []):
        total += int(cat_weights.get(category, 0))

    # Title hits count double
    title = paper.get("title", "").lower()
    for keyword in matched:
        if _pattern(keyword).search(title):
            total += int((cfg.get("keywords") or {}).get(keyword, 0))

    return total, matched


def theme(paper: dict[str, Any], themes: dict[str, list[str]]) -> str:
    text = _haystack(paper)
    fallback = "Other"
    for name, keywords in themes.items():
        for keyword in keywords:
            if not keyword:
                fallback = name
                continue
            if _pattern(keyword).search(text):
                return name
    return fallback
