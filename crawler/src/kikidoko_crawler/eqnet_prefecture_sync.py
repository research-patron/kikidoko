from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from google.api_core import exceptions as gcloud_exceptions

from .eqnet_backfill import parse_eqnet_id
from .firestore_client import get_client
from .utils import guess_prefecture, resolve_region

EQNET_PUBLIC_EQUIPMENT_URL = "https://eqnet.jp/public/equipment.html"

DEFAULT_ORG_PREF_MAP_OUT = "crawler/eqnet_org_prefecture_map.csv"
DEFAULT_AUDIT_OUT = "crawler/prefecture_gap_audit.csv"
DEFAULT_PREVIEW_OUT = "crawler/prefecture_gap_fix_preview.csv"

SPACE_RE = re.compile(r"\s+")
GLOBAL_ORGANIZATIONS_RE = re.compile(
    r"Global\.organizations\s*=\s*(\[[\s\S]*?\])\s*\|\|\s*\[\];", re.MULTILINE
)

# EQNETのorganization_idに対する都道府県マッピング（公式機関リスト準拠）
ORGANIZATION_PREFECTURE_BY_ID: dict[int, str] = {
    1: "北海道",
    2: "北海道",
    3: "北海道",
    4: "北海道",
    5: "宮城県",
    6: "青森県",
    7: "岩手県",
    8: "宮城県",
    9: "秋田県",
    10: "山形県",
    11: "福島県",
    12: "茨城県",
    13: "茨城県",
    14: "栃木県",
    15: "群馬県",
    16: "埼玉県",
    17: "千葉県",
    18: "東京都",
    19: "東京都",
    20: "東京都",
    21: "東京都",
    22: "東京都",
    23: "東京都",
    24: "東京都",
    25: "神奈川県",
    26: "山梨県",
    27: "愛知県",
    28: "岐阜県",
    29: "静岡県",
    30: "愛知県",
    31: "愛知県",
    32: "愛知県",
    33: "三重県",
    34: "長野県",
    35: "静岡県",
    36: "石川県",
    37: "新潟県",
    38: "新潟県",
    39: "富山県",
    40: "福井県",
    41: "石川県",
    42: "京都府",
    43: "京都府",
    44: "京都府",
    45: "奈良県",
    46: "奈良県",
    47: "奈良県",
    48: "大阪府",
    49: "大阪府",
    50: "兵庫県",
    51: "兵庫県",
    52: "和歌山県",
    53: "広島県",
    54: "鳥取県",
    55: "島根県",
    56: "岡山県",
    57: "山口県",
    58: "高知県",
    59: "徳島県",
    60: "徳島県",
    61: "香川県",
    62: "愛媛県",
    63: "福岡県",
    64: "福岡県",
    65: "福岡県",
    66: "佐賀県",
    67: "長崎県",
    68: "熊本県",
    69: "大分県",
    70: "宮崎県",
    71: "鹿児島県",
    72: "沖縄県",
    73: "愛知県",
    412: "滋賀県",
    414: "東京都",
    439: "北海道",
    465: "大阪府",
    469: "奈良県",
    585: "東京都",
}

ORGANIZATION_PREFECTURE_ALIASES: dict[str, str] = {
    "東京工業大学": "東京都",
    "東京医科歯科大学": "東京都",
    "東京科学大学": "東京都",
    "大阪公立大学": "大阪府",
    "公立大学法人大阪大阪公立大学": "大阪府",
    "分子科学研究所": "愛知県",
}


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit/fix missing prefectures for EQNET-derived equipment records."
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("KIKIDOKO_PROJECT_ID", ""),
        help="Firestore project id (or set KIKIDOKO_PROJECT_ID).",
    )
    parser.add_argument(
        "--credentials",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        help="Service account JSON path (or set GOOGLE_APPLICATION_CREDENTIALS).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout seconds.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Firestore batch write size (1-500).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=500,
        help="Progress log interval for Firestore documents.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite prefecture even when existing prefecture is not empty.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export EQNET organization->prefecture map only. Firestore is not read/written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read Firestore and export audit/preview CSVs without writing.",
    )
    parser.add_argument(
        "--org-pref-map-out",
        default=DEFAULT_ORG_PREF_MAP_OUT,
        help=f"Output CSV path for org->prefecture map (default: {DEFAULT_ORG_PREF_MAP_OUT}).",
    )
    parser.add_argument(
        "--audit-out",
        default=DEFAULT_AUDIT_OUT,
        help=f"Output CSV path for audit report (default: {DEFAULT_AUDIT_OUT}).",
    )
    parser.add_argument(
        "--preview-out",
        default=DEFAULT_PREVIEW_OUT,
        help=f"Output CSV path for update preview (default: {DEFAULT_PREVIEW_OUT}).",
    )
    parser.add_argument(
        "--apply-preview-csv",
        default="",
        help="Apply updates directly from an existing preview CSV without Firestore reads.",
    )
    return parser.parse_args(list(argv))


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return SPACE_RE.sub(" ", text).strip()


def normalize_org_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = SPACE_RE.sub("", text)
    for token in (" ", "　", "・", "･"):
        text = text.replace(token, "")
    text = re.sub(r"[()（）\[\]［］【】「」『』<>＜＞]", "", text)
    return text.lower()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_url_text(session: requests.Session, url: str, timeout: float) -> str:
    request_errors: list[str] = []
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as first_error:
        request_errors.append(str(first_error))

    # DNS揺らぎを避けるためcurlにフォールバック
    max_time = str(max(1, int(timeout)))
    for attempt in range(3):
        result = subprocess.run(
            [
                "curl",
                "-L",
                "-s",
                "--retry",
                "2",
                "--retry-delay",
                "1",
                "--retry-all-errors",
                "--max-time",
                max_time,
                url,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace")
        request_errors.append(
            f"curl attempt {attempt + 1} rc={result.returncode} "
            f"err={result.stderr.decode('utf-8', errors='replace')[:200]}"
        )
        if attempt < 2:
            time.sleep(attempt + 1)

    raise RuntimeError(f"failed requests+curl for {url}: {' | '.join(request_errors)}")


def fetch_public_equipment_html(session: requests.Session, timeout: float) -> str:
    return fetch_url_text(session=session, url=EQNET_PUBLIC_EQUIPMENT_URL, timeout=timeout)


def parse_global_organizations(html: str) -> list[dict[str, Any]]:
    match = GLOBAL_ORGANIZATIONS_RE.search(html)
    if not match:
        raise RuntimeError("Global.organizations was not found in EQNET public equipment HTML.")
    payload = json.loads(match.group(1))

    rows: list[dict[str, Any]] = []
    for block in payload:
        if not isinstance(block, list) or len(block) != 2:
            continue
        region_name = clean_text(block[0])
        organizations = block[1]
        if not isinstance(organizations, list):
            continue
        for item in organizations:
            if not isinstance(item, list) or len(item) != 2:
                continue
            org_name = clean_text(item[0])
            try:
                organization_id = int(item[1])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "region_name": region_name,
                    "organization_id": organization_id,
                    "organization_name": org_name,
                }
            )
    return rows


def resolve_prefecture_for_organization(organization_id: int, organization_name: str) -> tuple[str, str]:
    prefecture = ORGANIZATION_PREFECTURE_BY_ID.get(organization_id, "")
    if prefecture:
        return prefecture, "organization_id"

    guessed = guess_prefecture(organization_name)
    if guessed:
        return guessed, "name_guess"

    alias_prefecture = ORGANIZATION_PREFECTURE_ALIASES.get(clean_text(organization_name), "")
    if alias_prefecture:
        return alias_prefecture, "alias"

    return "", "unresolved"


def build_org_prefecture_rows(organization_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in organization_rows:
        organization_id = int(item["organization_id"])
        organization_name = clean_text(item["organization_name"])
        prefecture, source = resolve_prefecture_for_organization(organization_id, organization_name)
        rows.append(
            {
                "region_name": clean_text(item["region_name"]),
                "organization_id": organization_id,
                "organization_name": organization_name,
                "prefecture": prefecture,
                "prefecture_source": source,
                "normalized_org_name": normalize_org_name(organization_name),
            }
        )
    rows.sort(key=lambda row: (row["organization_id"], row["organization_name"]))
    return rows


def write_org_prefecture_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    write_csv(
        path=path,
        fieldnames=[
            "region_name",
            "organization_id",
            "organization_name",
            "prefecture",
            "prefecture_source",
            "normalized_org_name",
        ],
        rows=rows,
    )


def load_org_prefecture_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            org_name = clean_text(row.get("organization_name", ""))
            if not org_name:
                continue
            try:
                organization_id = int(clean_text(row.get("organization_id", "0")) or 0)
            except ValueError:
                organization_id = 0
            rows.append(
                {
                    "region_name": clean_text(row.get("region_name", "")),
                    "organization_id": organization_id,
                    "organization_name": org_name,
                    "prefecture": clean_text(row.get("prefecture", "")),
                    "prefecture_source": clean_text(row.get("prefecture_source", "")),
                    "normalized_org_name": normalize_org_name(row.get("normalized_org_name") or org_name),
                }
            )
    return rows


def build_prefecture_matchers(
    org_pref_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    by_name: dict[str, str] = {}
    for row in org_pref_rows:
        prefecture = clean_text(row.get("prefecture", ""))
        normalized = normalize_org_name(row.get("normalized_org_name") or row.get("organization_name", ""))
        if not normalized or not prefecture:
            continue
        by_name.setdefault(normalized, prefecture)

    for org_name, prefecture in ORGANIZATION_PREFECTURE_ALIASES.items():
        by_name.setdefault(normalize_org_name(org_name), prefecture)

    matcher_rows = [
        {
            "organization_name": clean_text(row["organization_name"]),
            "normalized_org_name": normalize_org_name(row["normalized_org_name"]),
            "prefecture": clean_text(row["prefecture"]),
        }
        for row in org_pref_rows
        if clean_text(row.get("prefecture", "")) and normalize_org_name(row.get("normalized_org_name", ""))
    ]
    matcher_rows.sort(key=lambda row: len(row["normalized_org_name"]), reverse=True)

    alias_matchers = sorted(by_name.items(), key=lambda item: len(item[0]), reverse=True)
    return matcher_rows, alias_matchers


def resolve_prefecture_from_org_name(
    org_name: str,
    matcher_rows: list[dict[str, Any]],
    alias_matchers: list[tuple[str, str]],
) -> tuple[str, str, str]:
    normalized_org = normalize_org_name(org_name)
    if not normalized_org:
        return "", "", "empty_org_name"

    for key, prefecture in alias_matchers:
        if normalized_org == key:
            return prefecture, key, "alias_exact"

    for row in matcher_rows:
        key = row["normalized_org_name"]
        if normalized_org.startswith(key):
            return row["prefecture"], row["organization_name"], "prefix"

    for row in matcher_rows:
        key = row["normalized_org_name"]
        if key in normalized_org:
            return row["prefecture"], row["organization_name"], "contains"

    guessed = guess_prefecture(clean_text(org_name))
    if guessed:
        return guessed, guessed, "name_guess"

    return "", "", "unresolved"


def run(args: argparse.Namespace) -> int:
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2

    if args.apply_preview_csv:
        if not args.project_id:
            print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
            return 2
        preview_path = Path(args.apply_preview_csv)
        if not preview_path.exists():
            print(f"Preview CSV not found: {preview_path}", file=sys.stderr)
            return 2
        client = get_client(args.project_id, args.credentials or None)
        return apply_preview_updates(
            client=client,
            preview_path=preview_path,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            log_every=args.log_every,
        )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "kikidoko-eqnet-prefecture-sync/0.1",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
        }
    )
    html = fetch_public_equipment_html(session=session, timeout=args.timeout)
    organizations = parse_global_organizations(html)
    org_pref_rows = build_org_prefecture_rows(organizations)

    org_pref_map_out = Path(args.org_pref_map_out)
    write_org_prefecture_csv(org_pref_map_out, org_pref_rows)
    unresolved_org_rows = [row for row in org_pref_rows if not row.get("prefecture")]
    print(
        f"EQNET organizations parsed: {len(org_pref_rows)} "
        f"(unresolved_prefecture={len(unresolved_org_rows)}) csv={org_pref_map_out}"
    )

    if args.export_only:
        return 0

    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2

    matcher_rows, alias_matchers = build_prefecture_matchers(org_pref_rows)
    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    now_iso = datetime.now(timezone.utc).isoformat()
    batch = client.batch()
    pending = 0

    processed = 0
    eqnet_docs = 0
    update_candidates = 0
    updated = 0
    unresolved_docs = 0
    status_counter: Counter[str] = Counter()
    unresolved_org_counter: Counter[str] = Counter()

    audit_rows: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []

    for doc in stream_eqnet_candidate_docs(collection):
        processed += 1
        if args.log_every and processed % args.log_every == 0:
            print(
                f"Processed {processed} docs "
                f"(eqnet={eqnet_docs} candidates={update_candidates} updated={updated})"
            )

        data = doc.to_dict() or {}
        org_name = clean_text(data.get("org_name", ""))
        current_prefecture = clean_text(data.get("prefecture", ""))
        current_region = clean_text(data.get("region", ""))
        eqnet_id = parse_eqnet_id(data.get("eqnet_equipment_id") or data.get("eqnet_url"))
        source_site = clean_text(data.get("source_site", "")).lower()
        is_eqnet = bool(eqnet_id) or source_site == "eqnet"
        if not is_eqnet:
            continue

        eqnet_docs += 1
        resolved_prefecture, matched_org_name, match_mode = resolve_prefecture_from_org_name(
            org_name=org_name,
            matcher_rows=matcher_rows,
            alias_matchers=alias_matchers,
        )
        resolved_region = resolve_region(resolved_prefecture)

        status = "keep_existing_prefecture"
        if not org_name:
            status = "unresolved_no_org_name"
        elif current_prefecture and not args.overwrite_existing:
            status = "keep_existing_prefecture"
        elif not resolved_prefecture:
            status = "unresolved_org_not_mapped"
        elif current_prefecture == resolved_prefecture and current_region == resolved_region:
            status = "already_synced"
        else:
            status = "update_candidate"
            update_candidates += 1

        status_counter[status] += 1
        if status.startswith("unresolved"):
            unresolved_docs += 1
            unresolved_org_counter[org_name or "(empty)"] += 1

        audit_rows.append(
            {
                "document_id": doc.id,
                "equipment_id": clean_text(data.get("equipment_id", "")),
                "eqnet_equipment_id": eqnet_id,
                "source_site": source_site,
                "org_name": org_name,
                "current_prefecture": current_prefecture,
                "resolved_prefecture": resolved_prefecture,
                "current_region": current_region,
                "resolved_region": resolved_region,
                "status": status,
                "match_mode": match_mode,
                "matched_org_name": matched_org_name,
            }
        )

        if status != "update_candidate":
            continue

        preview_rows.append(
            {
                "document_id": doc.id,
                "equipment_id": clean_text(data.get("equipment_id", "")),
                "eqnet_equipment_id": eqnet_id,
                "org_name": org_name,
                "prefecture_before": current_prefecture,
                "prefecture_after": resolved_prefecture,
                "region_before": current_region,
                "region_after": resolved_region,
                "prefecture_source": "eqnet_org_map",
                "match_mode": match_mode,
                "matched_org_name": matched_org_name,
            }
        )

        if args.dry_run:
            continue

        updates = {
            "prefecture": resolved_prefecture,
            "region": resolved_region,
            "prefecture_source": "eqnet_org_map",
            "prefecture_synced_at": now_iso,
            "prefecture_before_sync": current_prefecture,
            "region_before_sync": current_region,
        }
        batch.update(doc.reference, updates)
        pending += 1
        updated += 1
        if pending >= args.batch_size:
            try:
                batch.commit()
            except gcloud_exceptions.GoogleAPICallError as exc:
                print(f"[error] Firestore batch commit failed: {exc}", file=sys.stderr)
                raise
            batch = client.batch()
            pending = 0

    if not args.dry_run and pending:
        try:
            batch.commit()
        except gcloud_exceptions.GoogleAPICallError as exc:
            print(f"[error] Firestore final batch commit failed: {exc}", file=sys.stderr)
            raise

    audit_out = Path(args.audit_out)
    preview_out = Path(args.preview_out)
    write_csv(
        path=audit_out,
        fieldnames=[
            "document_id",
            "equipment_id",
            "eqnet_equipment_id",
            "source_site",
            "org_name",
            "current_prefecture",
            "resolved_prefecture",
            "current_region",
            "resolved_region",
            "status",
            "match_mode",
            "matched_org_name",
        ],
        rows=audit_rows,
    )
    write_csv(
        path=preview_out,
        fieldnames=[
            "document_id",
            "equipment_id",
            "eqnet_equipment_id",
            "org_name",
            "prefecture_before",
            "prefecture_after",
            "region_before",
            "region_after",
            "prefecture_source",
            "match_mode",
            "matched_org_name",
        ],
        rows=preview_rows,
    )

    print(
        f"Done. processed={processed} eqnet_docs={eqnet_docs} "
        f"update_candidates={update_candidates} updated={updated} unresolved={unresolved_docs}"
    )
    for key in sorted(status_counter.keys()):
        print(f"  status[{key}]={status_counter[key]}")
    if unresolved_org_counter:
        print("Top unresolved organizations:")
        for org_name, count in unresolved_org_counter.most_common(20):
            print(f"  {count} {org_name}")
    print(f"Audit CSV: {audit_out}")
    print(f"Preview CSV: {preview_out}")
    return 0


def stream_eqnet_candidate_docs(collection) -> Iterable[Any]:
    # 取得対象をeqnet関連に絞って読み取りを抑える。
    queries = [
        collection.where("source_site", "==", "eqnet"),
        collection.where("eqnet_equipment_id", ">", ""),
        collection.where("eqnet_url", ">", ""),
    ]
    seen_doc_ids: set[str] = set()
    for query in queries:
        retries = 3
        for attempt in range(retries):
            try:
                for doc in query.stream():
                    if doc.id in seen_doc_ids:
                        continue
                    seen_doc_ids.add(doc.id)
                    yield doc
                break
            except gcloud_exceptions.ResourceExhausted as exc:
                if attempt + 1 >= retries:
                    raise
                wait = min(90, 15 * (attempt + 1))
                print(
                    f"[warn] Firestore quota limited while streaming query. "
                    f"retry={attempt + 1}/{retries} wait={wait}s error={exc}",
                    file=sys.stderr,
                )
                time.sleep(wait)


def commit_batch_with_retry(batch, retries: int = 4) -> None:
    for attempt in range(retries):
        try:
            batch.commit()
            return
        except gcloud_exceptions.ResourceExhausted as exc:
            if attempt + 1 >= retries:
                raise
            wait = min(120, 10 * (attempt + 1))
            print(
                f"[warn] write quota limited on commit. "
                f"retry={attempt + 1}/{retries} wait={wait}s error={exc}",
                file=sys.stderr,
            )
            time.sleep(wait)


def apply_preview_updates(
    client,
    preview_path: Path,
    batch_size: int,
    dry_run: bool,
    log_every: int,
) -> int:
    rows: list[dict[str, Any]] = []
    with preview_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    if not rows:
        print(f"No rows in preview CSV: {preview_path}")
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    collection = client.collection("equipment")
    batch = client.batch()
    pending = 0
    processed = 0
    applied = 0
    skipped = 0

    for row in rows:
        processed += 1
        if log_every and processed % log_every == 0:
            print(
                f"Processed preview rows {processed} "
                f"(applied={applied} skipped={skipped})"
            )

        doc_id = clean_text(row.get("document_id", ""))
        prefecture_after = clean_text(row.get("prefecture_after", ""))
        if not doc_id or not prefecture_after:
            skipped += 1
            continue

        updates = {
            "prefecture": prefecture_after,
            "region": clean_text(row.get("region_after", "")),
            "prefecture_source": clean_text(row.get("prefecture_source", "")) or "eqnet_org_map",
            "prefecture_synced_at": now_iso,
            "prefecture_before_sync": clean_text(row.get("prefecture_before", "")),
            "region_before_sync": clean_text(row.get("region_before", "")),
            "eqnet_prefecture_match_mode": clean_text(row.get("match_mode", "")),
            "eqnet_prefecture_matched_org_name": clean_text(row.get("matched_org_name", "")),
        }

        if dry_run:
            applied += 1
            continue

        doc_ref = collection.document(doc_id)
        batch.set(doc_ref, updates, merge=True)
        pending += 1
        applied += 1
        if pending >= batch_size:
            commit_batch_with_retry(batch)
            batch = client.batch()
            pending = 0

    if not dry_run and pending:
        commit_batch_with_retry(batch)

    print(
        f"Preview apply done. rows={processed} applied={applied} "
        f"skipped={skipped} dry_run={dry_run}"
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
