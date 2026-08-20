"""arXiv Atom API source."""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from typing import Any

import feedparser
import requests

LOG = logging.getLogger(__name__)

API_URL = "http://export.arxiv.org/api/query"
PAGE_SIZE = 100
REQUEST_DELAY = 3.0
USER_AGENT = "veille-scientifique/1.0 (personal research digest)"

_VERSION_RE = re.compile(r"v\d+$")


def _date_window(days: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=days)
    fmt = "%Y%m%d%H%M"
    return f"submittedDate:[{start.strftime(fmt)} TO {now.strftime(fmt)}]"


def _normalize(entry: Any) -> dict[str, Any] | None:
    raw_id = entry.get("id", "")
    if not raw_id:
        return None
    short_id = _VERSION_RE.sub("", raw_id.rsplit("/abs/", 1)[-1])

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{short_id}"

    return {
        "uid": f"arxiv:{short_id}",
        "title": " ".join(entry.get("title", "").split()),
        "abstract": " ".join(entry.get("summary", "").split()),
        "authors": [a.get("name", "") for a in entry.get("authors", [])],
        "url": raw_id,
        "pdf_url": pdf_url,
        "published": entry.get("published", ""),
        "categories": [t.get("term", "") for t in entry.get("tags", [])],
        "venue": "arXiv",
        "source": "arXiv",
    }


def _query(search_query: str, max_results: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    start = 0
    while start < max_results:
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(PAGE_SIZE, max_results - start),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        try:
            resp = requests.get(
                API_URL, params=params, timeout=60, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            LOG.warning("arXiv request failed: %s", exc)
            break

        feed = feedparser.parse(resp.text)
        entries = feed.entries or []
        for entry in entries:
            paper = _normalize(entry)
            if paper:
                results.append(paper)

        if len(entries) < params["max_results"]:
            break
        start += PAGE_SIZE
        time.sleep(REQUEST_DELAY)

    return results


def fetch(cfg: dict[str, Any], lookback_days: int) -> list[dict[str, Any]]:
    """Return recent arXiv papers for the configured categories and queries."""
    window = _date_window(lookback_days)
    max_results = int(cfg.get("max_results_per_query", 300))
    queries: list[str] = []

    categories = cfg.get("categories") or []
    if categories:
        cat_clause = " OR ".join(f"cat:{c}" for c in categories)
        queries.append(f"({cat_clause}) AND {window}")

    for extra in cfg.get("extra_queries") or []:
        queries.append(f"({extra}) AND {window}")

    papers: dict[str, dict[str, Any]] = {}
    for query in queries:
        LOG.info("arXiv query: %s", query)
        for paper in _query(query, max_results):
            papers.setdefault(paper["uid"], paper)
        time.sleep(REQUEST_DELAY)

    LOG.info("arXiv: %d unique papers", len(papers))
    return list(papers.values())
