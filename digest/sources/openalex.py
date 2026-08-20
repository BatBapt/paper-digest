"""OpenAlex source: journals and conference proceedings outside arXiv."""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any

import requests

LOG = logging.getLogger(__name__)

API_URL = "https://api.openalex.org/works"
REQUEST_DELAY = 1.0
USER_AGENT = "veille-scientifique/1.0 (personal research digest)"


def _abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort()
    return " ".join(word for _, word in positions)


def _normalize(work: dict[str, Any]) -> dict[str, Any] | None:
    uid = work.get("doi") or work.get("id")
    if not uid:
        return None

    location = work.get("best_oa_location") or work.get("primary_location") or {}
    host = (location or {}).get("source") or {}

    return {
        "uid": f"openalex:{uid}",
        "title": work.get("title") or "",
        "abstract": _abstract(work.get("abstract_inverted_index")),
        "authors": [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])[:12]
        ],
        "url": work.get("doi") or work.get("id") or "",
        "pdf_url": (location or {}).get("pdf_url") or "",
        "published": work.get("publication_date", ""),
        "categories": [
            (c.get("display_name") or "") for c in (work.get("topics") or [])[:5]
        ],
        "venue": host.get("display_name") or work.get("type") or "",
        "source": "OpenAlex",
    }


def fetch(cfg: dict[str, Any], lookback_days: int) -> list[dict[str, Any]]:
    start_date = (dt.date.today() - dt.timedelta(days=lookback_days)).isoformat()
    per_page = min(int(cfg.get("max_results_per_query", 50)), 200)
    mailto = cfg.get("mailto") or ""

    papers: dict[str, dict[str, Any]] = {}
    for query in cfg.get("queries") or []:
        params = {
            "filter": f"from_publication_date:{start_date},title_and_abstract.search:{query}",
            "per-page": per_page,
            "sort": "publication_date:desc",
        }
        if mailto:
            params["mailto"] = mailto

        try:
            resp = requests.get(
                API_URL, params=params, timeout=60, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            items = resp.json().get("results", [])
        except (requests.RequestException, ValueError) as exc:
            LOG.warning("OpenAlex request failed for %r: %s", query, exc)
            continue

        for work in items:
            paper = _normalize(work)
            if paper and paper["title"]:
                papers.setdefault(paper["uid"], paper)
        time.sleep(REQUEST_DELAY)

    LOG.info("OpenAlex: %d unique papers", len(papers))
    return list(papers.values())
