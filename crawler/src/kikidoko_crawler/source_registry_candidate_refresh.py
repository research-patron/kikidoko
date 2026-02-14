from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REGISTRY_PATH = "crawler/config/source_registry_low_count.json"
DEFAULT_CANDIDATE_OUT = "crawler/source_registry_candidate_refresh.csv"
DEFAULT_BACKLOG_OUT = "crawler/source_registry_query_only_backlog.csv"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create source registry candidate/backlog CSVs from preview output."
    )
    parser.add_argument(
        "--preview-csv",
        required=True,
        help="source_registry_sync preview CSV path.",
    )
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"Registry JSON path (default: {DEFAULT_REGISTRY_PATH}).",
    )
    parser.add_argument(
        "--candidate-out",
        default=DEFAULT_CANDIDATE_OUT,
        help=f"Candidate output CSV path (default: {DEFAULT_CANDIDATE_OUT}).",
    )
    parser.add_argument(
        "--backlog-out",
        default=DEFAULT_BACKLOG_OUT,
        help=f"Query-only backlog CSV path (default: {DEFAULT_BACKLOG_OUT}).",
    )
    return parser.parse_args(list(argv))


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return WORKSPACE_ROOT / path


def parse_normalized_count(value: str) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return 0


def classify_action(fetch_status: str, normalized_count: int) -> tuple[str, str]:
    if fetch_status == "query_only":
        return (
            "implement_source",
            "公式URLと取得方式(parser_type)を確定してsource_registry_low_count.jsonを更新",
        )
    if fetch_status == "ok" and normalized_count > 0:
        return (
            "sync_now",
            "kikidoko-source-registry-syncを都道府県または20機関単位で分割実行",
        )
    if fetch_status == "ok":
        return (
            "verify_url",
            "URL/selector/リンクパターンを再確認してdry-runを再実行",
        )
    if fetch_status.startswith("error:"):
        return (
            "verify_url",
            "取得エラー解消後にdry-runを再実行（DNS/ネットワーク/HTML変更を確認）",
        )
    return ("verify_url", "fetch_statusを確認して設定を見直す")


def load_registry_map(registry_path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = payload.get("entries", []) if isinstance(payload, dict) else payload
    mapping: dict[str, dict[str, Any]] = {}
    if not isinstance(entries, list):
        return mapping
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", "")).strip()
        if not key:
            continue
        mapping[key] = entry
    return mapping


def join_query_keywords(entry: dict[str, Any]) -> str:
    keywords = entry.get("query_keywords", [])
    if isinstance(keywords, list):
        return " | ".join(str(v).strip() for v in keywords if str(v).strip())
    if isinstance(keywords, str):
        return keywords.strip()
    return ""


def build_query_only_status(official_url: str, parser_type: str) -> str:
    if parser_type != "query_only":
        return "ready_for_sync"
    if official_url:
        return "needs_parser_implementation"
    return "needs_url_and_parser"


def run(args: argparse.Namespace) -> int:
    preview_path = resolve_workspace_path(args.preview_csv)
    registry_path = resolve_workspace_path(args.registry)
    candidate_out_path = resolve_workspace_path(args.candidate_out)
    backlog_out_path = resolve_workspace_path(args.backlog_out)

    if not preview_path.exists():
        raise FileNotFoundError(f"Preview CSV not found: {preview_path}")
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry JSON not found: {registry_path}")

    registry_map = load_registry_map(registry_path)

    preview_rows: list[dict[str, str]] = []
    with preview_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            preview_rows.append({k: (v or "") for k, v in row.items()})

    candidate_rows: list[dict[str, str]] = []
    backlog_rows: list[dict[str, str]] = []

    for row in preview_rows:
        key = row.get("registry_key", "").strip()
        org_name = row.get("org_name", "").strip()
        prefecture = row.get("prefecture", "").strip()
        fetch_status = row.get("fetch_status", "").strip()
        normalized_count = parse_normalized_count(row.get("normalized_count", "0"))
        action, next_step = classify_action(fetch_status, normalized_count)
        candidate_rows.append(
            {
                "org_name": org_name,
                "prefecture": prefecture,
                "registry_key": key,
                "fetch_status": fetch_status,
                "normalized_count": str(normalized_count),
                "action": action,
                "next_step": next_step,
            }
        )

        if fetch_status != "query_only":
            continue

        entry = registry_map.get(key, {})
        parser_type = str(entry.get("parser_type", "query_only")).strip() or "query_only"
        source_handler = str(entry.get("source_handler", "")).strip()
        target_source = source_handler or key
        official_url = str(entry.get("url", "")).strip()
        backlog_rows.append(
            {
                "org_name": org_name,
                "prefecture": prefecture,
                "query_keywords": join_query_keywords(entry),
                "official_url": official_url,
                "parser_type": parser_type,
                "target_source": target_source,
                "status": build_query_only_status(official_url, parser_type),
                "owner_note": "",
            }
        )

    # Action order keeps immediate-sync rows at top.
    action_rank = {"sync_now": 0, "implement_source": 1, "verify_url": 2}
    candidate_rows.sort(
        key=lambda row: (
            action_rank.get(row["action"], 9),
            row["prefecture"],
            row["org_name"],
        )
    )
    backlog_rows.sort(key=lambda row: (row["prefecture"], row["org_name"]))

    candidate_out_path.parent.mkdir(parents=True, exist_ok=True)
    with candidate_out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "org_name",
                "prefecture",
                "registry_key",
                "fetch_status",
                "normalized_count",
                "action",
                "next_step",
            ],
        )
        writer.writeheader()
        writer.writerows(candidate_rows)

    backlog_out_path.parent.mkdir(parents=True, exist_ok=True)
    with backlog_out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "org_name",
                "prefecture",
                "query_keywords",
                "official_url",
                "parser_type",
                "target_source",
                "status",
                "owner_note",
            ],
        )
        writer.writeheader()
        writer.writerows(backlog_rows)

    sync_now_count = sum(1 for row in candidate_rows if row["action"] == "sync_now")
    implement_count = sum(1 for row in candidate_rows if row["action"] == "implement_source")
    verify_count = sum(1 for row in candidate_rows if row["action"] == "verify_url")
    print(
        "Done. "
        f"candidate_rows={len(candidate_rows)} "
        f"sync_now={sync_now_count} "
        f"implement_source={implement_count} "
        f"verify_url={verify_count}"
    )
    print(f"Candidate CSV: {candidate_out_path}")
    print(f"Query-only backlog CSV: {backlog_out_path}")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
