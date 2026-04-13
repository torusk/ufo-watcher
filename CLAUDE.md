# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**UFO Watcher** — A lightweight macOS desktop app that monitors a URL for content changes and animates a floating UFO when changes are detected. Click the UFO to dismiss the alert. Intended for public release on GitHub.

## Setup & Run

```bash
# Install dependencies
uv sync

# Run
uv run python main.py
```

## Configuration

Edit `config.json` before running:

```json
{
  "url": "https://example.com/news",
  "interval_sec": 60,
  "selector": "#main-content",        // optional: CSS selector to narrow scope
  "ignore_patterns": ["timestamp"],    // optional: lines to exclude from hash
  "schedule": {
    "enabled": false,
    "weekdays_only": true,
    "start": "09:00",
    "end": "15:30"
  }
}
```

Only `url` and `interval_sec` are required. `schedule` is disabled by default.

## Architecture

**1 process, 2 threads:**

```
Main thread (NSTimer @ 60fps)         Watcher thread
──────────────────────────            ──────────────
check event.is_set()         ←─ YES ── hash changed → event.set()
  → flying animation                  │
check click                           sleep(interval_sec)
  → event.clear() → idle              └─ loop
```

- **`main.py`** — Entry point: loads `config.json`, starts watcher thread, runs Cocoa app loop
- **`ufo.py`** — macOS window + animation via `pyobjc-framework-Cocoa`
  - `NSWindow` with `NSWindowStyleMaskBorderless`, fully transparent (`clearColor`)
  - Always-on-top (`setLevel_(25)`), spans all Spaces
  - Idle: sin-wave hover (±2–3px). Alert: Lissajous-curve flight across screen
  - Mouse passthrough when idle (`setIgnoresMouseEvents_(True)`); click-to-dismiss when flying
- **`watcher.py`** — URL polling loop: `urllib.request` GET → `hashlib.sha256` of body → `threading.Event`
  - First run records baseline hash without triggering alert
  - Optional `selector` (BeautifulSoup CSS select) and `ignore_patterns` (line filtering) for noise reduction

## Tech Stack

- Python 3.9+, managed with `uv`
- `pyobjc-framework-Cocoa` — only external dependency
- Standard library only for networking: `urllib.request`, `hashlib`, `threading`, `json`
- **macOS only** (pyobjc dependency)

## Development Order (from spec)

1. UFO display: idle hover + Lissajous flight + click detection
2. `watcher.py`: fetch → hash → Event signal
3. Test with own site (post article → UFO flies → click stops)
4. Test with TDnet URL
5. Write README.md → publish to GitHub
