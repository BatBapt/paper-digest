"""CLI: one shot run, scheduled service, or diagnostics."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, mailer, pipeline, summarize
from .store import Store

LOG = logging.getLogger("veille")

_lock = threading.Lock()
_running = False


def _run_guarded(send_mail: bool = True) -> None:
    global _running
    if not _lock.acquire(blocking=False):
        LOG.warning("A run is already in progress")
        return
    _running = True
    try:
        pipeline.run(send_mail=send_mail)
    except Exception:  # noqa: BLE001 - keep the service alive
        LOG.exception("Run aborted")
    finally:
        _running = False
        _lock.release()


class Handler(BaseHTTPRequestHandler):
    token = ""

    def _authorized(self) -> bool:
        if not self.token:
            return True
        if self.headers.get("X-Token") == self.token:
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._authorized():
            return
        if self.path.rstrip("/") != "/run":
            self._json(404, {"error": "not found"})
            return
        if _running:
            self._json(409, {"status": "already_running"})
            return
        threading.Thread(target=_run_guarded, daemon=True).start()
        self._json(202, {"status": "started"})

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if not self._authorized():
            return
        if self.path.rstrip("/") != "/status":
            self._json(404, {"error": "not found"})
            return
        store = Store(config.paths()["db"])
        self._json(200, {"running": _running, "last_run": store.last_run()})

    def log_message(self, fmt: str, *args) -> None:
        LOG.debug("http %s", fmt % args)


def serve(cfg: dict) -> None:
    http_cfg = cfg.get("http", {})
    if http_cfg.get("enabled", True):
        Handler.token = str(http_cfg.get("token") or "")
        server = ThreadingHTTPServer(
            (http_cfg.get("host", "0.0.0.0"), int(http_cfg.get("port", 8137))), Handler
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        LOG.info("HTTP trigger on %s:%s", http_cfg.get("host"), http_cfg.get("port"))

    sched = cfg.get("schedule", {})
    weekday = int(sched.get("weekday", 0))
    hour = int(sched.get("hour", 7))
    minute = int(sched.get("minute", 0))
    LOG.info("Scheduled weekly on weekday %d at %02d:%02d", weekday, hour, minute)

    last_fired: dt.date | None = None
    while True:
        now = dt.datetime.now()
        if (
            now.weekday() == weekday
            and now.hour == hour
            and now.minute == minute
            and last_fired != now.date()
        ):
            last_fired = now.date()
            LOG.info("Scheduled run triggered")
            _run_guarded()
        time.sleep(20)


def main() -> None:
    parser = argparse.ArgumentParser(prog="veille")
    parser.add_argument(
        "command", choices=["run", "serve", "test-mail", "test-ollama"], nargs="?", default="serve"
    )
    parser.add_argument("--no-mail", action="store_true", help="build the report without sending it")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    cfg = config.load()

    if args.command == "run":
        result = pipeline.run(cfg, send_mail=not args.no_mail)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "serve":
        serve(cfg)
    elif args.command == "test-mail":
        ok = mailer.send(
            "Research digest - SMTP test",
            "<p>SMTP configuration test.</p>",
            "SMTP configuration test.",
            cfg["mail"],
        )
        print("ok" if ok else "failed")
    elif args.command == "test-ollama":
        print("ok" if summarize.is_available(cfg["ollama"]) else "unreachable")


if __name__ == "__main__":
    main()
