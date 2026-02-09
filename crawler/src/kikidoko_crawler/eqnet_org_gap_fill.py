from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .eqnet_backfill import EQNET_SEARCH_URL, build_eqnet_url, parse_eqnet_id, strip_html_wrapper
from .eqnet_prefecture_sync import (
    build_org_prefecture_rows,
    build_prefecture_matchers,
    fetch_public_equipment_html,
    load_org_prefecture_csv,
    parse_global_organizations,
    resolve_prefecture_from_org_name,
    write_org_prefecture_csv,
)
from .firestore_client import get_client
from .models import RawEquipment
from .normalizer import normalize_equipment

SPACE_RE = re.compile(r"\s+")
JP_CHAR_RE = re.compile(r"[ぁ-んァ-ン一-龥々ー]")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List EQNET institutions missing in Firestore and import their equipment."
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("KIKIDOKO_PROJECT_ID", ""),
        help="Firestore project id (or KIKIDOKO_PROJECT_ID).",
    )
    parser.add_argument(
        "--credentials",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        help="Service account path (or GOOGLE_APPLICATION_CREDENTIALS).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="EQNET request timeout seconds.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Firestore batch write size (1-500).",
    )
    parser.add_argument(
        "--missing-orgs-out",
        default="crawler/eqnet_missing_orgs.csv",
        help="CSV output for missing institutions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list and count without writing Firestore.",
    )
    parser.add_argument(
        "--limit-orgs",
        type=int,
        default=0,
        help="Process only first N missing organizations (0 = all).",
    )
    parser.add_argument(
        "--skip-firestore-read",
        action="store_true",
        help="Skip Firestore scan and import organizations from --org-list-csv.",
    )
    parser.add_argument(
        "--org-list-csv",
        default="",
        help="CSV file with org_name column (used with --skip-firestore-read).",
    )
    parser.add_argument(
        "--org-prefecture-map-csv",
        default="crawler/eqnet_org_prefecture_map.csv",
        help="CSV path for EQNET organization->prefecture map.",
    )
    return parser.parse_args(list(argv))


def normalize_org_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = SPACE_RE.sub("", text)
    text = text.replace("・", "").replace("･", "").replace("　", "")
    return text.lower()


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = SPACE_RE.sub(" ", text).strip()
    return text


def jp_char_count(text: str) -> int:
    return len(JP_CHAR_RE.findall(text))


def maybe_fix_mojibake(text: str) -> str:
    if not text:
        return text
    try:
        fixed = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if jp_char_count(fixed) > jp_char_count(text):
        return fixed
    return text


def deep_fix_mojibake(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: deep_fix_mojibake(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [deep_fix_mojibake(item) for item in payload]
    if isinstance(payload, str):
        return maybe_fix_mojibake(payload)
    return payload


def fetch_eqnet_rows(timeout: float) -> tuple[list[dict[str, Any]], int]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "kikidoko-eqnet-org-gap-fill/0.1",
            "Accept": "application/json,text/plain,*/*",
        }
    )
    response = session.get(EQNET_SEARCH_URL, timeout=timeout)
    response.raise_for_status()
    payload_text = strip_html_wrapper(response.text)
    payload = json.loads(payload_text)
    data = payload.get("data") or {}
    rows = data.get("data") or []
    rows = deep_fix_mojibake(rows)
    total = int(data.get("total") or len(rows))
    return rows, total


def write_missing_orgs_csv(path: Path, org_to_rows: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["org_name", "equipment_count", "sample_equipment_name"],
        )
        writer.writeheader()
        for org_name in sorted(org_to_rows.keys()):
            rows = org_to_rows[org_name]
            sample = clean_text(rows[0].get("name", "")) if rows else ""
            writer.writerow(
                {
                    "org_name": org_name,
                    "equipment_count": len(rows),
                    "sample_equipment_name": sample,
                }
            )


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.skip_firestore_read and not args.org_list_csv:
        print("When --skip-firestore-read is set, --org-list-csv is required.", file=sys.stderr)
        return 2

    eqnet_rows, eqnet_total = fetch_eqnet_rows(args.timeout)
    print(f"EQNET rows loaded: {len(eqnet_rows)} (total={eqnet_total})")

    org_pref_path = Path(args.org_prefecture_map_csv)
    org_pref_rows = load_org_prefecture_csv(org_pref_path)
    if not org_pref_rows:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "kikidoko-eqnet-org-gap-fill/0.1",
                "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
            }
        )
        html = fetch_public_equipment_html(session=session, timeout=args.timeout)
        organizations = parse_global_organizations(html)
        org_pref_rows = build_org_prefecture_rows(organizations)
        write_org_prefecture_csv(org_pref_path, org_pref_rows)
    matcher_rows, alias_matchers = build_prefecture_matchers(org_pref_rows)
    print(
        f"Organization prefecture map loaded: rows={len(org_pref_rows)} "
        f"csv={org_pref_path}"
    )

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    existing_org_norms: set[str] = set()
    existing_eqnet_ids: set[str] = set()
    existing_equipment_ids: set[str] = set()
    existing_dedupe_keys: set[str] = set()
    if not args.skip_firestore_read:
        for doc in collection.stream():
            data = doc.to_dict() or {}
            org_name = clean_text(data.get("org_name", ""))
            if org_name:
                existing_org_norms.add(normalize_org_name(org_name))
            eqnet_id = parse_eqnet_id(data.get("eqnet_equipment_id") or data.get("eqnet_url"))
            if eqnet_id:
                existing_eqnet_ids.add(eqnet_id)
            equipment_id = clean_text(data.get("equipment_id", ""))
            if equipment_id:
                existing_equipment_ids.add(equipment_id)
            dedupe_key = clean_text(data.get("dedupe_key", ""))
            if dedupe_key:
                existing_dedupe_keys.add(dedupe_key)

        print(
            f"Firestore snapshot: orgs={len(existing_org_norms)} "
            f"eqnet_ids={len(existing_eqnet_ids)}"
        )

    org_to_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eqnet_rows:
        eqnet_id = parse_eqnet_id(row.get("id"))
        if not eqnet_id:
            continue
        affiliation = clean_text(row.get("affiliation", ""))
        if not affiliation:
            continue
        org_to_rows[affiliation].append(row)

    missing_org_to_rows: dict[str, list[dict[str, Any]]] = {}
    if args.skip_firestore_read:
        target_orgs: set[str] = set()
        with Path(args.org_list_csv).open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                org = clean_text(row.get("org_name", ""))
                if org:
                    target_orgs.add(org)
        for org_name, rows in org_to_rows.items():
            if org_name in target_orgs:
                missing_org_to_rows[org_name] = rows
        print(
            f"Target organizations from CSV: {len(target_orgs)} "
            f"(matched={len(missing_org_to_rows)})"
        )
    else:
        for org_name, rows in org_to_rows.items():
            if normalize_org_name(org_name) in existing_org_norms:
                continue
            missing_org_to_rows[org_name] = rows

    if args.limit_orgs > 0:
        limited: dict[str, list[dict[str, Any]]] = {}
        for org_name in sorted(missing_org_to_rows.keys())[: args.limit_orgs]:
            limited[org_name] = missing_org_to_rows[org_name]
        missing_org_to_rows = limited

    missing_orgs_out = Path(args.missing_orgs_out)
    write_missing_orgs_csv(missing_orgs_out, missing_org_to_rows)
    print(
        f"Missing organizations: {len(missing_org_to_rows)} "
        f"(csv={missing_orgs_out})"
    )

    if not missing_org_to_rows:
        print("No missing organizations found.")
        return 0

    to_write: list[tuple[str, dict[str, Any]]] = []
    unresolved_prefecture_orgs: Counter[str] = Counter()
    now_iso = datetime.now(timezone.utc).isoformat()
    for org_name, rows in missing_org_to_rows.items():
        resolved_prefecture, matched_org_name, match_mode = resolve_prefecture_from_org_name(
            org_name=org_name,
            matcher_rows=matcher_rows,
            alias_matchers=alias_matchers,
        )
        if not resolved_prefecture:
            unresolved_prefecture_orgs[org_name] += len(rows)
        for row in rows:
            eqnet_id = parse_eqnet_id(row.get("id"))
            if not eqnet_id:
                continue

            name = clean_text(row.get("name", ""))
            if not name:
                continue

            equipment_id = f"eqnet-{eqnet_id}"
            alias = hashlib.sha1(normalize_org_name(org_name).encode("utf-8")).hexdigest()[:8]
            if args.skip_firestore_read:
                equipment_id = f"{equipment_id}-{alias}"
            elif equipment_id in existing_equipment_ids:
                equipment_id = f"{equipment_id}-{alias}"
            if equipment_id in existing_equipment_ids:
                continue

            external_open = any(
                bool(row.get(key))
                for key in ("national_openness", "private_openness", "company_openness")
            )
            external_use = "可" if external_open else "不可"

            raw = RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general="EQNET設備",
                category_detail="",
                org_name=org_name,
                prefecture=resolved_prefecture,
                address_raw=org_name,
                external_use=external_use,
                fee_note=clean_text(row.get("budget", "")),
                conditions_note=clean_text(row.get("spec", "")),
                source_url=build_eqnet_url(eqnet_id),
                source_updated_at="",
            )
            record = normalize_equipment(raw)
            if not args.skip_firestore_read and record.dedupe_key and record.dedupe_key in existing_dedupe_keys:
                continue
            payload = record.to_firestore()
            payload.update(
                {
                    "eqnet_equipment_id": eqnet_id,
                    "eqnet_url": build_eqnet_url(eqnet_id),
                    "eqnet_match_status": "imported_org_gap",
                    "eqnet_match_confidence": "high",
                    "eqnet_match_name": name,
                    "eqnet_match_affiliation": org_name,
                    "eqnet_match_query": name,
                    "eqnet_match_total": 1,
                    "eqnet_match_updated_at": now_iso,
                    "source_site": "eqnet",
                    "prefecture_source": "eqnet_org_map" if resolved_prefecture else "",
                    "prefecture_synced_at": now_iso if resolved_prefecture else "",
                    "eqnet_prefecture_match_mode": match_mode,
                    "eqnet_prefecture_matched_org_name": matched_org_name,
                }
            )
            to_write.append((equipment_id, payload))
            existing_equipment_ids.add(equipment_id)
            if record.dedupe_key:
                existing_dedupe_keys.add(record.dedupe_key)
            existing_eqnet_ids.add(eqnet_id)

    print(f"Equipment candidates to import: {len(to_write)}")
    if args.dry_run:
        for org_name in sorted(missing_org_to_rows.keys())[:20]:
            print(f"[dry-run] missing_org: {org_name} ({len(missing_org_to_rows[org_name])} rows)")
        if unresolved_prefecture_orgs:
            print("[dry-run] unresolved_prefecture_orgs:")
            for org_name, count in unresolved_prefecture_orgs.most_common(20):
                print(f"  {count} {org_name}")
        return 0

    batch = client.batch()
    pending = 0
    for equipment_id, payload in to_write:
        doc_ref = collection.document(equipment_id)
        batch.set(doc_ref, payload, merge=True)
        pending += 1
        if pending >= args.batch_size:
            batch.commit()
            batch = client.batch()
            pending = 0
    if pending:
        batch.commit()

    print(f"Imported equipment rows: {len(to_write)}")
    if unresolved_prefecture_orgs:
        print("Unresolved prefecture organizations:")
        for org_name, count in unresolved_prefecture_orgs.most_common(20):
            print(f"  {count} {org_name}")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
