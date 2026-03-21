#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = "frontend/dist/update-history.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}
    if not isinstance(data, dict):
        return {"entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []
    return data


def save_history(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_entry(timestamp: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "event": "hosting_deploy",
        "summary": "Firebase Hosting をデプロイしました（kikidoko.web.app）",
        "stats": {
            "project": "kikidoko",
            "target": "hosting",
            "site_url": "https://kikidoko.web.app",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Append deploy history entry before Firebase Hosting deploy.")
    parser.add_argument("--history", default=DEFAULT_HISTORY_PATH, help="Path to update history JSON file.")
    args = parser.parse_args()

    history_path = Path(args.history).resolve()
    current = load_history(history_path)
    entries = current.get("entries")
    if not isinstance(entries, list):
        entries = []

    timestamp = utc_now_iso()
    entries.insert(0, build_entry(timestamp))
    current["entries"] = entries
    current["updated_at"] = timestamp

    save_history(history_path, current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
