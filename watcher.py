"""URL watcher thread — polls a URL and sets a threading.Event when content changes."""

import hashlib
import threading
import time
import urllib.request
from datetime import datetime, time as dtime
from typing import Optional


def _fetch_body(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ufo-watcher/0.1 (github.com/torusk/ufo-watcher)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _extract(body: bytes, selector: Optional[str], ignore_patterns: list[str]) -> bytes:
    """Apply optional CSS selector and ignore_patterns to narrow the hash target."""
    if selector:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, "html.parser")
            nodes = soup.select(selector)
            text = "\n".join(n.get_text() for n in nodes)
        except Exception:
            text = body.decode("utf-8", errors="replace")
    else:
        text = body.decode("utf-8", errors="replace")

    if ignore_patterns:
        lines = [
            line for line in text.splitlines()
            if not any(pat in line for pat in ignore_patterns)
        ]
        text = "\n".join(lines)

    return text.encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_active(schedule: dict) -> bool:
    """Return True if monitoring should run now, given a schedule config dict."""
    if not schedule.get("enabled", False):
        return True
    now = datetime.now()
    if schedule.get("weekdays_only", False) and now.weekday() >= 5:
        return False
    start_str = schedule.get("start", "00:00")
    end_str = schedule.get("end", "23:59")
    start = dtime(*map(int, start_str.split(":")))
    end = dtime(*map(int, end_str.split(":")))
    return start <= now.time() <= end


class Watcher(threading.Thread):
    """Background thread that polls a URL and signals *alert_event* on change."""

    def __init__(
        self,
        url: str,
        interval_sec: int,
        alert_event: threading.Event,
        selector: Optional[str] = None,
        ignore_patterns: Optional[list[str]] = None,
        schedule: Optional[dict] = None,
    ):
        super().__init__(daemon=True)
        self.url = url
        self.interval_sec = interval_sec
        self.alert_event = alert_event
        self.selector = selector
        self.ignore_patterns = ignore_patterns or []
        self.schedule = schedule or {}
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        prev_hash: Optional[str] = None

        while not self._stop_event.is_set():
            if not _is_active(self.schedule):
                self._stop_event.wait(timeout=30)
                continue

            try:
                body = _fetch_body(self.url)
                target = _extract(body, self.selector, self.ignore_patterns)
                current_hash = _sha256(target)

                if prev_hash is None:
                    # First run: record baseline, no alert
                    prev_hash = current_hash
                    print(f"[watcher] baseline recorded: {current_hash[:8]}…")
                elif current_hash != prev_hash:
                    print(f"[watcher] change detected! {prev_hash[:8]}… → {current_hash[:8]}…")
                    prev_hash = current_hash
                    self.alert_event.set()

            except Exception as exc:
                print(f"[watcher] error: {exc}")

            self._stop_event.wait(timeout=self.interval_sec)
