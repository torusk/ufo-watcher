"""UFO Watcher — entry point."""

import json
import sys
import threading
from pathlib import Path

from watcher import Watcher
from ufo import run_app

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[error] config.json not found. Copy config.example.json and edit it.")
        sys.exit(1)
    with CONFIG_PATH.open() as f:
        cfg = json.load(f)
    if "url" not in cfg or "interval_sec" not in cfg:
        print("[error] config.json must contain 'url' and 'interval_sec'.")
        sys.exit(1)
    return cfg


def main():
    cfg = load_config()

    alert_event = threading.Event()

    watcher = Watcher(
        url=cfg["url"],
        interval_sec=int(cfg["interval_sec"]),
        alert_event=alert_event,
        selector=cfg.get("selector"),
        ignore_patterns=cfg.get("ignore_patterns", []),
        schedule=cfg.get("schedule", {}),
    )
    watcher.start()
    print(f"[ufo-watcher] monitoring {cfg['url']} every {cfg['interval_sec']}s")

    try:
        run_app(alert_event)
    finally:
        watcher.stop()


if __name__ == "__main__":
    main()
