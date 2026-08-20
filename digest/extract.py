"""PDF download and text extraction."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import fitz
import requests

LOG = logging.getLogger(__name__)
USER_AGENT = "veille-scientifique/1.0 (personal research digest)"

_REFERENCES_RE = re.compile(
    r"\n\s*(references|bibliography|r\s?e\s?f\s?e\s?r\s?e\s?n\s?c\s?e\s?s)\s*\n", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def download_pdf(paper: dict[str, Any], dest_dir: Path, timeout: int = 90) -> Path | None:
    url = paper.get("pdf_url")
    if not url:
        return None

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", paper["uid"]) + ".pdf"
    dest = dest_dir / safe_name
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest

    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        LOG.warning("PDF download failed for %s: %s", paper["uid"], exc)
        return None

    if not resp.content.startswith(b"%PDF"):
        LOG.warning("Not a PDF for %s (%s)", paper["uid"], resp.headers.get("Content-Type"))
        return None

    dest.write_bytes(resp.content)
    return dest


def pdf_to_text(path: Path, max_pages: int = 40) -> str:
    try:
        with fitz.open(str(path)) as doc:
            pages = [doc[i].get_text("text") for i in range(min(len(doc), max_pages))]
    except Exception as exc:  # noqa: BLE001 - corrupted PDFs must not break the run
        LOG.warning("PDF parsing failed for %s: %s", path.name, exc)
        return ""
    return "\n".join(pages)


def clean(text: str) -> str:
    match = _REFERENCES_RE.search(text)
    if match and match.start() > len(text) * 0.4:
        text = text[: match.start()]
    text = _WHITESPACE_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return text.strip()


def build_llm_input(paper: dict[str, Any], body: str, max_chars: int) -> str:
    """Assemble metadata plus a truncated body that fits the model context."""
    header = (
        f"Titre: {paper.get('title', '')}\n"
        f"Auteurs: {', '.join(paper.get('authors', [])[:10])}\n"
        f"Source: {paper.get('venue') or paper.get('source', '')}\n"
        f"Date: {paper.get('published', '')}\n"
        f"Categories: {', '.join(paper.get('categories', []))}\n\n"
        f"Resume officiel:\n{paper.get('abstract', '')}\n\n"
    )
    budget = max_chars - len(header)
    if budget <= 0 or not body:
        return header

    if len(body) <= budget:
        return header + "Texte integral:\n" + body

    # Keep the beginning (intro, method) and the end (results, conclusion)
    head = int(budget * 0.65)
    tail = budget - head
    return (
        header
        + "Texte (debut):\n"
        + body[:head]
        + "\n\n[...]\n\nTexte (fin):\n"
        + body[-tail:]
    )
