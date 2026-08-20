"""Summarization through a remote Ollama instance."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

LOG = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a research digest assistant covering artificial intelligence, computer vision, "
    "audio and video signal processing, and sign language technology. "
    "You read scientific papers and write precise, technical summaries in English. "
    "No flattery, no filler, no marketing language. "
    "You answer with a single valid JSON object and nothing around it."
)

USER_TEMPLATE = """Analyse the paper below and return a JSON object with exactly these keys:

- "summary": 10 to 15 sentences, technical and concrete, covering the whole paper
- "problem": the problem being addressed, 1 to 2 sentences
- "method": the proposed approach, architecture and key ideas, 2 to 4 sentences
- "data": datasets and experimental protocol, 1 to 2 sentences
- "results": main quantitative results and comparison to prior work, 2 to 3 sentences
- "limitations": limitations, blind spots or compute cost, 1 to 2 sentences
- "relevance": why this paper deserves attention, 1 to 2 sentences
- "keywords": list of 4 to 8 keywords
- "relevance_score": integer from 0 to 10

Write every field in English. Report numbers exactly as they appear in the text.
If a piece of information is missing from the excerpt, write "not stated" rather than
guessing or inferring it.

--- PAPER ---
{content}
--- END PAPER ---"""

REQUIRED_KEYS = (
    "summary",
    "problem",
    "method",
    "data",
    "results",
    "limitations",
    "relevance",
    "keywords",
    "relevance_score",
)


def is_available(cfg: dict[str, Any]) -> bool:
    try:
        resp = requests.get(f"{cfg['url'].rstrip('/')}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def wait_until_available(cfg: dict[str, Any]) -> bool:
    """Poll Ollama, since the GPU machine may be off when the job triggers."""
    deadline = time.time() + int(cfg.get("wait_minutes", 0)) * 60
    while True:
        if is_available(cfg):
            return True
        if time.time() >= deadline:
            return False
        LOG.info("Ollama unreachable, retrying in 60s")
        time.sleep(60)


def _parse(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if raw.lower().startswith("json") else raw
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def summarize(content: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    payload = {
        "model": cfg["model"],
        "format": "json",
        "stream": False,
        "think": bool(cfg.get("think", False)),
        "options": {
            "num_ctx": int(cfg.get("num_ctx", 8192)),
            "temperature": float(cfg.get("temperature", 0.2)),
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(content=content)},
        ],
    }

    try:
        resp = requests.post(
            f"{cfg['url'].rstrip('/')}/api/chat",
            json=payload,
            timeout=int(cfg.get("timeout", 900)),
        )
        resp.raise_for_status()
        message = resp.json().get("message", {}).get("content", "")
    except (requests.RequestException, ValueError) as exc:
        LOG.warning("Ollama call failed: %s", exc)
        return None

    data = _parse(message)
    if not data:
        LOG.warning("Unparsable model output (%d chars)", len(message))
        return None

    for key in REQUIRED_KEYS:
        data.setdefault(key, "not stated")
    if isinstance(data.get("keywords"), str):
        data["keywords"] = [k.strip() for k in data["keywords"].split(",") if k.strip()]
    try:
        data["relevance_score"] = int(data["relevance_score"])
    except (TypeError, ValueError):
        data["relevance_score"] = 0
    return data
