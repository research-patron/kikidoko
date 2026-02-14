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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from google.api_core import exceptions as gcloud_exceptions

from .firestore_client import get_client
from .sources import available_sources, fetch_records
from .sources.table_sources import fetch_table_source
from .sources.table_utils import TableConfig, fetch_table_records

DEFAULT_REGISTRY_PATH = "crawler/config/source_registry_low_count.json"
DEFAULT_PREFECTURE_REPORT = "crawler/low_count_prefecture_report.csv"
DEFAULT_ORG_REPORT = "crawler/low_count_org_report.csv"
DEFAULT_PRIORITY_REPORT = "crawler/low_count_org_priority.csv"
DEFAULT_MEMO_DIR = "memo"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

SPACE_RE = re.compile(r"\s+")
DDG_RESULT_RE = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class RegistryEntry:
    key: str
    org_name: str
    prefecture: str
    url: str
    parser_type: str
    source_handler: str
    category_hint: str
    external_use: str
    selectors: dict[str, Any]
    query_keywords: list[str]
    enabled: bool
    official_page_status: str


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit low-count prefectures and prioritize supplemental scraping targets."
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
        "--summary-doc",
        default="prefecture_summary",
        help="stats document id (default: prefecture_summary).",
    )
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"Source registry path (default: {DEFAULT_REGISTRY_PATH}).",
    )
    parser.add_argument(
        "--pref-min",
        type=int,
        default=10,
        help="Minimum equipment count to treat as low-count prefecture.",
    )
    parser.add_argument(
        "--pref-max",
        type=int,
        default=99,
        help="Maximum equipment count to treat as low-count prefecture.",
    )
    parser.add_argument(
        "--org-max",
        type=int,
        default=9,
        help="Maximum organization equipment count for focused audit.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=25.0,
        help="HTTP timeout seconds for page checks and scraping estimate.",
    )
    parser.add_argument(
        "--prefecture-report-out",
        default=DEFAULT_PREFECTURE_REPORT,
        help=f"Output CSV path for prefecture report (default: {DEFAULT_PREFECTURE_REPORT}).",
    )
    parser.add_argument(
        "--org-report-out",
        default=DEFAULT_ORG_REPORT,
        help=f"Output CSV path for organization report (default: {DEFAULT_ORG_REPORT}).",
    )
    parser.add_argument(
        "--priority-report-out",
        default=DEFAULT_PRIORITY_REPORT,
        help=f"Output CSV path for priority report (default: {DEFAULT_PRIORITY_REPORT}).",
    )
    parser.add_argument(
        "--memo-out",
        default="",
        help="Memo markdown output path. Defaults to memo/YYYY-MM-DD_低件数都道府県再分析.md",
    )
    parser.add_argument(
        "--skip-query-check",
        action="store_true",
        help="Skip search query based public page verification.",
    )
    parser.add_argument(
        "--skip-observed-count",
        action="store_true",
        help="Skip counting public-page equipment records via parser.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compatibility flag: script is read-only regardless; this only labels output.",
    )
    parser.add_argument(
        "--limit-orgs",
        type=int,
        default=0,
        help="Limit number of focused organizations processed (0=all).",
    )
    return parser.parse_args(list(argv))


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return SPACE_RE.sub(" ", text).strip()


def normalize_org_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = SPACE_RE.sub("", text)
    for token in (" ", "　", "・", "･", "（", "）", "(", ")"):
        text = text.replace(token, "")
    return text.lower()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return WORKSPACE_ROOT / path


def fetch_url_text(session: requests.Session, url: str, timeout: float) -> str:
    errors: list[str] = []
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        errors.append(str(exc))

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
        errors.append(
            f"curl attempt {attempt + 1} rc={result.returncode} err={result.stderr.decode('utf-8', errors='replace')[:160]}"
        )
        if attempt < 2:
            time.sleep(attempt + 1)

    raise RuntimeError(f"failed requests+curl for {url}: {' | '.join(errors)}")


def run_firestore_with_retry(fn, label: str, retries: int = 4) -> Any:
    for attempt in range(retries):
        try:
            return fn()
        except (
            gcloud_exceptions.ServiceUnavailable,
            gcloud_exceptions.RetryError,
            gcloud_exceptions.ResourceExhausted,
            gcloud_exceptions.GoogleAPICallError,
        ) as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(
                    f"Firestore operation failed: {label} (attempt={attempt + 1}/{retries}) error={exc}"
                ) from exc
            wait_seconds = min(120, 10 * (attempt + 1))
            print(
                f"[warn] Firestore retry for {label}: "
                f"attempt={attempt + 1}/{retries} wait={wait_seconds}s error={exc}",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)


def parse_registry(path: Path) -> list[RegistryEntry]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries_raw = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries_raw, list):
        return []

    entries: list[RegistryEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        key = clean_text(item.get("key", ""))
        org_name = clean_text(item.get("org_name", ""))
        if not key or not org_name:
            continue
        selectors = item.get("selectors") if isinstance(item.get("selectors"), dict) else {}
        query_keywords_raw = item.get("query_keywords") if isinstance(item.get("query_keywords"), list) else []
        query_keywords = [clean_text(value) for value in query_keywords_raw if clean_text(value)]
        entries.append(
            RegistryEntry(
                key=key,
                org_name=org_name,
                prefecture=clean_text(item.get("prefecture", "")),
                url=clean_text(item.get("url", "")),
                parser_type=clean_text(item.get("parser_type", "table_utils")) or "table_utils",
                source_handler=clean_text(item.get("source_handler", "")),
                category_hint=clean_text(item.get("category_hint", "")),
                external_use=clean_text(item.get("external_use", "")),
                selectors=selectors,
                query_keywords=query_keywords,
                enabled=bool(item.get("enabled", True)),
                official_page_status=clean_text(item.get("official_page_status", "")),
            )
        )
    return entries


def build_registry_index(entries: list[RegistryEntry]) -> tuple[dict[str, RegistryEntry], list[tuple[str, RegistryEntry]]]:
    by_exact: dict[str, RegistryEntry] = {}
    partial: list[tuple[str, RegistryEntry]] = []
    for entry in entries:
        normalized = normalize_org_name(entry.org_name)
        if not normalized:
            continue
        by_exact[normalized] = entry
        partial.append((normalized, entry))
    partial.sort(key=lambda item: len(item[0]), reverse=True)
    return by_exact, partial


def match_registry_entry(
    org_name: str,
    by_exact: dict[str, RegistryEntry],
    partial: list[tuple[str, RegistryEntry]],
) -> tuple[RegistryEntry | None, str]:
    normalized = normalize_org_name(org_name)
    if not normalized:
        return None, "empty"
    if normalized in by_exact:
        return by_exact[normalized], "exact"
    for key, entry in partial:
        if normalized.startswith(key):
            return entry, "prefix"
    for key, entry in partial:
        if key in normalized:
            return entry, "contains"
    return None, "none"


def decode_search_url(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    uddg = query.get("uddg")
    if not uddg:
        return url
    return unquote(uddg[0])


def extract_search_candidates(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw_url in DDG_RESULT_RE.findall(html):
        decoded = decode_search_url(raw_url)
        if not decoded or decoded in seen:
            continue
        host = (urlparse(decoded).netloc or "").lower()
        if not host or "eqnet.jp" in host or "duckduckgo.com" in host:
            continue
        seen.add(decoded)
        urls.append(decoded)
    return urls


def query_public_page_candidates(
    session: requests.Session,
    org_name: str,
    query_keywords: list[str],
    timeout: float,
) -> tuple[list[str], str]:
    keyword = " ".join(query_keywords) if query_keywords else f"{org_name} 機器 共用"
    url = f"https://duckduckgo.com/html/?q={quote_plus(keyword)}"
    try:
        html = fetch_url_text(session, url, timeout)
    except Exception as exc:
        return [], f"query_failed:{exc}"
    candidates = extract_search_candidates(html)
    return candidates[:10], "ok"


def verify_public_page_url(session: requests.Session, url: str, timeout: float) -> tuple[str, int, str]:
    if not url:
        return "未確認", 0, "no_url"
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        code = int(response.status_code)
        if 200 <= code < 400:
            return "公開あり", code, "ok"
        if code == 404:
            return "公開なし", code, "not_found"
        return "未確認", code, f"http_{code}"
    except requests.RequestException as exc:
        try:
            fetch_url_text(session=session, url=url, timeout=timeout)
            return "公開あり", 200, "ok_curl_fallback"
        except Exception as fallback_exc:
            return "未確認", 0, f"network_unresolved:{exc} / fallback={fallback_exc}"


def estimate_registry_count(entry: RegistryEntry, timeout: int, limit: int = 0) -> tuple[int | None, str]:
    parser_type = entry.parser_type
    try:
        if parser_type == "source_handler":
            source_key = entry.source_handler or entry.key
            if source_key not in available_sources():
                return None, f"unknown_source_handler:{source_key}"
            rows = fetch_records(source_key, timeout=timeout, limit=limit)
            return len(rows), "ok"

        if parser_type in {"table_utils", "table"}:
            if not entry.url:
                return None, "missing_url"
            selectors = entry.selectors or {}
            config = TableConfig(
                key=entry.key,
                org_name=entry.org_name,
                url=entry.url,
                org_type=clean_text(selectors.get("org_type", "")),
                category_hint=entry.category_hint,
                external_use=entry.external_use,
                link_patterns=tuple(selectors.get("link_patterns", [])),
                required_table_links=tuple(selectors.get("required_table_links", [])),
                force_apparent_encoding=bool(selectors.get("force_apparent_encoding", False)),
            )
            rows = fetch_table_records(config=config, timeout=timeout, limit=limit)
            return len(rows), "ok"

        if parser_type == "table_source":
            rows = fetch_table_source(source_key=entry.key, timeout=timeout, limit=limit)
            return len(rows), "ok"

        if parser_type == "query_only":
            return None, "query_only"

        return None, f"unsupported_parser:{parser_type}"
    except Exception as exc:
        return None, f"network_unresolved:{exc}"


def build_prefecture_stats_from_summary(
    client,
    summary_doc: str,
) -> dict[str, int]:
    snap = run_firestore_with_retry(
        lambda: client.collection("stats").document(summary_doc).get(),
        label=f"stats/{summary_doc} get",
    )
    if not snap.exists:
        return {}
    data = snap.to_dict() or {}
    counts = data.get("prefecture_counts")
    if not isinstance(counts, dict):
        return {}
    output: dict[str, int] = {}
    for key, value in counts.items():
        prefecture = clean_text(key)
        if not prefecture:
            continue
        try:
            output[prefecture] = int(value)
        except (TypeError, ValueError):
            continue
    return output


def collect_prefecture_org_stats(
    client,
    target_prefectures: list[str],
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    prefecture_counts: dict[str, int] = {}
    prefecture_org_stats: dict[str, dict[str, Any]] = {}

    collection = client.collection("equipment")
    for prefecture in target_prefectures:
        query = collection.where("prefecture", "==", prefecture)
        org_counts: Counter[str] = Counter()
        org_source_counts: dict[str, Counter[str]] = defaultdict(Counter)
        doc_count = 0

        docs = run_firestore_with_retry(
            lambda: list(query.stream()),
            label=f"equipment stream prefecture={prefecture}",
        )
        for doc in docs:
            data = doc.to_dict() or {}
            org_name = clean_text(data.get("org_name", "")) or "(機関名未設定)"
            source_site = clean_text(data.get("source_site", "")) or "(empty)"
            org_counts[org_name] += 1
            org_source_counts[org_name][source_site] += 1
            doc_count += 1

        prefecture_counts[prefecture] = doc_count
        prefecture_org_stats[prefecture] = {
            "org_counts": org_counts,
            "org_source_counts": org_source_counts,
        }

    return prefecture_counts, prefecture_org_stats


def build_judgement(
    official_page_status: str,
    observed_count: int | None,
    firestore_count: int,
) -> tuple[str, int | None]:
    if official_page_status == "公開なし":
        return "妥当", None

    if observed_count is None:
        return "要確認", None

    diff = observed_count - firestore_count
    if abs(diff) <= 1:
        return "妥当", diff
    if diff >= 2:
        return "不足", diff
    return "要確認", diff


def build_priority(eqnet_only: bool, page_status: str, judgement: str) -> tuple[int, str]:
    if eqnet_only and page_status == "公開あり" and judgement == "不足":
        return 1, "eqnet only かつ 公式ページ差分あり"
    if eqnet_only and page_status == "公開あり":
        return 2, "eqnet only かつ 公式ページあり"
    if eqnet_only and page_status in {"未確認", "公開なし"}:
        return 3, "eqnet only だが外部ページ未確認"
    if judgement == "不足":
        return 4, "差分不足あり"
    return 9, "低優先"


def default_memo_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return resolve_workspace_path(DEFAULT_MEMO_DIR) / f"{today}_低件数都道府県再分析.md"


def write_memo(path: Path, rows: list[dict[str, Any]], prefecture_rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    ensure_parent(path)
    shortage = [row for row in rows if row["count_judgement"] == "不足"]
    unresolved = [row for row in rows if "network_unresolved" in row["network_status"]]
    query_unknown = [row for row in rows if row["official_page_status"] == "未確認"]

    lines: list[str] = []
    lines.append(f"# 低件数都道府県 再分析メモ ({datetime.now(timezone.utc).isoformat()})")
    lines.append("")
    lines.append("## 条件")
    lines.append(f"- 2桁都道府県判定: {args.pref_min} <= 件数 <= {args.pref_max}")
    lines.append(f"- 重点機関判定: 機関件数 <= {args.org_max}")
    lines.append(f"- Dry-run: {args.dry_run}")
    lines.append("")
    lines.append("## 都道府県サマリー")
    for row in prefecture_rows:
        lines.append(
            f"- {row['prefecture']}: summary={row['equipment_count_summary']}件 firestore={row['equipment_count_firestore']}件 / 重点機関={row['one_digit_org_count']}"
        )
    lines.append("")

    if shortage:
        lines.append("## 判定")
        lines.append("- 不足判定あり。追加スクレイピングが必要です。")
        lines.append("")
        lines.append("### 不足判定機関")
        for row in sorted(shortage, key=lambda item: (item["priority"], item["prefecture"], item["org_name"])):
            lines.append(
                f"- {row['prefecture']} / {row['org_name']}: firestore={row['firestore_count']} observed={row['observed_count']} diff={row['count_diff']}"
            )
    else:
        lines.append("## 判定")
        lines.append("- 現時点の保有機器数は概ね妥当です（不足判定なし）。")

    lines.append("")
    lines.append("## 未解決")
    lines.append(f"- ネットワーク未解決: {len(unresolved)}件")
    lines.append(f"- 公式ページ未確認: {len(query_unknown)}件")
    if unresolved:
        for row in unresolved[:20]:
            lines.append(
                f"- {row['prefecture']} / {row['org_name']}: {row['network_status']}"
            )

    lines.append("")
    lines.append("## 次回対応")
    lines.append("- 優先CSVの priority=1,2 を source_registry_low_count.json へ反映")
    lines.append("- kikidoko-source-registry-sync 実行後に backfill --write-summary を再実行")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.pref_min < 0 or args.pref_max < args.pref_min:
        print("Invalid prefecture range.", file=sys.stderr)
        return 2
    if args.org_max < 0:
        print("org-max must be >= 0.", file=sys.stderr)
        return 2

    registry_entries = [
        entry for entry in parse_registry(resolve_workspace_path(args.registry)) if entry.enabled
    ]
    registry_exact, registry_partial = build_registry_index(registry_entries)

    client = get_client(args.project_id, args.credentials or None)
    try:
        summary_counts = build_prefecture_stats_from_summary(client, args.summary_doc)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not summary_counts:
        print("[warn] prefecture_summary not found or empty; falling back to direct counts.", file=sys.stderr)
        summary_counts = {}

    if summary_counts:
        target_prefectures = sorted(
            [
                prefecture
                for prefecture, count in summary_counts.items()
                if args.pref_min <= int(count) <= args.pref_max
            ]
        )
    else:
        # fallback: derive from equipment collection
        target_prefectures = []
        pref_counter: Counter[str] = Counter()
        try:
            docs = run_firestore_with_retry(
                lambda: list(client.collection("equipment").stream()),
                label="equipment full stream fallback",
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        for doc in docs:
            data = doc.to_dict() or {}
            prefecture = clean_text(data.get("prefecture", ""))
            if prefecture:
                pref_counter[prefecture] += 1
        summary_counts = dict(pref_counter)
        target_prefectures = sorted(
            [
                prefecture
                for prefecture, count in pref_counter.items()
                if args.pref_min <= int(count) <= args.pref_max
            ]
        )

    try:
        prefecture_counts, org_stats = collect_prefecture_org_stats(client, target_prefectures)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "kikidoko-low-count-audit/0.1",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
        }
    )

    prefecture_report_rows: list[dict[str, Any]] = []
    org_report_rows: list[dict[str, Any]] = []

    for prefecture in target_prefectures:
        stats = org_stats.get(prefecture, {})
        org_counts: Counter[str] = stats.get("org_counts", Counter())
        org_source_counts: dict[str, Counter[str]] = stats.get("org_source_counts", {})

        focused_orgs = [
            (org_name, count)
            for org_name, count in org_counts.items()
            if count <= args.org_max
        ]
        focused_orgs.sort(key=lambda item: (item[1], item[0]))

        if args.limit_orgs > 0:
            focused_orgs = focused_orgs[: args.limit_orgs]

        eqnet_only_count = 0
        non_eqnet_count = 0

        for org_name, firestore_count in focused_orgs:
            source_counter = org_source_counts.get(org_name, Counter())
            source_sites = sorted(source_counter.keys())
            non_eqnet_sources = [
                source
                for source in source_sites
                if source not in {"eqnet", "(empty)", ""}
            ]
            eqnet_only = len(source_sites) > 0 and len(non_eqnet_sources) == 0
            has_non_eqnet = len(non_eqnet_sources) > 0
            if eqnet_only:
                eqnet_only_count += 1
            if has_non_eqnet:
                non_eqnet_count += 1

            entry, registry_match_mode = match_registry_entry(
                org_name=org_name,
                by_exact=registry_exact,
                partial=registry_partial,
            )

            page_url = entry.url if entry else ""
            parser_type = entry.parser_type if entry else ""
            registry_key = entry.key if entry else ""

            official_page_status = "未確認"
            page_http_status = 0
            network_status = ""
            query_candidates: list[str] = []
            query_status = "skipped"

            if entry and entry.official_page_status in {"公開あり", "公開なし", "未確認"}:
                official_page_status = entry.official_page_status

            if page_url:
                checked_status, page_http_status, verify_note = verify_public_page_url(
                    session=session,
                    url=page_url,
                    timeout=args.timeout,
                )
                official_page_status = checked_status
                network_status = verify_note
            elif not args.skip_query_check:
                query_candidates, query_status = query_public_page_candidates(
                    session=session,
                    org_name=org_name,
                    query_keywords=entry.query_keywords if entry else [],
                    timeout=args.timeout,
                )
                if query_candidates:
                    page_url = query_candidates[0]
                    official_page_status = "公開あり"
                if query_status != "ok":
                    network_status = query_status

            observed_count = None
            observed_note = "skipped"
            if entry and not args.skip_observed_count:
                observed_count, observed_note = estimate_registry_count(
                    entry=entry,
                    timeout=max(5, int(args.timeout)),
                    limit=0,
                )
                if observed_note.startswith("network_unresolved"):
                    network_status = observed_note

            count_judgement, count_diff = build_judgement(
                official_page_status=official_page_status,
                observed_count=observed_count,
                firestore_count=firestore_count,
            )
            priority, priority_reason = build_priority(
                eqnet_only=eqnet_only,
                page_status=official_page_status,
                judgement=count_judgement,
            )

            org_report_rows.append(
                {
                    "prefecture": prefecture,
                    "org_name": org_name,
                    "firestore_count": firestore_count,
                    "source_sites": " | ".join(source_sites),
                    "eqnet_only": eqnet_only,
                    "has_non_eqnet": has_non_eqnet,
                    "registry_key": registry_key,
                    "registry_match_mode": registry_match_mode,
                    "parser_type": parser_type,
                    "official_page_status": official_page_status,
                    "official_page_url": page_url,
                    "page_http_status": page_http_status,
                    "query_status": query_status,
                    "query_candidate_count": len(query_candidates),
                    "observed_count": observed_count if observed_count is not None else "",
                    "observed_note": observed_note,
                    "count_diff": count_diff if count_diff is not None else "",
                    "count_judgement": count_judgement,
                    "priority": priority,
                    "priority_reason": priority_reason,
                    "network_status": network_status,
                }
            )

        prefecture_report_rows.append(
            {
                "prefecture": prefecture,
                "equipment_count_summary": int(summary_counts.get(prefecture, 0)),
                "equipment_count_firestore": int(prefecture_counts.get(prefecture, 0)),
                "organization_count": len(org_counts),
                "one_digit_org_count": len(focused_orgs),
                "eqnet_only_org_count": eqnet_only_count,
                "non_eqnet_org_count": non_eqnet_count,
            }
        )

    org_report_rows.sort(
        key=lambda item: (
            int(item["priority"]),
            item["prefecture"],
            int(item["firestore_count"]),
            item["org_name"],
        )
    )

    priority_rows = [
        row
        for row in org_report_rows
        if int(row["priority"]) <= 4
    ]

    prefecture_report_path = resolve_workspace_path(args.prefecture_report_out)
    org_report_path = resolve_workspace_path(args.org_report_out)
    priority_report_path = resolve_workspace_path(args.priority_report_out)

    write_csv(
        prefecture_report_path,
        fieldnames=[
            "prefecture",
            "equipment_count_summary",
            "equipment_count_firestore",
            "organization_count",
            "one_digit_org_count",
            "eqnet_only_org_count",
            "non_eqnet_org_count",
        ],
        rows=prefecture_report_rows,
    )
    write_csv(
        org_report_path,
        fieldnames=[
            "prefecture",
            "org_name",
            "firestore_count",
            "source_sites",
            "eqnet_only",
            "has_non_eqnet",
            "registry_key",
            "registry_match_mode",
            "parser_type",
            "official_page_status",
            "official_page_url",
            "page_http_status",
            "query_status",
            "query_candidate_count",
            "observed_count",
            "observed_note",
            "count_diff",
            "count_judgement",
            "priority",
            "priority_reason",
            "network_status",
        ],
        rows=org_report_rows,
    )
    write_csv(
        priority_report_path,
        fieldnames=[
            "priority",
            "priority_reason",
            "prefecture",
            "org_name",
            "firestore_count",
            "official_page_status",
            "official_page_url",
            "count_judgement",
            "observed_count",
            "count_diff",
            "parser_type",
            "registry_key",
            "network_status",
        ],
        rows=priority_rows,
    )

    memo_path = resolve_workspace_path(args.memo_out) if args.memo_out else default_memo_path()
    write_memo(path=memo_path, rows=org_report_rows, prefecture_rows=prefecture_report_rows, args=args)

    shortage_count = sum(1 for row in org_report_rows if row["count_judgement"] == "不足")
    unresolved_count = sum(1 for row in org_report_rows if "network_unresolved" in row["network_status"])

    print(
        "Done. "
        f"prefectures={len(prefecture_report_rows)} "
        f"focused_orgs={len(org_report_rows)} "
        f"priority_rows={len(priority_rows)} "
        f"shortage={shortage_count} "
        f"network_unresolved={unresolved_count}"
    )
    print(f"Prefecture report: {prefecture_report_path}")
    print(f"Org report: {org_report_path}")
    print(f"Priority report: {priority_report_path}")
    print(f"Memo: {memo_path}")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
