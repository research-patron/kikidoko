#!/usr/bin/env python3
"""Manual curation guard session helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_REVIEWER = "codex-manual"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_queue_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def row_key(row: Dict[str, Any], index: int) -> str:
    doc_id = normalize_text(row.get("doc_id"))
    equipment_id = normalize_text(row.get("equipment_id"))
    if doc_id and equipment_id:
        return f"{doc_id}::{equipment_id}"
    if doc_id:
        return f"{doc_id}::"
    if equipment_id:
        return f"::{equipment_id}"
    return f"row-{index:06d}"


def queue_identity(rows: List[Dict[str, Any]]) -> Tuple[List[str], str]:
    keys = [row_key(row, idx) for idx, row in enumerate(rows)]
    joined = "\n".join(keys).encode("utf-8")
    digest = hashlib.sha256(joined).hexdigest()
    return keys, digest


def extract_reviewer(row: Dict[str, Any]) -> str:
    manual = row.get("manual_content_v1") if isinstance(row.get("manual_content_v1"), dict) else {}
    review = manual.get("review") if isinstance(manual.get("review"), dict) else {}
    reviewer = normalize_text(review.get("reviewer"))
    if reviewer:
        return reviewer
    return normalize_text(row.get("reviewer"))


def command_start(args: argparse.Namespace) -> int:
    root = Path.cwd()
    queue_path = (root / args.queue).resolve()
    snapshot_path = (root / args.snapshot).resolve()
    agents_path = (root / args.agents).resolve()
    reviewer = normalize_text(args.reviewer) or DEFAULT_REVIEWER
    batch_id = normalize_text(args.batch_id)
    if not batch_id:
        raise ValueError("batch_id is required")

    if not queue_path.exists():
        raise FileNotFoundError(f"Queue not found: {queue_path}")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    if not agents_path.exists():
        raise FileNotFoundError(f"AGENTS not found: {agents_path}")

    rows = load_queue_rows(queue_path)
    keys, key_hash = queue_identity(rows)

    target_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        target_rows.append(
            {
                "row_key": row_key(row, idx),
                "doc_id": normalize_text(row.get("doc_id")),
                "equipment_id": normalize_text(row.get("equipment_id")),
                "name": normalize_text(row.get("name")),
                "papers_count": int(row.get("papers_count") or 0),
            }
        )

    now = utc_now_iso()
    session_path = (root / args.session).resolve() if args.session else (root / f"tools/manual_guard_session_{batch_id}.json").resolve()
    payload = {
        "version": "manual_guard_v1",
        "batch_id": batch_id,
        "status": "active",
        "reviewer": reviewer,
        "created_at": now,
        "updated_at": now,
        "closed_at": "",
        "paths": {
            "agents": str(agents_path),
            "queue": str(queue_path),
            "snapshot": str(snapshot_path),
            "session": str(session_path),
        },
        "hashes": {
            "agents_sha256": sha256_file(agents_path),
            "snapshot_sha256_at_start": sha256_file(snapshot_path),
            "queue_sha256_at_start": sha256_file(queue_path),
            "queue_row_keys_sha256": key_hash,
        },
        "queue": {
            "target_count": len(rows),
            "target_row_keys": keys,
            "target_rows": target_rows,
        },
        "stats": {
            "verify_pass_count": 0,
            "verify_fail_count": 0,
        },
        "events": [
            {
                "at": now,
                "event": "start",
                "details": {
                    "target_count": len(rows),
                },
            }
        ],
    }
    save_json(session_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    root = Path.cwd()
    session_path = (root / args.session).resolve()
    session = load_json(session_path, {})
    if not isinstance(session, dict):
        raise ValueError(f"Invalid session: {session_path}")
    if normalize_text(session.get("status")).lower() != "active":
        raise ValueError("Session is not active")

    session_paths = session.get("paths") if isinstance(session.get("paths"), dict) else {}
    queue_path = (root / args.queue).resolve() if args.queue else Path(str(session_paths.get("queue") or "")).resolve()
    snapshot_path = (root / args.snapshot).resolve() if args.snapshot else Path(str(session_paths.get("snapshot") or "")).resolve()
    agents_path = (root / args.agents).resolve() if args.agents else Path(str(session_paths.get("agents") or "")).resolve()

    issues: List[str] = []
    details: Dict[str, Any] = {}

    if not agents_path.exists():
        issues.append("agents_not_found")
    else:
        expected_agents_hash = normalize_text((session.get("hashes") or {}).get("agents_sha256"))
        current_agents_hash = sha256_file(agents_path)
        details["agents_sha256_current"] = current_agents_hash
        if expected_agents_hash and current_agents_hash != expected_agents_hash:
            issues.append("agents_hash_mismatch")

    if not queue_path.exists():
        issues.append("queue_not_found")
        rows: List[Dict[str, Any]] = []
    else:
        rows = load_queue_rows(queue_path)
        details["queue_sha256_current"] = sha256_file(queue_path)

    if snapshot_path.exists():
        details["snapshot_sha256_current"] = sha256_file(snapshot_path)

    target = session.get("queue") if isinstance(session.get("queue"), dict) else {}
    target_keys = target.get("target_row_keys") if isinstance(target.get("target_row_keys"), list) else []
    target_set = {normalize_text(v) for v in target_keys if normalize_text(v)}

    current_keys = [row_key(row, idx) for idx, row in enumerate(rows)]
    current_set = set(current_keys)
    details["queue_rows_current"] = len(current_keys)
    details["queue_rows_target"] = int(target.get("target_count") or 0)

    if len(current_set) != len(current_keys):
        issues.append("queue_row_key_duplicated")
    unknown_keys = sorted([k for k in current_set if k not in target_set])
    if unknown_keys:
        issues.append("queue_contains_unknown_row")
        details["unknown_row_keys"] = unknown_keys[:20]
    if len(current_keys) > int(target.get("target_count") or 0):
        issues.append("queue_row_count_exceeds_target")

    reviewer_expected = normalize_text(args.reviewer) or normalize_text(session.get("reviewer")) or DEFAULT_REVIEWER
    mismatch_rows: List[str] = []
    for idx, row in enumerate(rows):
        reviewer = extract_reviewer(row)
        if reviewer != reviewer_expected:
            mismatch_rows.append(row_key(row, idx))
    if mismatch_rows:
        issues.append("reviewer_mismatch")
        details["reviewer_mismatch_row_keys"] = mismatch_rows[:20]

    status = "PASS" if not issues else "FAIL"
    now = utc_now_iso()
    result = {
        "status": status,
        "session": str(session_path),
        "batch_id": normalize_text(session.get("batch_id")),
        "reviewer_expected": reviewer_expected,
        "issues": issues,
        "details": details,
        "verified_at": now,
    }

    stats = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    stats["verify_pass_count"] = int(stats.get("verify_pass_count") or 0) + (1 if status == "PASS" else 0)
    stats["verify_fail_count"] = int(stats.get("verify_fail_count") or 0) + (1 if status == "FAIL" else 0)
    session["stats"] = stats
    session["updated_at"] = now
    events = session.get("events") if isinstance(session.get("events"), list) else []
    events.append(
        {
            "at": now,
            "event": "verify",
            "details": {
                "status": status,
                "issues": issues,
            },
        }
    )
    session["events"] = events
    if not args.no_write:
        save_json(session_path, session)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


def read_report_status(path: Path) -> str:
    payload = load_json(path, {})
    if isinstance(payload, dict):
        return normalize_text(payload.get("status")).upper()
    return ""


def command_close(args: argparse.Namespace) -> int:
    root = Path.cwd()
    session_path = (root / args.session).resolve()
    session = load_json(session_path, {})
    if not isinstance(session, dict):
        raise ValueError(f"Invalid session: {session_path}")
    if normalize_text(session.get("status")).lower() != "active":
        raise ValueError("Session is not active")

    issues: List[str] = []
    evidence: Dict[str, Any] = {}

    stats = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    if int(stats.get("verify_pass_count") or 0) <= 0:
        issues.append("verify_not_passed")
    evidence["verify_pass_count"] = int(stats.get("verify_pass_count") or 0)

    audit_path = (root / args.audit_report).resolve()
    if not audit_path.exists():
        issues.append("audit_report_not_found")
    else:
        audit_status = read_report_status(audit_path)
        evidence["audit_status"] = audit_status
        if audit_status != "PASS":
            issues.append("audit_not_pass")

    req_status = normalize_text(args.requirement_status).upper()
    evidence["requirement_status"] = req_status
    if req_status != "PASS":
        issues.append("requirement_not_pass")

    ui_status = normalize_text(args.ui_status).upper()
    evidence["ui_status"] = ui_status
    if ui_status != "PASS":
        issues.append("ui_not_pass")

    now = utc_now_iso()
    status = "PASS" if not issues else "FAIL"
    session["updated_at"] = now
    events = session.get("events") if isinstance(session.get("events"), list) else []
    events.append(
        {
            "at": now,
            "event": "close",
            "details": {
                "status": status,
                "issues": issues,
                "evidence": evidence,
            },
        }
    )
    session["events"] = events

    if status == "PASS":
        session["status"] = "closed"
        session["closed_at"] = now
    save_json(session_path, session)

    result = {
        "status": status,
        "session": str(session_path),
        "issues": issues,
        "evidence": evidence,
        "closed_at": now if status == "PASS" else "",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual guard for codex-manual curation workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a guard session")
    p_start.add_argument("--batch-id", required=True)
    p_start.add_argument("--queue", default="tools/manual_curation_queue_next100.jsonl")
    p_start.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    p_start.add_argument("--agents", default="AGENTS.md")
    p_start.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    p_start.add_argument("--session", default="")

    p_verify = sub.add_parser("verify", help="Verify active guard session")
    p_verify.add_argument("--session", required=True)
    p_verify.add_argument("--queue", default="")
    p_verify.add_argument("--snapshot", default="")
    p_verify.add_argument("--agents", default="")
    p_verify.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    p_verify.add_argument("--no-write", action="store_true")

    p_close = sub.add_parser("close", help="Close guard session")
    p_close.add_argument("--session", required=True)
    p_close.add_argument("--audit-report", required=True)
    p_close.add_argument("--requirement-status", required=True, choices=["PASS", "FAIL", "pass", "fail"])
    p_close.add_argument("--ui-status", required=True, choices=["PASS", "FAIL", "pass", "fail"])

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "start":
        return command_start(args)
    if args.command == "verify":
        return command_verify(args)
    if args.command == "close":
        return command_close(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

