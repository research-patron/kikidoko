from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

from .firestore_client import get_client
from .papers_backfill import build_usage_fields, parse_entries, select_diverse
from .utils import clean_text

ELSEVIER_API_URL = "https://api.elsevier.com/content/search/scopus"
DOC_TYPE_FILTER = "DOCTYPE(ar OR cp)"

DEFAULT_KEYWORD_MAP = "crawler/config/papers_strict_keyword_map.json"
DEFAULT_OVERRIDES_CSV = "crawler/config/papers_doc_query_overrides.csv"
DEFAULT_CANDIDATES_CSV = "crawler/papers_strict_candidates.csv"
DEFAULT_MANUAL_REVIEW_CSV = "crawler/papers_strict_manual_review.csv"
DEFAULT_RESULT_CSV = "crawler/papers_strict_apply_result.csv"

MODEL_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}[0-9][A-Za-z0-9-]*")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
JA_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龥々ー]{2,}")
SPACE_RE = re.compile(r"\s+")


@dataclass
class Target:
    document_id: str
    equipment_id: str
    name: str
    org_name: str
    prefecture: str
    category_general: str
    category_detail: str


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strict recheck for no_results_verified equipment papers via Elsevier Scopus API."
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
        "--api-key",
        default=os.getenv("ELSEVIER_API_KEY", ""),
        help="Elsevier API key (or set ELSEVIER_API_KEY).",
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        help="Input CSV for no_results_verified targets.",
    )
    parser.add_argument(
        "--keyword-map",
        default=DEFAULT_KEYWORD_MAP,
        help=f"Keyword map JSON path (default: {DEFAULT_KEYWORD_MAP}).",
    )
    parser.add_argument(
        "--overrides-csv",
        default=DEFAULT_OVERRIDES_CSV,
        help=f"Override query CSV path (default: {DEFAULT_OVERRIDES_CSV}).",
    )
    parser.add_argument(
        "--manual-review-csv",
        default="",
        help="Optional manual review CSV with decision column (accept/reject).",
    )
    parser.add_argument(
        "--output-candidates",
        default=DEFAULT_CANDIDATES_CSV,
        help=f"Output candidate CSV path (default: {DEFAULT_CANDIDATES_CSV}).",
    )
    parser.add_argument(
        "--output-manual-review",
        default=DEFAULT_MANUAL_REVIEW_CSV,
        help=f"Output manual-review CSV path (default: {DEFAULT_MANUAL_REVIEW_CSV}).",
    )
    parser.add_argument(
        "--output-result",
        default=DEFAULT_RESULT_CSV,
        help=f"Output result CSV path (default: {DEFAULT_RESULT_CSV}).",
    )
    parser.add_argument(
        "--max-queries-per-doc",
        type=int,
        default=6,
        help="Maximum queries per equipment (default: 6).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=25,
        help="Number of Scopus results per query (default: 25).",
    )
    parser.add_argument(
        "--view",
        default=os.getenv("ELSEVIER_API_VIEW", "STANDARD"),
        help="Scopus view name (default: STANDARD).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout seconds per Elsevier request.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Sleep seconds after each API call.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Firestore batch write size (default: 50).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only first N targets (0=all).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=50,
        help="Log progress every N targets.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to Firestore.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force no-write mode even with --apply.",
    )
    return parser.parse_args(list(argv))


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return Path(__file__).resolve().parents[3] / path


def normalize_match_text(value: str) -> str:
    text = clean_text(value).lower()
    return re.sub(r"[^a-z0-9ぁ-んァ-ン一-龥々ー]+", "", text)


def sanitize_term(value: str) -> str:
    return clean_text(value).replace('"', "").strip()


def extract_org_affil_token(org_name: str) -> str:
    text = clean_text(org_name)
    if not text:
        return ""
    text = re.sub(r"[()（）]", " ", text)
    text = SPACE_RE.sub(" ", text).strip()
    if not text:
        return ""
    parts = text.split(" ")
    if parts:
        token = parts[0]
        if token:
            return token
    return text


def load_keyword_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"keyword map not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("keyword map must be a JSON object.")
    payload.setdefault("generic_terms_ja", [])
    payload.setdefault("generic_terms_en", [])
    payload.setdefault("vendor_terms", [])
    payload.setdefault("core_rules", [])
    return payload


def load_override_queries(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    mapping: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doc_id = clean_text(row.get("document_id", ""))
            if not doc_id:
                continue
            queries: list[str] = []
            for key in ("query_1", "query_2"):
                value = clean_text(row.get(key, ""))
                if value:
                    queries.append(value)
            if queries:
                mapping[doc_id] = queries
    return mapping


def load_targets(path: Path) -> list[Target]:
    if not path.exists():
        raise FileNotFoundError(f"input csv not found: {path}")
    targets: list[Target] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            document_id = clean_text(row.get("document_id", ""))
            if not document_id:
                continue
            targets.append(
                Target(
                    document_id=document_id,
                    equipment_id=clean_text(row.get("equipment_id", "")),
                    name=clean_text(row.get("name", "")),
                    org_name=clean_text(row.get("org_name", "")),
                    prefecture=clean_text(row.get("prefecture", "")),
                    category_general=clean_text(row.get("category_general", "")),
                    category_detail=clean_text(row.get("category_detail", "")),
                )
            )
    return targets


def load_manual_decisions(path: Path) -> dict[tuple[str, str], str]:
    decisions: dict[tuple[str, str], str] = {}
    if not path.exists():
        return decisions
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doc_id = clean_text(row.get("document_id", ""))
            doi = clean_text(row.get("doi", "")).lower()
            decision = clean_text(row.get("decision", "")).lower()
            if not doc_id or not doi or not decision:
                continue
            decisions[(doc_id, doi)] = decision
    return decisions


def extract_model_tokens(name: str) -> list[str]:
    found = MODEL_TOKEN_RE.findall(name)
    tokens: list[str] = []
    seen = set()
    for token in found:
        normalized = token.upper()
        if len(normalized) < 4:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens[:4]


def extract_vendor_tokens(name: str, vendor_terms: list[str]) -> list[str]:
    vendors: list[str] = []
    seen = set()
    for vendor in vendor_terms:
        value = clean_text(str(vendor))
        if not value:
            continue
        if value.lower() in name.lower():
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            vendors.append(value)
    return vendors[:3]


def extract_core_terms(
    name: str,
    keyword_map: dict[str, Any],
) -> dict[str, list[str]]:
    generic_ja = {clean_text(value) for value in keyword_map.get("generic_terms_ja", [])}
    generic_en = {
        normalize_match_text(str(value))
        for value in keyword_map.get("generic_terms_en", [])
        if normalize_match_text(str(value))
    }
    core_ja: list[str] = []
    core_en: list[str] = []
    aliases_ja: list[str] = []
    aliases_en: list[str] = []
    seen = set()

    def add(values: list[str], container: list[str]) -> None:
        for value in values:
            cleaned = clean_text(value)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            container.append(cleaned)

    for rule in keyword_map.get("core_rules", []):
        if not isinstance(rule, dict):
            continue
        pattern = clean_text(rule.get("pattern", ""))
        if not pattern:
            continue
        try:
            matched = re.search(pattern, name, flags=re.IGNORECASE)
        except re.error:
            matched = pattern in name
        if not matched:
            continue
        add([str(rule.get("core_ja", ""))], core_ja)
        add([str(rule.get("core_en", ""))], core_en)
        if isinstance(rule.get("aliases_ja"), list):
            add([str(value) for value in rule["aliases_ja"]], aliases_ja)
        if isinstance(rule.get("aliases_en"), list):
            add([str(value) for value in rule["aliases_en"]], aliases_en)

    # Fallback: derive from tokens when no rules hit.
    if not core_en:
        for token in ASCII_TOKEN_RE.findall(name):
            normalized = normalize_match_text(token)
            if not normalized or normalized in generic_en:
                continue
            core_en.append(token)
            if len(core_en) >= 2:
                break
    if not core_ja:
        for token in JA_TOKEN_RE.findall(name):
            if token in generic_ja:
                continue
            core_ja.append(token)
            if len(core_ja) >= 2:
                break

    return {
        "core_ja": core_ja,
        "core_en": core_en,
        "aliases_ja": aliases_ja,
        "aliases_en": aliases_en,
    }


def build_query_candidates(
    target: Target,
    core_terms: dict[str, list[str]],
    model_tokens: list[str],
    override_queries: list[str],
    max_queries: int,
) -> list[str]:
    queries: list[str] = []
    seen = set()

    def add_query(query: str) -> None:
        normalized = clean_text(query)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        queries.append(normalized)

    core_en = [sanitize_term(value) for value in core_terms.get("core_en", []) if sanitize_term(value)]
    core_ja = [sanitize_term(value) for value in core_terms.get("core_ja", []) if sanitize_term(value)]
    alias_ja = [sanitize_term(value) for value in core_terms.get("aliases_ja", []) if sanitize_term(value)]
    alias_en = [sanitize_term(value) for value in core_terms.get("aliases_en", []) if sanitize_term(value)]
    org_token = sanitize_term(extract_org_affil_token(target.org_name))

    if core_en:
        add_query(f'TITLE-ABS-KEY("{core_en[0]}") AND {DOC_TYPE_FILTER}')
    if core_ja:
        add_query(f'TITLE-ABS-KEY("{core_ja[0]}") AND {DOC_TYPE_FILTER}')
    elif alias_ja:
        add_query(f'TITLE-ABS-KEY("{alias_ja[0]}") AND {DOC_TYPE_FILTER}')

    model = sanitize_term(model_tokens[0]) if model_tokens else ""
    if model and core_en:
        add_query(
            f'TITLE-ABS-KEY("{core_en[0]}") AND TITLE-ABS-KEY("{model}") AND {DOC_TYPE_FILTER}'
        )
    elif model and alias_en:
        add_query(
            f'TITLE-ABS-KEY("{alias_en[0]}") AND TITLE-ABS-KEY("{model}") AND {DOC_TYPE_FILTER}'
        )

    if core_en and org_token:
        add_query(f'TITLE-ABS-KEY("{core_en[0]}") AND AFFIL("{org_token}") AND {DOC_TYPE_FILTER}')

    for query in override_queries:
        add_query(query)

    return queries[:max_queries]


def fetch_scopus_entries(
    session: requests.Session,
    api_key: str,
    view: str,
    query: str,
    count: int,
    timeout: float,
    retries: int = 3,
) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json", "X-ELS-APIKey": api_key}
    last_error: str = ""
    for attempt in range(retries):
        try:
            response = session.get(
                ELSEVIER_API_URL,
                params={"query": query, "count": count, "view": view},
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt + 1 >= retries:
                raise RuntimeError(f"Elsevier request failed: {exc}") from exc
            time.sleep(2 + attempt * 2)
            continue

        if response.status_code == 429:
            delay = float(response.headers.get("Retry-After") or 10.0)
            time.sleep(delay)
            continue
        if response.status_code in (401, 403):
            raise RuntimeError(f"Elsevier authorization failed: {response.status_code}")
        if response.status_code >= 500:
            last_error = f"server {response.status_code}"
            time.sleep(3 + attempt)
            continue
        if not response.ok:
            raise RuntimeError(f"Elsevier API error: {response.status_code}")

        payload = response.json()
        entries = payload.get("search-results", {}).get("entry", []) or []
        return entries

    raise RuntimeError(f"Elsevier API failed after retries: {last_error}")


def build_core_match_terms(core_terms: dict[str, list[str]]) -> list[str]:
    terms = (
        core_terms.get("core_ja", [])
        + core_terms.get("core_en", [])
        + core_terms.get("aliases_ja", [])
        + core_terms.get("aliases_en", [])
    )
    normalized: list[str] = []
    seen = set()
    for term in terms:
        value = normalize_match_text(term)
        if len(value) < 2 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def evaluate_candidate(
    paper: dict[str, Any],
    query: str,
    core_match_terms: list[str],
    model_tokens: list[str],
) -> tuple[bool, str]:
    title = clean_text(str(paper.get("title", "")))
    title_norm = normalize_match_text(title)
    query_norm = normalize_match_text(query)

    has_core = any(term in title_norm for term in core_match_terms if term)
    model_norms = [normalize_match_text(token) for token in model_tokens if normalize_match_text(token)]
    has_model = any(token and token in title_norm for token in model_norms)
    query_has_core = any(term and term in query_norm for term in core_match_terms)

    if has_core:
        return True, "core_term_in_title"
    if has_model and query_has_core:
        return True, "model_in_title_and_core_in_query"
    return False, "strict_match_failed"


def commit_batch(batch, pending: int, sleep_seconds: float) -> None:
    if pending <= 0:
        return
    batch.commit()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(args: argparse.Namespace) -> int:
    if args.max_queries_per_doc <= 0:
        print("max-queries-per-doc must be 1 or greater.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.apply and args.dry_run:
        print("Cannot use --apply and --dry-run together.", file=sys.stderr)
        return 2
    if args.apply and not args.project_id:
        print("Missing --project-id for --apply mode.", file=sys.stderr)
        return 2
    if not args.api_key:
        print("Missing --api-key or ELSEVIER_API_KEY.", file=sys.stderr)
        return 2

    keyword_map = load_keyword_map(resolve_workspace_path(args.keyword_map))
    overrides = load_override_queries(resolve_workspace_path(args.overrides_csv))
    targets = load_targets(resolve_workspace_path(args.input_csv))
    manual_decisions: dict[tuple[str, str], str] = {}
    if args.manual_review_csv:
        manual_decisions = load_manual_decisions(resolve_workspace_path(args.manual_review_csv))

    if args.limit > 0:
        targets = targets[: args.limit]

    session = requests.Session()
    query_cache: dict[str, list[dict[str, Any]]] = {}
    timestamp = datetime.now(timezone.utc).isoformat()

    candidate_rows: list[dict[str, Any]] = []
    manual_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    status_counts = {"ready": 0, "no_results_verified": 0, "error": 0}

    client = get_client(args.project_id, args.credentials or None) if args.apply else None
    collection = client.collection("equipment") if client else None
    batch = client.batch() if client else None
    pending_writes = 0

    for idx, target in enumerate(targets, start=1):
        core_terms = extract_core_terms(target.name, keyword_map)
        model_tokens = extract_model_tokens(target.name)
        vendor_tokens = extract_vendor_tokens(
            target.name, [str(v) for v in keyword_map.get("vendor_terms", [])]
        )
        query_candidates = build_query_candidates(
            target=target,
            core_terms=core_terms,
            model_tokens=model_tokens,
            override_queries=overrides.get(target.document_id, []),
            max_queries=args.max_queries_per_doc,
        )
        core_match_terms = build_core_match_terms(core_terms)

        auto_candidates: list[dict[str, Any]] = []
        strict_rejects: list[dict[str, Any]] = []
        queries_tried: list[str] = []
        error_messages: list[str] = []
        doc_candidate_count = 0
        query_success_count = 0

        for query in query_candidates:
            queries_tried.append(query)
            try:
                if query in query_cache:
                    papers = query_cache[query]
                else:
                    entries = fetch_scopus_entries(
                        session=session,
                        api_key=args.api_key,
                        view=args.view,
                        query=query,
                        count=args.count,
                        timeout=args.timeout,
                    )
                    papers = parse_entries(entries)
                    query_cache[query] = papers
                query_success_count += 1
            except Exception as exc:
                error_messages.append(str(exc))
                continue

            for paper in papers:
                doi = clean_text(str(paper.get("doi", "")))
                if not doi:
                    continue
                is_auto, reason = evaluate_candidate(
                    paper=paper,
                    query=query,
                    core_match_terms=core_match_terms,
                    model_tokens=model_tokens,
                )
                candidate_row = {
                    "document_id": target.document_id,
                    "equipment_id": target.equipment_id,
                    "name": target.name,
                    "org_name": target.org_name,
                    "query": query,
                    "title": clean_text(str(paper.get("title", ""))),
                    "doi": doi,
                    "source": clean_text(str(paper.get("source", ""))),
                    "year": clean_text(str(paper.get("year", ""))),
                    "genre": clean_text(str(paper.get("genre", ""))),
                    "auto_match": "yes" if is_auto else "no",
                    "reason": reason,
                    "model_tokens": " | ".join(model_tokens),
                    "vendor_tokens": " | ".join(vendor_tokens),
                    "core_terms": " | ".join(core_match_terms),
                }
                candidate_rows.append(candidate_row)
                doc_candidate_count += 1
                if is_auto:
                    enriched = dict(paper)
                    enriched["_query"] = query
                    enriched["_reason"] = reason
                    auto_candidates.append(enriched)
                else:
                    strict_rejects.append(candidate_row)

            if args.sleep > 0:
                time.sleep(args.sleep)

        manual_accepts: list[dict[str, Any]] = []
        for reject in strict_rejects:
            key = (reject["document_id"], reject["doi"].lower())
            decision = manual_decisions.get(key, "")
            manual_rows.append(
                {
                    "document_id": reject["document_id"],
                    "equipment_id": reject["equipment_id"],
                    "name": reject["name"],
                    "org_name": reject["org_name"],
                    "query": reject["query"],
                    "title": reject["title"],
                    "doi": reject["doi"],
                    "source": reject["source"],
                    "year": reject["year"],
                    "reason_not_auto": reject["reason"],
                    "decision": decision,
                }
            )
            if decision in {"accept", "accepted", "yes", "ok", "1"}:
                manual_accepts.append(
                    {
                        "title": reject["title"],
                        "doi": reject["doi"],
                        "genre": reject["genre"],
                        "source": reject["source"],
                        "year": reject["year"],
                        "url": f"https://doi.org/{reject['doi']}",
                        "_query": reject["query"],
                        "_reason": "manual_accept",
                    }
                )

        deduped: list[dict[str, Any]] = []
        seen_doi = set()
        for paper in auto_candidates + manual_accepts:
            doi = clean_text(str(paper.get("doi", ""))).lower()
            if not doi or doi in seen_doi:
                continue
            seen_doi.add(doi)
            deduped.append(paper)

        selected = select_diverse(deduped, limit=3) if deduped else []
        selected_papers = [
            {
                "title": clean_text(str(item.get("title", ""))),
                "doi": clean_text(str(item.get("doi", ""))),
                "genre": clean_text(str(item.get("genre", ""))),
                "source": clean_text(str(item.get("source", ""))),
                "year": clean_text(str(item.get("year", ""))),
                "url": clean_text(str(item.get("url", ""))),
            }
            for item in selected
        ]

        if selected_papers:
            new_status = "ready"
            error_text = ""
            selected_query = clean_text(str(selected[0].get("_query", "")))
        elif error_messages and query_success_count == 0:
            new_status = "error"
            error_text = error_messages[0]
            selected_query = ""
        else:
            new_status = "no_results_verified"
            error_text = ""
            selected_query = queries_tried[0] if queries_tried else ""

        status_counts[new_status] = status_counts.get(new_status, 0) + 1

        result_rows.append(
            {
                "document_id": target.document_id,
                "equipment_id": target.equipment_id,
                "name": target.name,
                "org_name": target.org_name,
                "prefecture": target.prefecture,
                "queries_tried_count": len(queries_tried),
                "queries_tried": " || ".join(queries_tried),
                "auto_candidates": len(auto_candidates),
                "manual_candidates": len(strict_rejects),
                "manual_accepts": len(manual_accepts),
                "selected_papers": len(selected_papers),
                "new_status": new_status,
                "selected_query": selected_query,
                "error": error_text,
            }
        )

        if args.apply and client is not None and collection is not None and batch is not None:
            updates = {
                "papers": selected_papers,
                "papers_status": new_status,
                "papers_query": selected_query,
                "papers_queries_tried": queries_tried,
                "papers_source": "elsevier",
                "papers_view": args.view,
                "papers_updated_at": timestamp,
                "papers_rechecked_at": timestamp,
                "papers_recheck_source": "elsevier_scopus_strict",
                "papers_error": error_text,
            }
            if selected_papers:
                usage_themes, usage_genres = build_usage_fields(selected_papers)
                updates["usage_themes"] = usage_themes
                updates["usage_genres"] = usage_genres
                updates["usage_source"] = "papers"
                updates["usage_updated_at"] = timestamp
            batch.update(collection.document(target.document_id), updates)
            pending_writes += 1
            if pending_writes >= args.batch_size:
                commit_batch(batch, pending_writes, args.sleep)
                batch = client.batch()
                pending_writes = 0

        if args.log_every and idx % args.log_every == 0:
            print(
                f"Processed {idx}/{len(targets)} targets (ready={status_counts.get('ready', 0)}, "
                f"no_results_verified={status_counts.get('no_results_verified', 0)}, "
                f"error={status_counts.get('error', 0)})."
            )

    if args.apply and client is not None and batch is not None and pending_writes:
        commit_batch(batch, pending_writes, args.sleep)

    candidates_path = resolve_workspace_path(args.output_candidates)
    manual_path = resolve_workspace_path(args.output_manual_review)
    result_path = resolve_workspace_path(args.output_result)

    write_csv(
        candidates_path,
        [
            "document_id",
            "equipment_id",
            "name",
            "org_name",
            "query",
            "title",
            "doi",
            "source",
            "year",
            "genre",
            "auto_match",
            "reason",
            "model_tokens",
            "vendor_tokens",
            "core_terms",
        ],
        candidate_rows,
    )
    write_csv(
        manual_path,
        [
            "document_id",
            "equipment_id",
            "name",
            "org_name",
            "query",
            "title",
            "doi",
            "source",
            "year",
            "reason_not_auto",
            "decision",
        ],
        manual_rows,
    )
    write_csv(
        result_path,
        [
            "document_id",
            "equipment_id",
            "name",
            "org_name",
            "prefecture",
            "queries_tried_count",
            "queries_tried",
            "auto_candidates",
            "manual_candidates",
            "manual_accepts",
            "selected_papers",
            "new_status",
            "selected_query",
            "error",
        ],
        result_rows,
    )

    print(
        (
            f"Done strict recheck. targets={len(targets)} status_counts={status_counts} "
            f"apply={args.apply and not args.dry_run} "
            f"candidates_csv={candidates_path} manual_csv={manual_path} result_csv={result_path}"
        )
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
