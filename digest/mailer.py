"""Email delivery over SMTP (Gmail app password)."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

LOG = logging.getLogger(__name__)


def send(subject: str, html: str, markdown: str, cfg: dict[str, Any]) -> bool:
    if not cfg.get("enabled", True):
        LOG.info("Mail disabled by config")
        return False
    if not cfg.get("user") or not cfg.get("password") or not cfg.get("to"):
        LOG.error("Missing SMTP credentials or recipient")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = cfg["user"]
    message["To"] = ", ".join(cfg["to"])
    message.set_content(markdown)
    message.add_alternative(html, subtype="html")

    if cfg.get("attach_markdown", True):
        message.add_attachment(
            markdown.encode("utf-8"),
            maintype="text",
            subtype="markdown",
            filename=subject.replace(" ", "_").replace("/", "-") + ".md",
        )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg["smtp_port"]), context=context) as server:
            server.login(cfg["user"], cfg["password"])
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        LOG.error("Mail delivery failed: %s", exc)
        return False

    LOG.info("Report sent to %s", message["To"])
    return True
