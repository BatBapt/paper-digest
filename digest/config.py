"""Configuration loading and runtime paths."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(os.environ.get("VEILLE_CONFIG", "config.yaml"))
DATA_DIR = Path(os.environ.get("VEILLE_DATA", "./data"))
DOTENV_PATH = Path(".env")


def _load_dotenv(path: Path = DOTENV_PATH) -> None:
    """Best effort .env loader for local runs (Docker gets its env from env_file)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load(path: Path | None = None) -> dict[str, Any]:
    _load_dotenv()
    path = path or CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    cfg.setdefault("mail", {})
    cfg["mail"]["user"] = os.environ.get("SMTP_USER", "")
    cfg["mail"]["password"] = os.environ.get("SMTP_PASSWORD", "")
    cfg["mail"]["to"] = [
        addr.strip()
        for addr in os.environ.get("MAIL_TO", os.environ.get("SMTP_USER", "")).split(",")
        if addr.strip()
    ]
    cfg.setdefault("sources", {}).setdefault("openalex", {})["mailto"] = os.environ.get(
        "OPENALEX_MAILTO", os.environ.get("SMTP_USER", "")
    )
    return cfg


def paths() -> dict[str, Path]:
    dirs = {
        "data": DATA_DIR,
        "pdf": DATA_DIR / "pdf",
        "reports": DATA_DIR / "reports",
        "db": DATA_DIR / "state.sqlite",
    }
    for key in ("data", "pdf", "reports"):
        dirs[key].mkdir(parents=True, exist_ok=True)
    return dirs
