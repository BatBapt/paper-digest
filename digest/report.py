"""HTML and Markdown report rendering."""
from __future__ import annotations

import datetime as dt
from typing import Any

from jinja2 import Template

HTML_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;">
<div style="max-width:760px;margin:0 auto;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1c1e21;line-height:1.55;">

  <h1 style="font-size:22px;margin:0 0 4px 0;">{{ title }}</h1>
  <p style="margin:0 0 20px 0;color:#606770;font-size:13px;">
    {{ period_start }} to {{ period_end }} &middot;
    {{ stats.candidates }} screened &middot;
    {{ stats.selected }} selected &middot;
    {{ stats.summarized }} read in full
  </p>

  <div style="background:#ffffff;border:1px solid #dcdfe4;border-radius:8px;padding:14px 18px;margin-bottom:24px;">
    <strong style="font-size:14px;">Contents</strong>
    <ol style="margin:8px 0 0 0;padding-left:20px;font-size:14px;">
    {% for paper in papers %}
      <li style="margin-bottom:4px;">
        <a href="#p{{ loop.index }}" style="color:#1a4fa0;text-decoration:none;">{{ paper.title }}</a>
        <span style="color:#606770;">({{ paper.theme }})</span>
      </li>
    {% endfor %}
    </ol>
  </div>

  {% for paper in papers %}
  <div id="p{{ loop.index }}" style="background:#ffffff;border:1px solid #dcdfe4;border-radius:8px;padding:18px;margin-bottom:18px;">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#8a8d91;margin-bottom:6px;">
      {{ paper.theme }} &middot; {{ paper.venue }} &middot; {{ paper.published }}
      {%- if paper.summary %} &middot; relevance {{ paper.summary.relevance_score }}/10{% endif %}
    </div>
    <h2 style="font-size:17px;margin:0 0 6px 0;">
      <a href="{{ paper.url }}" style="color:#1c1e21;text-decoration:none;">{{ loop.index }}. {{ paper.title }}</a>
    </h2>
    <p style="margin:0 0 12px 0;color:#606770;font-size:13px;">{{ paper.authors_short }}</p>

    {% if paper.summary %}
      <p style="margin:0 0 12px 0;font-size:14.5px;">{{ paper.summary.summary }}</p>
      <table style="width:100%;border-collapse:collapse;font-size:13.5px;">
        {% for label, value in paper.rows %}
        <tr>
          <td style="vertical-align:top;padding:5px 10px 5px 0;color:#606770;white-space:nowrap;width:110px;">{{ label }}</td>
          <td style="vertical-align:top;padding:5px 0;">{{ value }}</td>
        </tr>
        {% endfor %}
      </table>
      {% if paper.summary.keywords %}
      <p style="margin:12px 0 0 0;font-size:12.5px;color:#606770;">
        Keywords: {{ paper.summary.keywords | join(', ') }}
      </p>
      {% endif %}
    {% else %}
      <p style="margin:0 0 12px 0;font-size:14px;color:#606770;"><em>Automatic summary unavailable, original abstract below.</em></p>
      <p style="margin:0;font-size:14px;">{{ paper.abstract }}</p>
    {% endif %}

    <p style="margin:14px 0 0 0;font-size:13px;">
      <a href="{{ paper.url }}" style="color:#1a4fa0;">Page</a>
      {% if paper.pdf_url %} &middot; <a href="{{ paper.pdf_url }}" style="color:#1a4fa0;">PDF</a>{% endif %}
    </p>
  </div>
  {% endfor %}

  {% if not papers %}
  <p style="font-size:14px;">No paper passed the relevance threshold this week.</p>
  {% endif %}

  <p style="color:#8a8d91;font-size:12px;margin-top:28px;">
    Generated automatically on {{ generated_at }}. Sources: {{ stats.sources | join(', ') }}.
  </p>
</div>
</body>
</html>"""
)

ROW_LABELS = [
    ("Problem", "problem"),
    ("Method", "method"),
    ("Data", "data"),
    ("Results", "results"),
    ("Limitations", "limitations"),
    ("Why it matters", "relevance"),
]


def _prepare(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for paper in papers:
        item = dict(paper)
        authors = paper.get("authors", [])
        item["authors_short"] = ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else "")
        summary = paper.get("summary")
        item["rows"] = (
            [(label, summary.get(key, "")) for label, key in ROW_LABELS] if summary else []
        )
        prepared.append(item)
    return prepared


def render_html(papers: list[dict[str, Any]], stats: dict[str, Any], period: tuple[str, str]) -> str:
    return HTML_TEMPLATE.render(
        title=f"Research digest - week of {period[0]}",
        period_start=period[0],
        period_end=period[1],
        generated_at=dt.datetime.now().strftime("%d %b %Y at %H:%M"),
        papers=_prepare(papers),
        stats=stats,
    )


def render_markdown(
    papers: list[dict[str, Any]], stats: dict[str, Any], period: tuple[str, str]
) -> str:
    lines = [
        f"# Research digest - week of {period[0]}",
        "",
        f"{period[0]} to {period[1]} | {stats['candidates']} screened "
        f"| {stats['selected']} selected | {stats['summarized']} read in full",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        authors = paper.get("authors", [])
        lines += [
            f"## {index}. {paper['title']}",
            "",
            f"- Topic: {paper.get('theme', '')}",
            f"- Source: {paper.get('venue') or paper.get('source', '')} ({paper.get('published', '')})",
            f"- Authors: {', '.join(authors[:5])}{' et al.' if len(authors) > 5 else ''}",
            f"- Link: {paper.get('url', '')}",
        ]
        if paper.get("pdf_url"):
            lines.append(f"- PDF: {paper['pdf_url']}")
        summary = paper.get("summary")
        lines.append("")
        if summary:
            lines += [summary.get("summary", ""), ""]
            for label, key in ROW_LABELS:
                lines.append(f"**{label}**: {summary.get(key, '')}")
            keywords = summary.get("keywords") or []
            if keywords:
                lines.append(f"**Keywords**: {', '.join(keywords)}")
            lines.append(f"**Relevance**: {summary.get('relevance_score', 0)}/10")
        else:
            lines.append(paper.get("abstract", ""))
        lines += ["", "---", ""]
    return "\n".join(lines)
