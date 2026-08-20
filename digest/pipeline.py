"""End to end pipeline: collect, select, read, summarize, report, send."""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any

from . import config, extract, mailer, report, scoring, summarize
from .sources import arxiv, openalex
from .store import Store

LOG = logging.getLogger(__name__)


def collect(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    lookback = int(cfg["window"]["lookback_days"])
    papers: list[dict[str, Any]] = []
    used: list[str] = []

    src = cfg.get("sources", {})
    if src.get("arxiv", {}).get("enabled"):
        papers += arxiv.fetch(src["arxiv"], lookback)
        used.append("arXiv")
    if src.get("openalex", {}).get("enabled"):
        papers += openalex.fetch(src["openalex"], lookback)
        used.append("OpenAlex")

    # Cross source dedup on normalized title
    unique: dict[str, dict[str, Any]] = {}
    for paper in papers:
        key = "".join(ch for ch in paper["title"].lower() if ch.isalnum())[:120]
        if key and key not in unique:
            unique[key] = paper
    return list(unique.values()), used


def select(
    papers: list[dict[str, Any]], cfg: dict[str, Any], store: Store
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selection_cfg = cfg["selection"]
    themes = cfg.get("themes", {})
    fresh = [p for p in papers if not store.is_seen(p["uid"])]

    for paper in fresh:
        paper["score"], paper["matched"] = scoring.score(paper, cfg.get("scoring", {}))
        paper["theme"] = scoring.theme(paper, themes)

    ranked = [p for p in fresh if p["score"] >= int(selection_cfg.get("min_score", 0))]
    ranked.sort(key=lambda p: p.get("published", ""), reverse=True)
    ranked.sort(key=lambda p: p["score"], reverse=True)
    selected = ranked[: int(selection_cfg.get("max_papers", 15))]
    return selected, fresh


def enrich(selected: list[dict[str, Any]], cfg: dict[str, Any]) -> int:
    """Download, parse and summarize each selected paper. Returns success count."""
    paths = config.paths()
    ex_cfg = cfg["extraction"]
    ollama_cfg = cfg["ollama"]
    download = bool(cfg["selection"].get("download_pdf", True))
    ok = 0

    if not summarize.wait_until_available(ollama_cfg):
        LOG.error("Ollama unavailable, falling back to abstracts only")
        return 0

    for index, paper in enumerate(selected, start=1):
        LOG.info("[%d/%d] %s", index, len(selected), paper["title"][:80])
        body = ""
        if download:
            pdf_path = extract.download_pdf(paper, paths["pdf"], int(ex_cfg.get("pdf_timeout", 90)))
            if pdf_path:
                body = extract.clean(
                    extract.pdf_to_text(pdf_path, int(ex_cfg.get("max_pages", 40)))
                )
                paper["full_text"] = bool(body)

        content = extract.build_llm_input(paper, body, int(ex_cfg.get("max_chars", 18000)))
        started = time.time()
        paper["summary"] = summarize.summarize(content, ollama_cfg)
        if paper["summary"]:
            ok += 1
            LOG.info("    resume genere en %.0fs", time.time() - started)
        else:
            LOG.warning("    resume indisponible")
        time.sleep(1)

    return ok


def run(cfg: dict[str, Any] | None = None, send_mail: bool = True) -> dict[str, Any]:
    cfg = cfg or config.load()
    paths = config.paths()
    store = Store(paths["db"])
    run_id = store.start_run()

    today = dt.date.today()
    period = (
        (today - dt.timedelta(days=int(cfg["window"]["lookback_days"]))).strftime("%d %b %Y"),
        today.strftime("%d %b %Y"),
    )

    try:
        papers, sources_used = collect(cfg)
        LOG.info("Collected %d unique papers", len(papers))

        selected, fresh = select(papers, cfg, store)
        LOG.info("Selected %d papers out of %d fresh", len(selected), len(fresh))

        summarized = enrich(selected, cfg) if selected else 0

        stats = {
            "candidates": len(fresh),
            "selected": len(selected),
            "summarized": summarized,
            "sources": sources_used,
        }

        html = report.render_html(selected, stats, period)
        markdown = report.render_markdown(selected, stats, period)

        stamp = today.strftime("%Y-%m-%d")
        (paths["reports"] / f"veille-{stamp}.html").write_text(html, encoding="utf-8")
        (paths["reports"] / f"veille-{stamp}.md").write_text(markdown, encoding="utf-8")

        sent = False
        if send_mail:
            subject = f"{cfg['mail'].get('subject_prefix', 'Veille scientifique')} - {period[0]}"
            sent = mailer.send(subject, html, markdown, cfg["mail"])

        for paper in fresh:
            store.mark_seen(paper)
        store.prune()

        details = {**stats, "mail_sent": sent, "report": f"veille-{stamp}.html"}
        store.end_run(run_id, "ok", details)
        return details

    except Exception as exc:  # noqa: BLE001 - a scheduled job must record its failures
        LOG.exception("Run failed")
        store.end_run(run_id, "error", {"error": str(exc)})
        raise
