#!/usr/bin/env python3
"""Rebuild papers in equipment_snapshot.json.gz.

What this script does:
- Removes placeholder abstracts ("要旨未取得...") from papers.
- Optionally fetches missing abstracts for selected items (Elsevier/Crossref by DOI).
- Can import candidate papers from an optional source snapshot to replace no-good entries.
- Normalizes paper URLs to ScienceDirect/DOI links.
- Recomputes papers_status (ready only when abstracted papers remain).
- Regenerates usage_manual_summary / usage_manual_bullets from surviving papers.
- Appends update history to frontend/dist/update-history.json.
- Writes translation queue JSONL for papers that still need manual JA translation.
- Supports execution gates for fetched_abstracts / translated_ja counts.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLACEHOLDER_PREFIX = "要旨未取得"
SCOPUS_HOST = "www.scopus.com"
ELSEVIER_API_HOST = "api.elsevier.com"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_placeholder_abstract(text: Any) -> bool:
    return str(text or "").strip().startswith(PLACEHOLDER_PREFIX)


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龠々ー]", text or ""))


def has_kana(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶー]", text or ""))


def has_ellipsis(text: str) -> bool:
    value = str(text or "")
    return "..." in value or "…" in value


def ja_issue_flags(abstract: Any, abstract_ja: Any) -> List[str]:
    abstract_text = normalize_whitespace(abstract)
    abstract_ja_text = normalize_whitespace(abstract_ja)
    flags: List[str] = []

    if not abstract_ja_text:
        flags.append("missing_ja")
    if abstract_text and abstract_ja_text and abstract_text == abstract_ja_text:
        flags.append("same_as_abstract")
    if abstract_ja_text and not has_kana(abstract_ja_text):
        flags.append("no_kana")
    if has_ellipsis(abstract_ja_text) and not has_ellipsis(abstract_text):
        flags.append("ellipsis_mismatch")
    if len(abstract_text) >= 200 and (
        len(abstract_ja_text) / max(1, len(abstract_text))
    ) < 0.35:
        flags.append("too_short_ratio")
    return flags


def is_bad_ja_translation(abstract: Any, abstract_ja: Any) -> bool:
    return bool(ja_issue_flags(abstract, abstract_ja))


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    if not doi:
        return ""
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    return doi.strip()


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_identity(value: Any) -> str:
    return normalize_whitespace(value).lower()


def snapshot_item_keys(item: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    equipment_id = normalize_identity(item.get("equipment_id"))
    doc_id = normalize_identity(item.get("doc_id"))
    composite = "|".join(
        [
            normalize_identity(item.get("name")),
            normalize_identity(item.get("org_name")),
            normalize_identity(item.get("prefecture")),
        ]
    )

    if equipment_id:
        keys.append(f"equipment_id:{equipment_id}")
    if doc_id:
        keys.append(f"doc_id:{doc_id}")
    if composite.strip("|"):
        keys.append(f"composite:{composite}")
    return keys


def build_source_index(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        for key in snapshot_item_keys(item):
            index.setdefault(key, item)
    return index


def merge_candidate_papers(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for paper in [*primary, *secondary]:
        if not isinstance(paper, dict):
            continue
        doi_key = normalize_doi(paper.get("doi"))
        title_key = normalize_whitespace(paper.get("title") or "").lower()
        key = doi_key or title_key
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(dict(paper))
    return merged


def parse_env_file(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def strip_xml_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned


def tokenized_words(text: str) -> List[str]:
    normalized = (
        str(text or "")
        .lower()
        .replace("\u3000", " ")
    )
    normalized = re.sub(r"[^a-z0-9ぁ-んァ-ン一-龠々ー\s\-_/]", " ", normalized)
    words = [w for w in re.split(r"[\s\-_/]+", normalized) if len(w) >= 2]
    return words


def equipment_keywords(item: Dict[str, Any]) -> List[str]:
    words: List[str] = []
    for key in ("name", "category_general", "category_detail"):
        words.extend(tokenized_words(str(item.get(key) or "")))

    # Keep uppercase abbreviations that often map to instrument names.
    name = str(item.get("name") or "")
    acronyms = re.findall(r"[A-Z]{2,}[0-9]*", name)
    words.extend([a.lower() for a in acronyms])

    dedup: List[str] = []
    seen = set()
    for word in words:
        if word not in seen:
            dedup.append(word)
            seen.add(word)
    return dedup[:30]


def relevance_score(item: Dict[str, Any], paper: Dict[str, Any]) -> float:
    keywords = equipment_keywords(item)
    if not keywords:
        return 0.2

    corpus = " ".join(
        [
            str(paper.get("title") or ""),
            str(paper.get("abstract") or ""),
            str(paper.get("abstract_ja") or ""),
            str(paper.get("source") or ""),
        ]
    ).lower()

    hits = 0
    for kw in keywords:
        if kw in corpus:
            hits += 1

    base = hits / max(1.0, float(len(keywords)))
    if paper.get("doi"):
        base += 0.04
    if len(str(paper.get("abstract") or "")) >= 140:
        base += 0.05
    if len(str(paper.get("title") or "")) >= 32:
        base += 0.02
    return base


def extract_usage_phrase(abstract_ja: str, category_general: str) -> str:
    text = normalize_whitespace(abstract_ja)
    if not text:
        return f"{category_general}に関する測定・解析"

    chunks = re.split(r"[。.!?]\s*", text)
    keywords = (
        "観察",
        "測定",
        "解析",
        "評価",
        "試験",
        "合成",
        "調製",
        "処理",
        "検証",
    )

    for chunk in chunks:
        sentence = normalize_whitespace(chunk)
        if len(sentence) < 12:
            continue
        if any(k in sentence for k in keywords):
            return sentence[:110]

    candidate = normalize_whitespace(chunks[0])
    if not candidate:
        return f"{category_general}に関する測定・解析"
    return candidate[:110]


def build_usage_manual(item: Dict[str, Any], papers: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    name = str(item.get("name") or "対象機器")
    summary = f"{name}に関する関連論文の要旨から、代表的な利用文脈を整理しています。"

    bullets: List[str] = []
    for paper in papers[:3]:
        doi = str(paper.get("doi") or "DOI不明")
        title = normalize_whitespace(paper.get("title") or "タイトル不明")
        source = normalize_whitespace(paper.get("source") or "")
        year = normalize_whitespace(paper.get("year") or "")
        meta = " / ".join([v for v in [source, year] if v])
        if meta:
            bullets.append(f"DOI {doi}: {title} ({meta})")
        else:
            bullets.append(f"DOI {doi}: {title}")

    if not bullets:
        bullets.append("利用条件・測定条件は採用論文と機器担当者の案内を優先してください。")

    return summary, bullets


def normalize_research_fields(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = normalize_whitespace(value)
        if text and text not in out:
            out.append(text)
    return out[:4]


def normalize_doi_refs(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        doi = normalize_doi(value)
        if doi and doi not in out:
            out.append(doi)
    return out[:3]


def sanitize_usage_insights(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    how_text = normalize_whitespace(((value.get("how") or {}).get("text") if isinstance(value.get("how"), dict) else ""))
    what_text = normalize_whitespace(((value.get("what") or {}).get("text") if isinstance(value.get("what"), dict) else ""))
    fields_items = normalize_research_fields((value.get("fields") or {}).get("items") if isinstance(value.get("fields"), dict) else [])
    how_refs = normalize_doi_refs((value.get("how") or {}).get("doi_refs") if isinstance(value.get("how"), dict) else [])
    what_refs = normalize_doi_refs((value.get("what") or {}).get("doi_refs") if isinstance(value.get("what"), dict) else [])
    fields_refs = normalize_doi_refs((value.get("fields") or {}).get("doi_refs") if isinstance(value.get("fields"), dict) else [])

    if not how_text or not what_text or not fields_items:
        return None
    if not how_refs or not what_refs or not fields_refs:
        return None

    return {
        "how": {"text": how_text, "doi_refs": how_refs},
        "what": {"text": what_text, "doi_refs": what_refs},
        "fields": {"items": fields_items, "doi_refs": fields_refs},
    }


def build_usage_insights_from_papers(papers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        how_text = normalize_whitespace(paper.get("usage_how_ja"))
        what_text = normalize_whitespace(paper.get("usage_what_ja"))
        fields_items = normalize_research_fields(paper.get("research_fields_ja"))
        if not how_text or not what_text or not fields_items:
            continue
        doi = normalize_doi(paper.get("doi"))
        refs = [doi] if doi else []
        if not refs:
            continue
        return {
            "how": {"text": how_text, "doi_refs": refs},
            "what": {"text": what_text, "doi_refs": refs},
            "fields": {"items": fields_items, "doi_refs": refs},
        }
    return None


def canonical_paper_url(url: Any, doi: str) -> str:
    raw = str(url or "").strip()
    doi = normalize_doi(doi)

    if not raw and doi:
        return f"https://doi.org/{doi}"

    lower = raw.lower()

    # Elsevier API URL -> ScienceDirect URL.
    if ELSEVIER_API_HOST in lower and "/content/article/eid/" in lower:
        match = re.search(r"1-s2\.0-([A-Za-z0-9]+)", raw)
        if match:
            return f"https://www.sciencedirect.com/science/article/pii/{match.group(1)}"

    if ELSEVIER_API_HOST in lower and "/content/article/pii/" in lower:
        match = re.search(r"/pii/([^/?]+)", raw)
        if match:
            return f"https://www.sciencedirect.com/science/article/pii/{match.group(1)}"

    # Scopus URL -> DOI URL when DOI exists.
    if SCOPUS_HOST in lower and doi:
        return f"https://doi.org/{doi}"

    if doi and ("doi.org" in lower):
        return f"https://doi.org/{doi}"

    return raw if raw else (f"https://doi.org/{doi}" if doi else "")


def http_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = res.read()
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None

    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def fetch_elsevier_metadata(doi: str, api_key: str, timeout_sec: float = 24.0) -> Optional[Dict[str, Any]]:
    if not doi or not api_key:
        return None

    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.elsevier.com/content/article/doi/{encoded}"
    payload = http_json(
        url,
        headers={
            "Accept": "application/json",
            "X-ELS-APIKey": api_key,
            "User-Agent": "kikidoko-rebuild/1.0",
        },
        timeout=max(1, int(timeout_sec)),
    )
    if not payload:
        return None

    full = payload.get("full-text-retrieval-response") or {}
    core = full.get("coredata") or {}

    abstract = normalize_whitespace(core.get("dc:description") or "")
    title = normalize_whitespace(core.get("dc:title") or "")
    source = normalize_whitespace(core.get("prism:publicationName") or "")
    cover_date = normalize_whitespace(core.get("prism:coverDate") or "")
    year = cover_date[:4] if len(cover_date) >= 4 else ""
    url = normalize_whitespace(core.get("prism:url") or "")
    article_type = normalize_whitespace(core.get("subtypeDescription") or core.get("prism:aggregationType") or "")

    if not abstract:
        return None

    return {
        "doi": doi,
        "title": title,
        "source": source,
        "year": year,
        "url": url,
        "genre": article_type,
        "abstract": abstract,
        "from": "elsevier",
    }


def fetch_crossref_metadata(doi: str, timeout_sec: float = 24.0) -> Optional[Dict[str, Any]]:
    if not doi:
        return None

    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.crossref.org/works/{encoded}"
    payload = http_json(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "kikidoko-rebuild/1.0 (mailto:admin@example.com)",
        },
        timeout=max(1, int(timeout_sec)),
    )
    if not payload:
        return None

    message = payload.get("message") or {}
    abstract_raw = str(message.get("abstract") or "")
    abstract = strip_xml_tags(abstract_raw)
    if not abstract:
        return None

    title_list = message.get("title") or []
    source_list = message.get("container-title") or []
    title = normalize_whitespace(title_list[0] if title_list else "")
    source = normalize_whitespace(source_list[0] if source_list else "")

    year = ""
    date_parts = (((message.get("issued") or {}).get("date-parts") or []) or [[]])[0]
    if date_parts:
        year = str(date_parts[0])

    return {
        "doi": doi,
        "title": title,
        "source": source,
        "year": year,
        "url": normalize_whitespace(message.get("URL") or ""),
        "genre": normalize_whitespace(message.get("type") or ""),
        "abstract": abstract,
        "from": "crossref",
    }


def build_search_queries(item: Dict[str, Any]) -> List[str]:
    name = normalize_whitespace(item.get("name") or "")
    category_general = normalize_whitespace(item.get("category_general") or "")
    category_detail = normalize_whitespace(item.get("category_detail") or "")
    keywords = equipment_keywords(item)

    candidates: List[str] = []
    if name:
        candidates.append(name)
    if name and category_general:
        candidates.append(f"{name} {category_general}")
    if name and category_detail:
        candidates.append(f"{name} {category_detail}")
    if category_general:
        candidates.append(category_general)

    if keywords:
        candidates.append(" ".join(keywords[:6]))

    dedup: List[str] = []
    seen = set()
    for candidate in candidates:
        normalized = normalize_whitespace(candidate)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(normalized)
    return dedup[:4]


def fetch_crossref_search_candidates(
    query: str,
    rows: int = 8,
    timeout_sec: float = 12.0,
) -> List[Dict[str, Any]]:
    query = normalize_whitespace(query)
    if not query:
        return []

    encoded_query = urllib.parse.urlencode(
        {
            "query.bibliographic": query,
            "rows": max(1, min(20, int(rows))),
            "select": "DOI,title,container-title,URL,type,issued,abstract",
        }
    )
    url = f"https://api.crossref.org/works?{encoded_query}"
    payload = http_json(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "kikidoko-rebuild/1.0 (mailto:admin@example.com)",
        },
        timeout=max(1, int(timeout_sec)),
    )
    if not payload:
        return []

    message = payload.get("message") or {}
    rows_out: List[Dict[str, Any]] = []
    for entry in message.get("items") or []:
        if not isinstance(entry, dict):
            continue
        doi = normalize_doi(entry.get("DOI"))
        title_list = entry.get("title") or []
        source_list = entry.get("container-title") or []
        title = normalize_whitespace(title_list[0] if title_list else "")
        source = normalize_whitespace(source_list[0] if source_list else "")
        url_value = normalize_whitespace(entry.get("URL") or "")
        genre = normalize_whitespace(entry.get("type") or "")
        abstract = strip_xml_tags(str(entry.get("abstract") or ""))
        issued = (((entry.get("issued") or {}).get("date-parts") or []) or [[]])[0]
        year = str(issued[0]) if issued else ""

        rows_out.append(
            {
                "doi": doi,
                "title": title,
                "source": source,
                "year": year,
                "url": url_value,
                "genre": genre,
                "abstract": abstract,
                "from": "crossref_search",
            }
        )
    return rows_out


def resolve_manual_translation(text: str, cache: Dict[str, str]) -> str:
    value = normalize_whitespace(text)
    if not value:
        return ""
    if has_kana(value):
        return value
    cache_key = str(abs(hash(value)))
    translated = normalize_whitespace(cache.get(cache_key, ""))
    if translated and has_kana(translated):
        return translated
    return ""


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_snapshot(snapshot_path: Path) -> Dict[str, Any]:
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(snapshot_path: Path, payload: Dict[str, Any]) -> None:
    with gzip.open(snapshot_path, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


def append_update_history(history_path: Path, entry: Dict[str, Any]) -> None:
    current = load_json(history_path, {"entries": []})
    entries = current.get("entries")
    if not isinstance(entries, list):
        entries = []
    entries.insert(0, entry)
    current["entries"] = entries
    save_json(history_path, current)


def build_default_usage(name: str) -> Tuple[str, List[str]]:
    summary = f"{name}に紐づく要旨付き関連論文は現在確認できませんでした。公開情報をご確認ください。"
    bullets = [
        "関連論文は要旨取得可能な候補のみを採用対象としています。",
        "該当機器の詳細は保有機関の公開情報と原著論文本文を優先して確認してください。",
    ]
    return summary, bullets


def pick_fetch_mode(fetch_mode: str, has_good: bool, status: str) -> bool:
    if fetch_mode == "none":
        return False
    if fetch_mode == "all-no-good":
        return not has_good
    # ready-only
    return (not has_good) and status == "ready"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild paper metadata in equipment snapshot")
    parser.add_argument(
        "--snapshot",
        default="frontend/dist/equipment_snapshot.json.gz",
        help="Path to equipment_snapshot.json.gz",
    )
    parser.add_argument(
        "--history",
        default="frontend/dist/update-history.json",
        help="Path to update history JSON",
    )
    parser.add_argument(
        "--cache-dir",
        default="tools/cache",
        help="Directory for fetch/translation caches",
    )
    parser.add_argument(
        "--translation-queue",
        default="tools/translation_queue.jsonl",
        help="Path to JSONL file for manual translation queue",
    )
    parser.add_argument(
        "--source-snapshot",
        default="",
        help="Optional source snapshot (.json.gz) used for paper replacement candidates",
    )
    parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.05,
        help="Minimum relevance score to keep a paper",
    )
    parser.add_argument(
        "--max-papers-per-item",
        type=int,
        default=3,
        help="Max papers to keep for each equipment",
    )
    parser.add_argument(
        "--fetch-mode",
        choices=["ready-only", "all-no-good", "none"],
        default="ready-only",
        help="When to fetch missing abstracts by DOI",
    )
    parser.add_argument(
        "--manual-translation-only",
        action="store_true",
        default=True,
        help="Manual translation queue only (network translation is disabled)",
    )
    parser.add_argument(
        "--translate-sleep",
        type=float,
        default=0.0,
        help="Deprecated no-op (network translation disabled)",
    )
    parser.add_argument(
        "--translate-timeout",
        type=float,
        default=8.0,
        help="Deprecated no-op (network translation disabled)",
    )
    parser.add_argument(
        "--max-fetch-attempts",
        type=int,
        default=0,
        help="Maximum network fetch attempts for missing abstracts (0 = unlimited)",
    )
    parser.add_argument(
        "--fetch-timeout",
        type=float,
        default=8.0,
        help="Timeout (seconds) for each abstract metadata fetch request",
    )
    parser.add_argument(
        "--search-timeout",
        type=float,
        default=6.0,
        help="Timeout (seconds) for each Crossref search request",
    )
    parser.add_argument(
        "--search-rows",
        type=int,
        default=6,
        help="Number of Crossref rows to inspect per query",
    )
    parser.add_argument(
        "--max-search-attempts",
        type=int,
        default=180,
        help="Maximum Crossref search attempts for no_results items (0 = unlimited)",
    )
    parser.add_argument(
        "--max-translate-attempts",
        type=int,
        default=0,
        help="Deprecated no-op (network translation disabled)",
    )
    parser.add_argument(
        "--require-fetched-min",
        type=int,
        default=0,
        help="Fail when fetched_abstracts is below this threshold",
    )
    parser.add_argument(
        "--require-translated-min",
        type=int,
        default=0,
        help="Fail when translated_ja is below this threshold",
    )
    parser.add_argument(
        "--require-bad-ja-remaining-max",
        type=int,
        default=0,
        help="Fail when bad Japanese translations remain above this threshold",
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    history_path = (root / args.history).resolve()
    cache_dir = (root / args.cache_dir).resolve()
    queue_path = (root / args.translation_queue).resolve()

    if not snapshot_path.exists():
        print(f"Snapshot not found: {snapshot_path}", file=sys.stderr)
        return 1

    env = parse_env_file((root / "frontend/.env.local").resolve())
    elsevier_api_key = env.get("VITE_ELSEVIER_API_KEY", "")

    fetch_cache_path = cache_dir / "paper_fetch_cache.json"
    search_cache_path = cache_dir / "paper_search_cache.json"
    translation_cache_path = cache_dir / "translation_cache.json"
    checkpoint_path = cache_dir / "translation_checkpoint.json"

    fetch_cache: Dict[str, Any] = load_json(fetch_cache_path, {})
    search_cache: Dict[str, Any] = load_json(search_cache_path, {})
    translation_cache: Dict[str, str] = load_json(translation_cache_path, {})

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items")
    if not isinstance(items, list):
        print("Invalid snapshot structure: items is not a list", file=sys.stderr)
        return 1

    source_snapshot_path: Optional[Path] = None
    source_index: Dict[str, Dict[str, Any]] = {}
    if str(args.source_snapshot or "").strip():
        source_snapshot_path = (root / str(args.source_snapshot)).resolve()
        if not source_snapshot_path.exists():
            print(f"Source snapshot not found: {source_snapshot_path}", file=sys.stderr)
            return 1
        source_snapshot = load_snapshot(source_snapshot_path)
        source_items = source_snapshot.get("items")
        if not isinstance(source_items, list):
            print("Invalid source snapshot structure: items is not a list", file=sys.stderr)
            return 1
        source_index = build_source_index(source_items)

    now = utc_now_iso()

    total_papers_before = 0
    total_papers_after = 0
    ready_before = 0
    ready_after = 0
    no_results_before = 0
    no_results_after = 0
    newly_ready_count = 0
    placeholder_before = 0
    placeholder_after = 0
    fetched_count = 0
    translated_count = 0
    fetch_network_attempts = 0
    search_network_attempts = 0
    translate_network_attempts = 0
    removed_placeholder_count = 0
    missing_abstract_ja_after = 0
    removed_low_relevance_count = 0
    replaced_from_source_items = 0
    source_papers_imported = 0
    search_candidates_imported = 0
    bad_ja_detected = 0
    bad_ja_fixed = 0
    bad_ja_remaining = 0

    translation_queue: List[Dict[str, Any]] = []

    def resolve_missing_by_doi(doi: str) -> Optional[Dict[str, Any]]:
        nonlocal fetched_count, fetch_network_attempts

        doi = normalize_doi(doi)
        if not doi:
            return None

        cached = fetch_cache.get(doi)
        if isinstance(cached, dict):
            if cached.get("missing"):
                return None
            return cached

        max_fetch_attempts = max(0, int(args.max_fetch_attempts))
        if max_fetch_attempts > 0 and fetch_network_attempts >= max_fetch_attempts:
            return None
        fetch_network_attempts += 1

        meta: Optional[Dict[str, Any]] = None
        if elsevier_api_key:
            meta = fetch_elsevier_metadata(
                doi,
                elsevier_api_key,
                timeout_sec=max(1.0, float(args.fetch_timeout)),
            )
        if not meta:
            meta = fetch_crossref_metadata(doi, timeout_sec=max(1.0, float(args.fetch_timeout)))

        if not meta:
            fetch_cache[doi] = {"missing": True, "updated_at": now}
            return None

        meta["updated_at"] = now
        fetch_cache[doi] = meta
        fetched_count += 1
        return meta

    def translate_abstract_ja(abstract: str) -> str:
        nonlocal translated_count
        translated = resolve_manual_translation(abstract, translation_cache)
        if translated:
            translated_count += 1
        return translated

    def search_no_results_candidates(item: Dict[str, Any]) -> List[Dict[str, Any]]:
        nonlocal search_network_attempts

        max_search_attempts = max(0, int(args.max_search_attempts))
        rows = max(1, int(args.search_rows))
        timeout = max(1.0, float(args.search_timeout))
        combined: List[Dict[str, Any]] = []

        for query in build_search_queries(item):
            cache_key = query.lower()
            cached_rows = search_cache.get(cache_key)
            if isinstance(cached_rows, list):
                candidates = [row for row in cached_rows if isinstance(row, dict)]
            else:
                if max_search_attempts > 0 and search_network_attempts >= max_search_attempts:
                    break
                search_network_attempts += 1
                candidates = fetch_crossref_search_candidates(query, rows=rows, timeout_sec=timeout)
                search_cache[cache_key] = candidates

            if candidates:
                combined = merge_candidate_papers(combined, candidates)

        return combined

    for item in items:
        current_papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        papers = [dict(p) for p in current_papers if isinstance(p, dict)]
        existing_usage_insights = sanitize_usage_insights(item.get("usage_insights"))
        status_before = str(item.get("papers_status") or "")
        if status_before == "ready":
            ready_before += 1
        if status_before == "no_results_verified":
            no_results_before += 1

        total_papers_before += len(papers)
        placeholder_before += sum(1 for p in papers if is_placeholder_abstract(p.get("abstract")))

        has_good_existing = any(not is_placeholder_abstract(p.get("abstract")) for p in papers)

        if source_index and not has_good_existing:
            source_item = None
            for key in snapshot_item_keys(item):
                if key in source_index:
                    source_item = source_index[key]
                    break

            if source_item and isinstance(source_item.get("papers"), list):
                source_papers = [p for p in source_item.get("papers") if isinstance(p, dict)]
                if source_papers:
                    before_len = len(papers)
                    papers = merge_candidate_papers(papers, source_papers)
                    imported = max(0, len(papers) - before_len)
                    if imported > 0:
                        replaced_from_source_items += 1
                        source_papers_imported += imported
                    has_good_existing = any(
                        not is_placeholder_abstract(p.get("abstract")) for p in papers
                    )

        if status_before == "no_results_verified" and not has_good_existing:
            searched_papers = search_no_results_candidates(item)
            if searched_papers:
                before_len = len(papers)
                papers = merge_candidate_papers(papers, searched_papers)
                search_candidates_imported += max(0, len(papers) - before_len)
                has_good_existing = any(
                    not is_placeholder_abstract(p.get("abstract")) for p in papers
                )

        allow_fetch = pick_fetch_mode(args.fetch_mode, has_good_existing, status_before)

        rebuilt: List[Dict[str, Any]] = []

        for paper_index, paper in enumerate(papers):
            doi = normalize_doi(paper.get("doi"))
            title = normalize_whitespace(paper.get("title") or "")
            source = normalize_whitespace(paper.get("source") or "")
            year = normalize_whitespace(paper.get("year") or "")
            genre = normalize_whitespace(paper.get("genre") or "")
            genre_ja = normalize_whitespace(paper.get("genre_ja") or "")
            url = canonical_paper_url(paper.get("url"), doi)

            abstract = normalize_whitespace(paper.get("abstract") or "")
            abstract_ja = normalize_whitespace(paper.get("abstract_ja") or "")
            bad_ja_initial = False

            if is_placeholder_abstract(abstract) or not abstract:
                meta = None
                # In ready-only mode, fetch only first placeholder candidate to keep runtime predictable.
                should_fetch_this = allow_fetch and doi and (
                    args.fetch_mode != "ready-only" or paper_index == 0
                )
                if should_fetch_this:
                    meta = resolve_missing_by_doi(doi)

                if meta:
                    abstract = normalize_whitespace(meta.get("abstract") or "")
                    title = title or normalize_whitespace(meta.get("title") or "")
                    source = source or normalize_whitespace(meta.get("source") or "")
                    year = year or normalize_whitespace(meta.get("year") or "")
                    genre = genre or normalize_whitespace(meta.get("genre") or "")
                    url = canonical_paper_url(meta.get("url") or url, doi)

                    if not abstract_ja or is_placeholder_abstract(abstract_ja):
                        translated = translate_abstract_ja(abstract)
                        if translated:
                            abstract_ja = translated

            if is_placeholder_abstract(abstract) or not abstract:
                removed_placeholder_count += 1
                continue

            if abstract_ja and not is_placeholder_abstract(abstract_ja):
                if is_bad_ja_translation(abstract, abstract_ja):
                    bad_ja_detected += 1
                    bad_ja_initial = True
                    abstract_ja = ""

            if not abstract_ja or is_placeholder_abstract(abstract_ja):
                translated = translate_abstract_ja(abstract)
                if translated:
                    abstract_ja = translated
                else:
                    abstract_ja = ""
                    issue_flags = ja_issue_flags(abstract, abstract_ja)
                    translation_queue.append(
                        {
                            "paper_key": normalize_doi(doi) and f"doi:{normalize_doi(doi)}"
                            or (
                                normalize_whitespace(title).lower()
                                and f"title:{normalize_whitespace(title).lower()}"
                                or ""
                            ),
                            "equipment_id": item.get("equipment_id") or item.get("doc_id") or "",
                            "equipment_name": item.get("name") or "",
                            "doi": doi,
                            "title": title,
                            "abstract": abstract,
                            "translation_ja": "",
                            "issue_flags": issue_flags,
                        }
                    )

            final_bad_ja = is_bad_ja_translation(abstract, abstract_ja)
            if bad_ja_initial and not final_bad_ja:
                bad_ja_fixed += 1
            if final_bad_ja:
                bad_ja_remaining += 1

            normalized_paper = {
                "doi": doi,
                "title": title,
                "url": canonical_paper_url(url, doi),
                "source": source,
                "year": year,
                "genre": genre,
                "genre_ja": genre_ja or None,
                "abstract": abstract,
                "abstract_ja": abstract_ja,
            }
            usage_how_ja = normalize_whitespace(paper.get("usage_how_ja"))
            usage_what_ja = normalize_whitespace(paper.get("usage_what_ja"))
            research_fields_ja = normalize_research_fields(paper.get("research_fields_ja"))
            if usage_how_ja:
                normalized_paper["usage_how_ja"] = usage_how_ja
            if usage_what_ja:
                normalized_paper["usage_what_ja"] = usage_what_ja
            if research_fields_ja:
                normalized_paper["research_fields_ja"] = research_fields_ja

            score = relevance_score(item, normalized_paper)
            if score < float(args.min_relevance):
                removed_low_relevance_count += 1
                continue

            normalized_paper["_score"] = score
            rebuilt.append(normalized_paper)

        rebuilt.sort(
            key=lambda p: (
                float(p.get("_score") or 0.0),
                len(str(p.get("abstract") or "")),
                p.get("year") or "",
            ),
            reverse=True,
        )

        deduped: List[Dict[str, Any]] = []
        seen_keys = set()
        for paper in rebuilt:
            key = normalize_doi(paper.get("doi")) or normalize_whitespace(paper.get("title") or "")
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            paper.pop("_score", None)
            deduped.append(paper)
            if len(deduped) >= max(1, int(args.max_papers_per_item)):
                break

        item["papers"] = deduped
        item["papers_updated_at"] = now

        if deduped:
            item["papers_status"] = "ready"
            summary, bullets = build_usage_manual(item, deduped)
            item["usage_manual_summary"] = summary
            item["usage_manual_bullets"] = bullets
            item["usage_insights"] = existing_usage_insights or build_usage_insights_from_papers(deduped)
            if not item.get("usage_insights"):
                item.pop("usage_insights", None)
            ready_after += 1
            if status_before == "no_results_verified":
                newly_ready_count += 1
        else:
            item["papers_status"] = "no_results_verified"
            default_summary, default_bullets = build_default_usage(str(item.get("name") or "対象機器"))
            item["usage_manual_summary"] = default_summary
            item["usage_manual_bullets"] = default_bullets
            item.pop("usage_insights", None)
            no_results_after += 1

        total_papers_after += len(deduped)
        placeholder_after += sum(1 for p in deduped if is_placeholder_abstract(p.get("abstract")))
        missing_abstract_ja_after += sum(
            1
            for p in deduped
            if not normalize_whitespace(p.get("abstract_ja") or "")
            or is_placeholder_abstract(p.get("abstract_ja"))
        )

    require_fetched_min = int(args.require_fetched_min)
    require_translated_min = int(args.require_translated_min)
    require_bad_ja_remaining_max = max(0, int(args.require_bad_ja_remaining_max))
    fetched_gate_effective = fetched_count
    translated_gate_effective = translated_count

    if fetched_gate_effective < require_fetched_min:
        if placeholder_before == 0 and placeholder_after == 0:
            fetched_gate_effective = require_fetched_min
            print(
                "fetched_abstracts gate bypassed: no placeholder abstracts remained for fetch",
                file=sys.stderr,
            )
        else:
            print(
                (
                    f"fetched_abstracts gate failed: expected >= {require_fetched_min}, "
                    f"actual {fetched_count}"
                ),
                file=sys.stderr,
            )
            return 1

    if translated_gate_effective < require_translated_min:
        if missing_abstract_ja_after == 0:
            translated_gate_effective = require_translated_min
            print(
                "translated_ja gate bypassed: no missing abstract_ja remained for translation",
                file=sys.stderr,
            )
        else:
            print(
                (
                    f"translated_ja gate failed: expected >= {require_translated_min}, "
                    f"actual {translated_count}"
                ),
                file=sys.stderr,
            )
            return 1

    if bad_ja_remaining > require_bad_ja_remaining_max:
        print(
            (
                f"bad_ja_remaining gate failed: expected <= {require_bad_ja_remaining_max}, "
                f"actual {bad_ja_remaining}"
            ),
            file=sys.stderr,
        )
        return 1

    snapshot["generated_at"] = now
    snapshot["count"] = len(items)

    save_snapshot(snapshot_path, snapshot)

    # Validation: gzip read + count consistency.
    verify_payload = load_snapshot(snapshot_path)
    verify_items = verify_payload.get("items") if isinstance(verify_payload.get("items"), list) else []
    if len(verify_items) != len(items):
        raise RuntimeError("Snapshot verification failed: item count mismatch after write")

    save_json(fetch_cache_path, fetch_cache)
    save_json(search_cache_path, search_cache)
    save_json(translation_cache_path, translation_cache)
    save_json(
        checkpoint_path,
        {
            "updated_at": now,
            "queue_size": len(translation_queue),
            "translated_count": translated_count,
        },
    )

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", encoding="utf-8") as queue_fh:
        for row in translation_queue:
            queue_fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    history_entry = {
        "timestamp": now,
        "event": "snapshot_rebuild",
        "summary": (
            f"論文データ再構築を実施: 論文 {total_papers_before}件→{total_papers_after}件, "
            f"placeholder除去 {removed_placeholder_count}件, ready {ready_before}件→{ready_after}件, "
            f"no_results {no_results_before}件→{no_results_after}件"
        ),
        "stats": {
            "items": len(items),
            "papers_before": total_papers_before,
            "papers_after": total_papers_after,
            "placeholder_before": placeholder_before,
            "placeholder_after": placeholder_after,
            "removed_placeholder": removed_placeholder_count,
            "removed_low_relevance": removed_low_relevance_count,
            "missing_abstract_ja_after": missing_abstract_ja_after,
            "ready_before": ready_before,
            "ready_after": ready_after,
            "no_results_before": no_results_before,
            "no_results_after": no_results_after,
            "newly_ready_count": newly_ready_count,
            "fetched_abstracts": fetched_count,
            "fetched_abstracts_gate_effective": fetched_gate_effective,
            "translated_ja": translated_count,
            "translated_ja_gate_effective": translated_gate_effective,
            "bad_ja_detected": bad_ja_detected,
            "bad_ja_fixed": bad_ja_fixed,
            "bad_ja_remaining": bad_ja_remaining,
            "translation_queue": len(translation_queue),
            "fetch_mode": args.fetch_mode,
            "manual_translation_only": bool(args.manual_translation_only),
            "min_relevance": float(args.min_relevance),
            "max_fetch_attempts": int(args.max_fetch_attempts),
            "max_translate_attempts": int(args.max_translate_attempts),
            "fetch_timeout": float(args.fetch_timeout),
            "translate_timeout": float(args.translate_timeout),
            "fetch_network_attempts": fetch_network_attempts,
            "search_network_attempts": search_network_attempts,
            "translate_network_attempts": translate_network_attempts,
            "search_candidates_imported": search_candidates_imported,
            "max_search_attempts": int(args.max_search_attempts),
            "search_rows": int(args.search_rows),
            "search_timeout": float(args.search_timeout),
            "source_snapshot": str(source_snapshot_path) if source_snapshot_path else "",
            "replaced_from_source_items": replaced_from_source_items,
            "source_papers_imported": source_papers_imported,
            "require_fetched_min": require_fetched_min,
            "require_translated_min": require_translated_min,
            "require_bad_ja_remaining_max": require_bad_ja_remaining_max,
        },
    }
    append_update_history(history_path, history_entry)

    print(json.dumps(history_entry["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
