from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

import requests

from .firestore_client import get_client
from .utils import NORMALIZED_KEYWORDS, TOKEN_PATTERN, clean_text

ELSEVIER_API_URL = "https://api.elsevier.com/content/search/scopus"
DOC_TYPE_FILTER = "DOCTYPE(ar OR cp)"
SKIP_STATUSES = {"ready", "no_results", "no_query"}
TITLE_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "based",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "via",
    "with",
}
GENERIC_TERMS = {
    "analysis",
    "approach",
    "assessment",
    "behavior",
    "behaviour",
    "case",
    "characterization",
    "comparison",
    "comparative",
    "design",
    "development",
    "effect",
    "effects",
    "evaluation",
    "experimental",
    "investigation",
    "method",
    "methods",
    "model",
    "models",
    "performance",
    "properties",
    "property",
    "research",
    "review",
    "study",
    "system",
    "systems",
    "optimization",
    "optimized",
    "novel",
    "new",
    "high",
    "low",
    "advanced",
    "enhanced",
    "improved",
}


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Elsevier paper data into equipment documents."
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
        "--view",
        default=os.getenv("ELSEVIER_API_VIEW", "STANDARD"),
        help="Scopus view name (default: STANDARD).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=25,
        help="Number of Scopus results to request per query.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds before each Elsevier request times out.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="Seconds to sleep after each API call.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of updates per batch commit (max 500).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Number of documents to fetch per Firestore page.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after processing this many documents (0 = no limit).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report changes without writing to Firestore.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute papers even if already present.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=100,
        help="Print progress every N documents.",
    )
    parser.add_argument(
        "--flush-logs",
        action="store_true",
        help="Force flush logs after each progress update.",
    )
    return parser.parse_args(list(argv))


def sanitize_term(value: str) -> str:
    return value.replace('"', "").strip()


def build_alias_terms(alias_key: str) -> List[str]:
    terms: List[str] = []
    key = alias_key.lower().strip()
    if not key:
        return terms
    terms.append(key.upper())
    variants = NORMALIZED_KEYWORDS.get(key, [])
    for term in variants:
        if term.lower() == key:
            continue
        if re.search(r"[A-Za-z]", term):
            terms.append(term)
            break
    return terms


def build_query_terms(data: Dict[str, Any]) -> List[str]:
    aliases = data.get("search_aliases")
    terms: List[str] = []
    if isinstance(aliases, list):
        for alias_key in aliases:
            if len(terms) >= 2:
                break
            for term in build_alias_terms(str(alias_key)):
                if term and term not in terms:
                    terms.append(term)
            if len(terms) >= 2:
                break
    if terms:
        return terms[:2]

    combined = " ".join(
        [
            clean_text(str(data.get("name", ""))),
            clean_text(str(data.get("category_general", ""))),
            clean_text(str(data.get("category_detail", ""))),
        ]
    )
    cleaned = re.sub(r"\[[^\]]+\]", " ", combined)
    cleaned = re.sub(r"[()（）]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    tokens = TOKEN_PATTERN.findall(cleaned)
    ascii_tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
    if ascii_tokens:
        return ascii_tokens[:2]
    return [cleaned][:1]


def build_query(data: Dict[str, Any]) -> str:
    terms = build_query_terms(data)
    if not terms:
        return ""
    parts = [f'TITLE-ABS-KEY("{sanitize_term(term)}")' for term in terms]
    base = " OR ".join(parts)
    return f"({base}) AND {DOC_TYPE_FILTER}"


def extract_subject(entry: Dict[str, Any]) -> str:
    subject = entry.get("subject-area")
    if isinstance(subject, list):
        for item in subject:
            if isinstance(item, str) and item:
                return item
            if isinstance(item, dict):
                if item.get("$"):
                    return item["$"]
                if item.get("@abbrev"):
                    return item["@abbrev"]
    elif isinstance(subject, dict):
        if subject.get("$"):
            return subject["$"]
        if subject.get("@abbrev"):
            return subject["@abbrev"]
    elif isinstance(subject, str) and subject:
        return subject
    return entry.get("subtypeDescription") or entry.get("prism:aggregationType") or "Uncategorized"


def extract_link(entry: Dict[str, Any], doi: str) -> str:
    links = entry.get("link")
    if isinstance(links, list):
        for ref in ("full-text", "scopus", "self"):
            for item in links:
                if isinstance(item, dict) and item.get("@ref") == ref and item.get("@href"):
                    return item["@href"]
    if entry.get("prism:url"):
        return entry["prism:url"]
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def extract_title_keywords(title: str) -> List[str]:
    if not title:
        return []
    tokens = TITLE_TOKEN_PATTERN.findall(title.lower())
    keywords: List[str] = []
    for token in tokens:
        normalized = token.strip("-").replace("-", "")
        if not normalized or normalized.isdigit():
            continue
        if normalized in STOPWORDS or normalized in GENERIC_TERMS:
            continue
        if normalized not in keywords:
            keywords.append(normalized)
        if len(keywords) >= 6:
            break
    return keywords


def build_usage_fields(papers: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    themes: List[str] = []
    genres: List[str] = []
    for paper in papers:
        for token in extract_title_keywords(paper.get("title", "")):
            if token not in themes:
                themes.append(token)
        genre = paper.get("genre")
        if genre:
            genre_text = str(genre)
            if genre_text not in genres:
                genres.append(genre_text)
    return themes[:3], genres[:3]


def parse_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        doi = entry.get("prism:doi") or entry.get("doi") or ""
        if not doi or doi in seen:
            continue
        seen.add(doi)
        title = entry.get("dc:title") or entry.get("prism:title") or ""
        genre = extract_subject(entry)
        source = entry.get("prism:publicationName") or ""
        cover_date = entry.get("prism:coverDate") or ""
        year = cover_date[:4] if cover_date else ""
        url = extract_link(entry, doi)
        results.append(
            {
                "title": title,
                "doi": doi,
                "genre": genre,
                "source": source,
                "year": year,
                "url": url,
            }
        )
    return results


def select_diverse(papers: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    used_genres = set()
    for paper in papers:
        if len(selected) >= limit:
            break
        genre = paper.get("genre") or "Uncategorized"
        if genre in used_genres:
            continue
        used_genres.add(genre)
        selected.append(paper)
    if len(selected) >= limit:
        return selected
    for paper in papers:
        if len(selected) >= limit:
            break
        if paper in selected:
            continue
        selected.append(paper)
    return selected[:limit]


def fetch_papers(
    session: requests.Session,
    api_key: str,
    view: str,
    count: int,
    query: str,
    timeout: float,
    retries: int = 3,
) -> Tuple[List[Dict[str, Any]], str]:
    headers = {"Accept": "application/json", "X-ELS-APIKey": api_key}
    for attempt in range(retries):
        try:
            response = session.get(
                ELSEVIER_API_URL,
                params={"query": query, "count": count, "view": view},
                headers=headers,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f"Elsevier request failed: {exc}") from exc
            time.sleep(2 + attempt * 2)
            continue
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 10.0
            time.sleep(delay)
            continue
        if response.status_code in (401, 403):
            raise RuntimeError("Elsevier authorization failed.")
        if response.status_code >= 500:
            time.sleep(5)
            continue
        if not response.ok:
            raise RuntimeError(f"Elsevier API error: {response.status_code}")
        payload = response.json()
        entries = payload.get("search-results", {}).get("entry", []) or []
        papers = parse_entries(entries)
        return select_diverse(papers, 3), "ready" if papers else "no_results"
    raise RuntimeError("Elsevier API rate limit or server error.")


def commit_batch(batch, pending: int, sleep_seconds: float) -> None:
    if pending <= 0:
        return
    batch.commit()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def fetch_page(query, retries: int = 3) -> List[Any]:
    last_error = None
    for attempt in range(retries):
        try:
            return list(query.stream())
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            time.sleep(2 + attempt * 2)
    if last_error:
        raise last_error
    return []


def run_backfill(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if not args.api_key:
        print("Missing --api-key or ELSEVIER_API_KEY.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.page_size <= 0:
        print("page-size must be 1 or greater.", file=sys.stderr)
        return 2
    if args.sleep < 0:
        print("sleep must be 0 or greater.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    print(
        f"Starting papers backfill (project={args.project_id}, page_size={args.page_size}, force={args.force}).",
        flush=args.flush_logs,
    )

    total = 0
    updated = 0
    skipped = 0
    errors = 0
    pending = 0
    batch = client.batch()
    query_cache: Dict[str, Tuple[List[Dict[str, Any]], str]] = {}
    session = requests.Session()

    last_doc = None
    while True:
        page_query = collection.order_by("__name__").limit(args.page_size)
        if last_doc:
            page_query = page_query.start_after(last_doc)
        try:
            docs = fetch_page(page_query)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to fetch page: {exc}", file=sys.stderr)
            errors += 1
            break
        if not docs:
            break
        if args.flush_logs:
            print(f"Fetched page with {len(docs)} docs.", flush=True)
        for doc in docs:
            total += 1
            data = doc.to_dict() or {}
            existing = data.get("papers")
            status = data.get("papers_status", "")
            if not args.force:
                if status in SKIP_STATUSES:
                    skipped += 1
                    if args.limit and total >= args.limit:
                        break
                    continue
                if isinstance(existing, list) and len(existing) > 0:
                    skipped += 1
                    if args.limit and total >= args.limit:
                        break
                    continue

            query = build_query(data)
            papers: List[Dict[str, Any]] = []
            paper_status = "no_query"
            error_message = ""
            try:
                if not query:
                    paper_status = "no_query"
                elif query in query_cache:
                    papers, paper_status = query_cache[query]
                else:
                    papers, paper_status = fetch_papers(
                        session,
                        args.api_key,
                        args.view,
                        args.count,
                        query,
                        args.timeout,
                    )
                    query_cache[query] = (papers, paper_status)
            except Exception as exc:
                errors += 1
                error_message = str(exc)
                paper_status = "error"
                print(f"Failed {doc.id}: {error_message}", file=sys.stderr)

            updates = {
                "papers": papers,
                "papers_status": paper_status,
                "papers_query": query,
                "papers_source": "elsevier",
                "papers_view": args.view,
                "papers_updated_at": datetime.now(timezone.utc).isoformat(),
                "papers_error": error_message,
                "usage_themes": [],
                "usage_genres": [],
                "usage_source": "papers",
                "usage_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if papers:
                usage_themes, usage_genres = build_usage_fields(papers)
                updates["usage_themes"] = usage_themes
                updates["usage_genres"] = usage_genres

            updated += 1
            if not args.dry_run:
                batch.update(doc.reference, updates)
                pending += 1
                if pending >= args.batch_size:
                    commit_batch(batch, pending, args.sleep)
                    batch = client.batch()
                    pending = 0

            if args.sleep > 0:
                time.sleep(args.sleep)
            if args.log_every and total % args.log_every == 0:
                print(
                    f"Processed {total} docs (updated {updated}, skipped {skipped}, errors {errors}).",
                    flush=args.flush_logs,
                )
            if args.limit and total >= args.limit:
                break
        if args.limit and total >= args.limit:
            break
        last_doc = docs[-1]

    if not args.dry_run and pending:
        commit_batch(batch, pending, args.sleep)

    print(
        f"Done. processed={total} updated={updated} skipped={skipped} errors={errors}",
        flush=args.flush_logs,
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run_backfill(args))


if __name__ == "__main__":
    main()
