#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from build_update_info_manifest import DEFAULT_OUTPUT_PATH, DEFAULT_SOURCE_DIR, load_notes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify update info source and manifest before deploy.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def fail(message: str) -> int:
    raise SystemExit(message)


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    manifest_path = Path(args.manifest).resolve()

    entries = load_notes(source_dir)
    if not entries:
        fail("update_info_predeploy_failed:no_source_entries")

    if not manifest_path.exists():
        fail("update_info_predeploy_failed:manifest_missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    latest_manifest = manifest.get("latest") or {}
    latest_entry = entries[0]

    latest_published = datetime.fromisoformat(latest_entry.published_at).astimezone(ZoneInfo("Asia/Tokyo"))
    today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    if latest_published.date() != today_jst:
        fail("update_info_predeploy_failed:latest_entry_not_today_jst")

    required = ("title", "published_at", "summary", "version_label", "status")
    for field in required:
        if not latest_manifest.get(field):
            fail(f"update_info_predeploy_failed:manifest_missing_{field}")

    if latest_manifest.get("id") != latest_entry.slug:
        fail("update_info_predeploy_failed:manifest_latest_mismatch")

    manifest_mtime = manifest_path.stat().st_mtime
    newest_source_mtime = max(entry.source_path.stat().st_mtime for entry in entries)
    if manifest_mtime < newest_source_mtime:
        fail("update_info_predeploy_failed:manifest_stale")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
