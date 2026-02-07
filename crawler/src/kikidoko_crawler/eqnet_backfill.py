from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable

import requests
from google.api_core import exceptions as gcloud_exceptions

from .firestore_client import get_client

EQNET_SEARCH_URL = "https://eqnet.jp/public/equipment/search.json"
EQNET_DETAIL_URL = "https://eqnet.jp/top#/public/equipment/{equipment_id}"
TAG_PATTERN = re.compile(r"<[^>]*>")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[ぁ-んァ-ン一-龥々ー]+")
EQNET_ID_PATTERN = re.compile(r"(?:#?/public/equipment/|/public/equipment/)(\d+)")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill EQNET equipment links into equipment documents."
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
        "--dry-run",
        action="store_true",
        help="Only report changes without writing to Firestore.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-resolve even if eqnet_equipment_id is already set.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after processing this many documents (0 = no limit).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of updates per batch commit (max 500).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep after each EQNET request.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Seconds before each EQNET request times out.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=5,
        help="Max number of EQNET candidates to store per document.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=50,
        help="Print progress every N processed documents.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Number of Firestore docs fetched per page.",
    )
    parser.add_argument(
        "--max-candidate-pool",
        type=int,
        default=450,
        help="Max candidate pool size per equipment before scoring.",
    )
    return parser.parse_args(list(argv))


def parse_eqnet_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return text
    match = EQNET_ID_PATTERN.search(text)
    if match:
        return match.group(1)
    return ""


def build_eqnet_url(equipment_id: str) -> str:
    eq_id = parse_eqnet_id(equipment_id)
    if not eq_id:
        return ""
    return EQNET_DETAIL_URL.format(equipment_id=eq_id)


def strip_html_wrapper(text: str) -> str:
    payload = text.strip()
    if payload.startswith("<"):
        payload = TAG_PATTERN.sub("", payload).strip()
    return payload


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = text.replace("−", "-")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-zぁ-んァ-ン一-龥々ー]", "", text)
    return text


def token_set(value: Any) -> set[str]:
    if value is None:
        return set()
    normalized = unicodedata.normalize("NFKC", str(value)).lower()
    return {token for token in TOKEN_PATTERN.findall(normalized) if len(token) >= 2}


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_candidate(name: str, org_name: str, candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_name = str(candidate.get("name", "")).strip()
    candidate_affiliation = str(candidate.get("affiliation", "")).strip()
    candidate_id = parse_eqnet_id(candidate.get("id", ""))
    normalized_name = normalize_text(name)
    normalized_candidate_name = candidate.get("normalized_name") or normalize_text(candidate_name)
    normalized_org = normalize_text(org_name)
    normalized_affiliation = candidate.get("normalized_affiliation") or normalize_text(
        candidate_affiliation
    )

    name_score = 0
    name_exact = False
    if normalized_name and normalized_candidate_name:
        if normalized_name == normalized_candidate_name:
            name_score = 72
            name_exact = True
        elif normalized_name in normalized_candidate_name or normalized_candidate_name in normalized_name:
            name_score = 60
        else:
            name_score = int(similarity(normalized_name, normalized_candidate_name) * 55)

    org_score = 0
    org_match = False
    if normalized_org and normalized_affiliation:
        if normalized_org == normalized_affiliation:
            org_score = 30
            org_match = True
        elif normalized_org in normalized_affiliation or normalized_affiliation in normalized_org:
            org_score = 26
            org_match = True
        else:
            org_score = int(similarity(normalized_org, normalized_affiliation) * 22)

    name_tokens = token_set(name)
    candidate_tokens = candidate.get("tokens") or token_set(candidate_name)
    token_overlap = len(name_tokens.intersection(candidate_tokens))
    token_score = min(12, token_overlap * 3)

    score = min(100, name_score + org_score + token_score)
    return {
        "id": candidate_id,
        "name": candidate_name,
        "affiliation": candidate_affiliation,
        "url": build_eqnet_url(candidate_id),
        "score": score,
        "name_exact": name_exact,
        "org_match": org_match,
    }


def decide_match(scored_candidates: list[dict[str, Any]]) -> tuple[str, str]:
    if not scored_candidates:
        return "", "none"
    top = scored_candidates[0]
    second_score = scored_candidates[1]["score"] if len(scored_candidates) > 1 else -1
    margin = top["score"] - second_score

    if top["name_exact"] and top["org_match"] and top["score"] >= 88:
        return top["id"], "high"
    if top["score"] >= 92 and margin >= 6:
        return top["id"], "high"
    if top["score"] >= 82 and margin >= 10:
        return top["id"], "medium"
    return "", "none"


def fetch_master_candidates(
    session: requests.Session,
    timeout: float,
) -> tuple[list[dict[str, Any]], int]:
    response = session.get(EQNET_SEARCH_URL, timeout=timeout)
    response.raise_for_status()
    payload_text = strip_html_wrapper(response.text)
    payload = json.loads(payload_text)
    data = payload.get("data") or {}
    raw_candidates = data.get("data") or []
    total = int(data.get("total") or len(raw_candidates))
    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        eq_id = parse_eqnet_id(raw.get("id", ""))
        if not eq_id:
            continue
        name = str(raw.get("name", "")).strip()
        affiliation = str(raw.get("affiliation", "")).strip()
        candidates.append(
            {
                "id": eq_id,
                "name": name,
                "affiliation": affiliation,
                "normalized_name": normalize_text(name),
                "normalized_affiliation": normalize_text(affiliation),
                "tokens": token_set(name),
            }
        )
    return candidates, total


def build_candidate_pool(
    name: str,
    master_candidates: list[dict[str, Any]],
    max_pool: int,
) -> list[dict[str, Any]]:
    normalized_name = normalize_text(name)
    name_tokens = token_set(name)
    direct_matches: list[dict[str, Any]] = []
    token_matches: list[tuple[int, dict[str, Any]]] = []

    for candidate in master_candidates:
        candidate_name = candidate.get("normalized_name", "")
        if normalized_name and candidate_name:
            if normalized_name in candidate_name or candidate_name in normalized_name:
                direct_matches.append(candidate)
                continue
        if name_tokens:
            overlap = len(name_tokens.intersection(candidate.get("tokens") or set()))
            if overlap > 0:
                token_matches.append((overlap, candidate))

    if max_pool <= 0:
        max_pool = 450

    if direct_matches:
        remaining = max(0, max_pool - len(direct_matches))
        if remaining <= 0:
            return direct_matches[:max_pool]
        token_matches.sort(key=lambda item: item[0], reverse=True)
        return direct_matches + [item[1] for item in token_matches[:remaining]]

    if token_matches:
        token_matches.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in token_matches[:max_pool]]

    return master_candidates[:max_pool]


def build_updates(
    data: dict[str, Any],
    master_candidates: list[dict[str, Any]],
    candidate_limit: int,
    max_candidate_pool: int,
) -> dict[str, Any]:
    name = str(data.get("name", "")).strip()
    org_name = str(data.get("org_name", "")).strip()
    if not name:
        return {
            "eqnet_match_status": "skipped",
            "eqnet_match_error": "missing_name",
            "eqnet_match_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    candidate_pool = build_candidate_pool(
        name=name,
        master_candidates=master_candidates,
        max_pool=max_candidate_pool,
    )
    scored_candidates = [
        score_candidate(name, org_name, candidate)
        for candidate in candidate_pool
    ]
    scored_candidates.sort(key=lambda item: item["score"], reverse=True)

    match_id, confidence = decide_match(scored_candidates)
    updated_at = datetime.now(timezone.utc).isoformat()
    candidate_payload = [
        {
            "id": candidate["id"],
            "name": candidate["name"],
            "affiliation": candidate["affiliation"],
            "url": candidate["url"],
            "score": candidate["score"],
        }
        for candidate in scored_candidates[:candidate_limit]
    ]

    updates: dict[str, Any] = {
        "eqnet_match_query": name,
        "eqnet_match_total": len(candidate_pool),
        "eqnet_candidates": candidate_payload,
        "eqnet_match_updated_at": updated_at,
    }
    if match_id:
        best = scored_candidates[0]
        updates.update(
            {
                "eqnet_match_status": "matched",
                "eqnet_match_confidence": confidence,
                "eqnet_equipment_id": match_id,
                "eqnet_url": build_eqnet_url(match_id),
                "eqnet_match_name": best["name"],
                "eqnet_match_affiliation": best["affiliation"],
                "eqnet_match_error": "",
            }
        )
        return updates

    updates["eqnet_equipment_id"] = ""
    updates["eqnet_url"] = ""
    updates["eqnet_match_name"] = ""
    updates["eqnet_match_affiliation"] = ""
    updates["eqnet_match_confidence"] = ""
    updates["eqnet_match_error"] = ""
    updates["eqnet_match_status"] = "candidate" if candidate_payload else "unmatched"
    return updates


def has_updates(current: dict[str, Any], updates: dict[str, Any]) -> bool:
    for key, value in updates.items():
        if current.get(key) != value:
            return True
    return False


def iter_documents(collection, page_size: int) -> Iterable[Any]:
    if page_size <= 0:
        page_size = 200
    base_query = collection.order_by("__name__").limit(page_size)
    last_doc = None
    while True:
        page_query = base_query if last_doc is None else base_query.start_after(last_doc)
        docs = None
        for attempt in range(3):
            try:
                docs = list(page_query.stream())
                break
            except (gcloud_exceptions.DeadlineExceeded, gcloud_exceptions.ServiceUnavailable):
                if attempt >= 2:
                    raise
                time.sleep(2 * (attempt + 1))
        if not docs:
            break
        for doc in docs:
            yield doc
        if len(docs) < page_size:
            break
        last_doc = docs[-1]


def run_backfill(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.candidate_limit <= 0:
        print("candidate-limit must be at least 1.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "kikidoko-eqnet-backfill/0.1",
            "Accept": "application/json,text/plain,*/*",
        }
    )
    master_candidates, master_total = fetch_master_candidates(session, args.timeout)
    print(
        f"Loaded EQNET master candidates: {len(master_candidates)} (total={master_total})"
    )

    processed = 0
    updated = 0
    skipped = 0
    errors = 0
    pending = 0
    batch = client.batch()

    for doc in iter_documents(collection, args.page_size):
        processed += 1
        data = doc.to_dict() or {}

        existing_id = parse_eqnet_id(data.get("eqnet_equipment_id") or data.get("eqnet_url"))
        status = str(data.get("eqnet_match_status", "")).strip()
        if (existing_id or (status and status != "error")) and not args.force:
            skipped += 1
            if args.limit and processed >= args.limit:
                break
            continue

        try:
            updates = build_updates(
                data=data,
                master_candidates=master_candidates,
                candidate_limit=args.candidate_limit,
                max_candidate_pool=args.max_candidate_pool,
            )
        except Exception as exc:
            errors += 1
            message = str(exc)
            updates = {
                "eqnet_match_status": "error",
                "eqnet_match_error": message[:300],
                "eqnet_match_updated_at": datetime.now(timezone.utc).isoformat(),
            }

        if has_updates(data, updates):
            updated += 1
            if args.dry_run:
                doc_name = str(data.get("name", "")).strip() or doc.id
                print(
                    f"[dry-run] {doc.id} {doc_name} -> "
                    f"{updates.get('eqnet_match_status', 'unknown')}"
                )
            else:
                batch.set(doc.reference, updates, merge=True)
                pending += 1
                if pending >= args.batch_size:
                    batch.commit()
                    batch = client.batch()
                    pending = 0

        if args.sleep > 0:
            time.sleep(args.sleep)

        if args.log_every > 0 and processed % args.log_every == 0:
            print(
                f"Processed {processed} docs (updated={updated}, skipped={skipped}, errors={errors})"
            )

        if args.limit and processed >= args.limit:
            break

    if not args.dry_run and pending:
        batch.commit()

    print(
        f"Done. processed={processed} updated={updated} skipped={skipped} errors={errors}"
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run_backfill(args))


if __name__ == "__main__":
    main()
