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
        print("[error] config.json not found. Copy config.example.json and edit it.")
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

    # watcher_holder[0] lets the URL-change callback swap the watcher at runtime
    watcher_holder = [Watcher(
        url=cfg["url"],
        interval_sec=int(cfg["interval_sec"]),
        alert_event=alert_event,
        selector=cfg.get("selector"),
        ignore_patterns=cfg.get("ignore_patterns", []),
        schedule=cfg.get("schedule", {}),
    )]
    watcher_holder[0].start()
    print(f"[ufo-watcher] monitoring {cfg['url']} every {cfg['interval_sec']}s")

    def on_url_change(new_url: str):
        # Persist to config.json
        data = json.loads(CONFIG_PATH.read_text())
        data["url"] = new_url
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

        # Restart watcher with new URL (keep all other settings)
        old = watcher_holder[0]
        old.stop()
        new_watcher = Watcher(
            url=new_url,
            interval_sec=int(data["interval_sec"]),
            alert_event=alert_event,
            selector=data.get("selector"),
            ignore_patterns=data.get("ignore_patterns", []),
            schedule=data.get("schedule", {}),
        )
        new_watcher.start()
        watcher_holder[0] = new_watcher
        alert_event.clear()
        print(f"[ufo-watcher] now monitoring {new_url}")

    fly_duration = float(cfg.get("fly_duration_sec", 5))
    try:
        run_app(
            alert_event,
            fly_duration=fly_duration,
            current_url=cfg["url"],
            on_url_change=on_url_change,
        )
    finally:
        watcher_holder[0].stop()


if __name__ == "__main__":
    main()
