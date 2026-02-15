from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .firestore_client import get_client
from .paper_abstract_sources import build_fallback_abstract, clean_abstract_text, normalize_doi

DEFAULT_MODEL = "gpt-5.3-codex"
RULE_BASED_EDITOR = "rule-based-codex"

RULE_USAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "化学組成の同定・定量",
        (
            "mass spectrometry",
            "ms/ms",
            "lc-ms",
            "gc-ms",
            "chromatography",
            "hplc",
            "gas chromatography",
            "liquid chromatography",
            "nmr",
            "ftir",
            "raman",
            "metabol",
            "compound",
            "chemical",
            "化学",
            "分子",
            "定量",
            "同定",
            "質量分析",
            "クロマト",
        ),
    ),
    (
        "材料・表面特性の評価",
        (
            "material",
            "surface",
            "coating",
            "thin film",
            "nanoparticle",
            "microstructure",
            "crystal",
            "xrd",
            "sem",
            "tem",
            "afm",
            "morphology",
            "材料",
            "表面",
            "結晶",
            "薄膜",
            "ナノ",
        ),
    ),
    (
        "生体試料の解析",
        (
            "clinical",
            "patient",
            "biomarker",
            "cell",
            "tissue",
            "gene",
            "genome",
            "proteom",
            "disease",
            "diagnos",
            "bio",
            "生体",
            "細胞",
            "組織",
            "診断",
            "疾患",
            "バイオ",
        ),
    ),
    (
        "環境・エネルギー関連の評価",
        (
            "environment",
            "pollut",
            "water",
            "soil",
            "air",
            "emission",
            "battery",
            "catalyst",
            "energy",
            "electrochemical",
            "photocatal",
            "環境",
            "水質",
            "土壌",
            "電池",
            "触媒",
            "エネルギー",
        ),
    ),
    (
        "画像化・可視化解析",
        (
            "imaging",
            "image",
            "microscopy",
            "tomography",
            "ct",
            "mri",
            "fluorescence",
            "confocal",
            "visualization",
            "顕微",
            "画像",
            "可視化",
            "断層",
        ),
    ),
    (
        "工程最適化・プロセス検証",
        (
            "optimization",
            "optimisation",
            "process",
            "reaction",
            "synthesis",
            "manufactur",
            "quality control",
            "validation",
            "parameter",
            "最適化",
            "工程",
            "プロセス",
            "反応",
            "検証",
        ),
    ),
)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate usage_manual fields from paper abstracts "
            "(default: rule-based local generation)."
        ),
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
        "--generation-mode",
        choices=["rule-based", "openai"],
        default="rule-based",
        help="Generation mode (default: rule-based).",
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="OpenAI API key (used only when --generation-mode=openai).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--api-base",
        default="https://api.openai.com/v1",
        help="OpenAI API base URL (default: https://api.openai.com/v1).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="HTTP timeout seconds (default: 90).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.15,
        help="Sleep seconds between doc requests.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Firestore batch write size (default: 50, max 500).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Firestore read page size (default: 200).",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=0,
        help="Process at most N target docs (0 = no limit).",
    )
    parser.add_argument(
        "--resume-from-doc-id",
        default="",
        help="Resume from document id (exclusive).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Max retries for OpenAI call (default: 4).",
    )
    parser.add_argument(
        "--fill-abstract-ja",
        action="store_true",
        help="Also update papers[].abstract_ja* fields (default: off).",
    )
    parser.add_argument(
        "--skip-manual",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Skip docs where usage_manual_editor is manual "
            "(default: true; pass --no-skip-manual to include them)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write updates to Firestore.",
    )
    parser.add_argument(
        "--done-csv",
        default="crawler/usage_from_abstract_done.csv",
        help="Output CSV path for successful docs.",
    )
    parser.add_argument(
        "--error-csv",
        default="crawler/usage_from_abstract_errors.csv",
        help="Output CSV path for failed docs.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=25,
        help="Print progress every N docs (default: 25).",
    )
    parser.add_argument(
        "--flush-logs",
        action="store_true",
        help="Force flush logs after each progress update.",
    )
    return parser.parse_args(list(argv))


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return Path(__file__).resolve().parents[3] / path


def write_csv(path_value: str, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
    path = resolve_workspace_path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def fetch_page(query, retries: int = 4):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return list(query.stream())
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            time.sleep(1.5 + attempt * 1.2)
    if last_error:
        raise last_error
    return []


def commit_batch(batch, pending: int, sleep_seconds: float) -> None:
    if pending <= 0:
        return
    batch.commit()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def build_input_papers(raw_papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    papers: list[dict[str, Any]] = []
    for paper in raw_papers:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(str(paper.get("doi", "")))
        if not doi:
            continue
        title = clean_abstract_text(str(paper.get("title", "")))
        year = clean_abstract_text(str(paper.get("year", "")))
        genre = clean_abstract_text(str(paper.get("genre", "")))
        abstract = clean_abstract_text(str(paper.get("abstract", "")))
        from_fallback = str(paper.get("abstract_source", "")) == "fallback"
        if not abstract:
            abstract = build_fallback_abstract(paper)
            from_fallback = True
        papers.append(
            {
                "doi": doi,
                "title": title,
                "year": year,
                "genre": genre,
                "abstract": abstract,
                "is_fallback": from_fallback,
            }
        )
        if len(papers) >= 3:
            break
    return papers


def _extract_output_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for message in output:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"output_text", "text"}:
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _fallback_usage_summary(doc_data: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    name = clean_abstract_text(str(doc_data.get("name", "")))
    category = clean_abstract_text(str(doc_data.get("category_general", "")))
    if name and category:
        return f"{name}は{category}分野の研究で利用され、関連論文の要旨から用途傾向を整理しています。"
    if name:
        return f"{name}は関連論文の要旨を基に、利用シーンを整理した機器です。"
    if papers:
        return "関連論文の要旨を基に、当該機器の代表的な利用シーンを整理しています。"
    return "要旨情報が不足しているため、機器の利用シーンを暫定的に整理しています。"


def _fallback_usage_bullets(papers: list[dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    if papers:
        first = papers[0]
        if first.get("title"):
            bullets.append(f"論文題名「{first['title']}」に関連する実験・分析用途が中心です。")
    bullets.append("研究目的に応じて測定条件・試料条件を調整して利用します。")
    bullets.append("詳細な再現条件は原論文本文で確認してください。")
    bullets.append("初回利用時は担当機関へ事前相談し、運用条件を確認してください。")
    normalized = [clean_abstract_text(item) for item in bullets if clean_abstract_text(item)]
    while len(normalized) < 3:
        normalized.append("関連論文を基に利用条件を整理し、実運用前に原文で確認してください。")
    return normalized[:3]


def _fallback_paper_abstract_ja(paper: dict[str, Any]) -> str:
    title = clean_abstract_text(str(paper.get("title", "")))
    year = clean_abstract_text(str(paper.get("year", "")))
    genre = clean_abstract_text(str(paper.get("genre", "")))
    if title:
        detail = []
        if year:
            detail.append(f"{year}年")
        if genre:
            detail.append(f"{genre}分野")
        suffix = f"（{'・'.join(detail)}）" if detail else ""
        return f"論文「{title}」{suffix}の要旨情報が不足しているため、原文確認を前提とした暫定要約です。"
    return "要旨情報が不足しているため、原文確認を前提とした暫定要約です。"


def _build_response_request(
    doc_data: dict[str, Any],
    papers: list[dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["usage_summary", "usage_bullets", "paper_abstracts"],
        "properties": {
            "usage_summary": {"type": "string", "minLength": 10},
            "usage_bullets": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 5},
            },
            "paper_abstracts": {
                "type": "array",
                "minItems": len(papers),
                "maxItems": len(papers),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["doi", "abstract_ja", "is_fallback"],
                    "properties": {
                        "doi": {"type": "string", "minLength": 3},
                        "abstract_ja": {"type": "string", "minLength": 10},
                        "is_fallback": {"type": "boolean"},
                    },
                },
            },
        },
    }
    prompt_payload = {
        "equipment": {
            "name": clean_abstract_text(str(doc_data.get("name", ""))),
            "org_name": clean_abstract_text(str(doc_data.get("org_name", ""))),
            "category_general": clean_abstract_text(str(doc_data.get("category_general", ""))),
            "category_detail": clean_abstract_text(str(doc_data.get("category_detail", ""))),
            "prefecture": clean_abstract_text(str(doc_data.get("prefecture", ""))),
        },
        "papers": papers,
        "requirements": {
            "language": "ja",
            "summary_focus": "機器の使われ方",
            "bullets_count": 3,
            "notes": [
                "誇張や断定を避ける",
                "要旨から読み取れる範囲に限定する",
                "一般利用者が理解しやすい表現にする",
            ],
        },
    }
    return {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "あなたは研究機器データ整備担当です。"
                            "与えられた論文要旨から、機器の使われ方を日本語で簡潔に要約してください。"
                            "出力は必ず指定JSONスキーマに一致させてください。"
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(prompt_payload, ensure_ascii=False)}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "usage_from_abstract",
                "schema": schema,
                "strict": True,
            }
        },
    }


def _call_openai_usage(
    session: requests.Session,
    api_base: str,
    api_key: str,
    timeout: float,
    max_retries: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = "openai_request_failed"
    for attempt in range(max_retries):
        try:
            response = session.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            last_error = f"openai_request_error:{exc}"
            time.sleep(1.5 + attempt * 1.5)
            continue

        if response.status_code in (429, 500, 502, 503, 504):
            last_error = f"openai_retryable_http:{response.status_code}"
            time.sleep(1.5 + attempt * 2.0)
            continue
        if not response.ok:
            body = ""
            try:
                body = response.text[:240]
            except Exception:  # pragma: no cover - defensive
                body = ""
            last_error = f"openai_http_error:{response.status_code}:{body}"
            break

        try:
            response_payload = response.json()
        except ValueError as exc:
            last_error = f"openai_json_error:{exc}"
            time.sleep(1.2 + attempt * 1.2)
            continue

        text = _extract_output_text(response_payload if isinstance(response_payload, dict) else {})
        if not text:
            last_error = "openai_empty_output_text"
            time.sleep(1.2 + attempt * 1.2)
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = f"openai_output_json_decode_error:{exc}"
            time.sleep(1.2 + attempt * 1.2)
            continue
        if not isinstance(parsed, dict):
            last_error = "openai_output_not_object"
            time.sleep(1.2 + attempt * 1.2)
            continue
        return parsed
    raise RuntimeError(last_error)


def _category_default_label(doc_data: dict[str, Any]) -> str:
    category_detail = clean_abstract_text(str(doc_data.get("category_detail", "")))
    category_general = clean_abstract_text(str(doc_data.get("category_general", "")))
    if category_detail:
        return f"{category_detail}の測定・評価"
    if category_general:
        return f"{category_general}領域の測定・評価"
    return "基礎的な測定・評価"


def _extract_usage_labels(papers: list[dict[str, Any]], fallback_label: str) -> list[str]:
    score_map: dict[str, int] = {}
    for paper in papers:
        text = " ".join(
            [
                clean_abstract_text(str(paper.get("title", ""))),
                clean_abstract_text(str(paper.get("genre", ""))),
                clean_abstract_text(str(paper.get("abstract", ""))),
            ]
        ).lower()
        if not text:
            continue
        for label, keywords in RULE_USAGE_KEYWORDS:
            if any(keyword in text for keyword in keywords):
                score_map[label] = score_map.get(label, 0) + 1

    if not score_map:
        return [fallback_label]

    ordered = sorted(score_map.items(), key=lambda item: (-item[1], item[0]))
    labels = [item[0] for item in ordered]
    if fallback_label not in labels:
        labels.append(fallback_label)
    return labels


def _build_rule_based_usage_summary(doc_data: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    name = clean_abstract_text(str(doc_data.get("name", ""))) or "当該機器"
    labels = _extract_usage_labels(papers, _category_default_label(doc_data))
    primary = labels[0]
    secondary = labels[1] if len(labels) > 1 else ""
    lead_title = clean_abstract_text(str(papers[0].get("title", ""))) if papers else ""

    if secondary:
        summary = f"{name}は関連論文の要旨から、主に{primary}や{secondary}を目的として利用されています。"
    else:
        summary = f"{name}は関連論文の要旨から、主に{primary}を目的として利用されています。"

    if lead_title:
        summary = f"{summary} 代表例として論文「{lead_title}」などが根拠になります。"
    return clean_abstract_text(summary)


def _build_rule_based_usage_bullets(doc_data: dict[str, Any], papers: list[dict[str, Any]]) -> list[str]:
    labels = _extract_usage_labels(papers, _category_default_label(doc_data))
    primary = labels[0]
    secondary = labels[1] if len(labels) > 1 else ""

    lead_title = clean_abstract_text(str(papers[0].get("title", ""))) if papers else ""
    lead_year = clean_abstract_text(str(papers[0].get("year", ""))) if papers else ""

    if lead_title and lead_year:
        bullet_1 = f"{lead_year}年の論文「{lead_title}」などでは、{primary}目的での利用が確認できます。"
    elif lead_title:
        bullet_1 = f"論文「{lead_title}」などでは、{primary}目的での利用が確認できます。"
    else:
        bullet_1 = f"関連要旨から、{primary}を目的とした利用が中心です。"

    if secondary:
        bullet_2 = f"{secondary}にも活用され、試料や条件の比較検証に使われています。"
    else:
        bullet_2 = "測定条件・前処理条件を調整し、研究目的に応じて比較検証に使われています。"

    bullet_3 = "最終的な測定手順や再現条件は、原論文本文と機器担当者の案内で確認してください。"

    bullets = [clean_abstract_text(bullet_1), clean_abstract_text(bullet_2), clean_abstract_text(bullet_3)]
    normalized = [item for item in bullets if item]
    while len(normalized) < 3:
        normalized.append("関連論文の要旨と原文を確認し、条件を合わせて利用してください。")
    return normalized[:3]


def _build_rule_based_paper_abstracts(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for paper in papers:
        doi = normalize_doi(str(paper.get("doi", "")))
        if not doi:
            continue
        abstract = clean_abstract_text(str(paper.get("abstract", "")))
        if abstract:
            snippet = abstract[:160].rstrip()
            if len(abstract) > 160:
                snippet += "…"
            abstract_ja = clean_abstract_text(f"原文要旨の要点（機械抽出）: {snippet}")
        else:
            abstract_ja = _fallback_paper_abstract_ja(paper)
        results.append({"doi": doi, "abstract_ja": abstract_ja, "is_fallback": True})
    return results


def _build_rule_based_output(doc_data: dict[str, Any], papers: list[dict[str, Any]], fill_abstract_ja: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "usage_summary": _build_rule_based_usage_summary(doc_data, papers),
        "usage_bullets": _build_rule_based_usage_bullets(doc_data, papers),
        "paper_abstracts": [],
    }
    if fill_abstract_ja:
        payload["paper_abstracts"] = _build_rule_based_paper_abstracts(papers)
    return payload


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.generation_mode == "openai" and not args.openai_api_key:
        print("Missing --openai-api-key or OPENAI_API_KEY for --generation-mode=openai.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.page_size <= 0:
        print("page-size must be 1 or greater.", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("timeout must be greater than 0.", file=sys.stderr)
        return 2
    if args.max_retries <= 0:
        print("max-retries must be 1 or greater.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    session = requests.Session() if args.generation_mode == "openai" else None

    last_doc = None
    resume_snapshot = None
    if args.resume_from_doc_id:
        try:
            candidate = collection.document(args.resume_from_doc_id).get()
            if candidate.exists:
                resume_snapshot = candidate
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to resolve --resume-from-doc-id: {exc}", file=sys.stderr)

    pending = 0
    batch = client.batch()

    scanned_docs = 0
    target_docs = 0
    updated_docs = 0
    failed_docs = 0
    skipped_manual_docs = 0

    done_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []

    editor_label = args.model if args.generation_mode == "openai" else RULE_BASED_EDITOR

    while True:
        page_query = collection.order_by("__name__").limit(args.page_size)
        if last_doc is not None:
            page_query = page_query.start_after(last_doc)
        elif resume_snapshot is not None:
            page_query = page_query.start_after(resume_snapshot)
        docs = fetch_page(page_query)
        if not docs:
            break

        for doc in docs:
            scanned_docs += 1
            if args.resume_from_doc_id and resume_snapshot is None and doc.id <= args.resume_from_doc_id:
                continue

            data = doc.to_dict() or {}
            if args.skip_manual and str(data.get("usage_manual_editor", "") or "").strip().lower() == "manual":
                skipped_manual_docs += 1
                continue
            papers_status = str(data.get("papers_status", "") or "")
            papers_raw = data.get("papers")
            if papers_status != "ready" or not isinstance(papers_raw, list) or len(papers_raw) == 0:
                continue

            papers_for_prompt = build_input_papers(papers_raw)
            if not papers_for_prompt:
                continue

            target_docs += 1
            now_iso = datetime.now(timezone.utc).isoformat()

            try:
                if args.generation_mode == "openai":
                    request_payload = _build_response_request(data, papers_for_prompt, args.model)
                    llm_output = _call_openai_usage(
                        session=session if session is not None else requests.Session(),
                        api_base=args.api_base,
                        api_key=args.openai_api_key,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                        payload=request_payload,
                    )
                else:
                    llm_output = _build_rule_based_output(
                        doc_data=data,
                        papers=papers_for_prompt,
                        fill_abstract_ja=args.fill_abstract_ja,
                    )
            except Exception as exc:
                failed_docs += 1
                error_rows.append(
                    {
                        "doc_id": doc.id,
                        "name": clean_abstract_text(str(data.get("name", ""))),
                        "error": str(exc),
                    }
                )
                if args.log_every and target_docs % args.log_every == 0:
                    print(
                        f"Processed target docs={target_docs} updated={updated_docs} failed={failed_docs}",
                        flush=args.flush_logs,
                    )
                if args.limit_docs and target_docs >= args.limit_docs:
                    break
                continue

            usage_summary = clean_abstract_text(str(llm_output.get("usage_summary", "")))
            if not usage_summary:
                usage_summary = _fallback_usage_summary(data, papers_for_prompt)

            output_bullets = llm_output.get("usage_bullets")
            bullets: list[str] = []
            if isinstance(output_bullets, list):
                bullets = [clean_abstract_text(str(item)) for item in output_bullets if clean_abstract_text(str(item))]
            if len(bullets) < 3:
                bullets = _fallback_usage_bullets(papers_for_prompt)
            else:
                bullets = bullets[:3]

            source_titles = [paper.get("title", "") for paper in papers_for_prompt if paper.get("title")]
            source_dois = [paper.get("doi", "") for paper in papers_for_prompt if paper.get("doi")]

            abstract_ja_updated = 0
            updates: dict[str, Any] = {
                "usage_manual_summary": usage_summary,
                "usage_manual_bullets": bullets,
                "usage_manual_sources": source_titles,
                "usage_manual_dois": source_dois,
                "usage_manual_editor": editor_label,
                "usage_manual_updated_at": now_iso,
            }

            if args.fill_abstract_ja:
                paper_abstracts_map: dict[str, dict[str, Any]] = {}
                output_paper_abstracts = llm_output.get("paper_abstracts")
                if isinstance(output_paper_abstracts, list):
                    for entry in output_paper_abstracts:
                        if not isinstance(entry, dict):
                            continue
                        doi = normalize_doi(str(entry.get("doi", "")))
                        if not doi:
                            continue
                        paper_abstracts_map[doi] = {
                            "abstract_ja": clean_abstract_text(str(entry.get("abstract_ja", ""))),
                            "is_fallback": bool(entry.get("is_fallback", False)),
                        }

                updated_papers: list[Any] = []
                for paper in papers_raw:
                    if not isinstance(paper, dict):
                        updated_papers.append(paper)
                        continue

                    updated = dict(paper)
                    doi = normalize_doi(str(updated.get("doi", "")))
                    if not doi:
                        updated_papers.append(updated)
                        continue

                    mapped = paper_abstracts_map.get(doi)
                    mapped_ja = clean_abstract_text(str((mapped or {}).get("abstract_ja", "")))
                    mapped_fallback = bool((mapped or {}).get("is_fallback", False))
                    if not mapped_ja:
                        mapped_ja = _fallback_paper_abstract_ja(updated)
                        mapped_fallback = True

                    updated["abstract_ja"] = mapped_ja
                    updated["abstract_ja_model"] = editor_label
                    updated["abstract_ja_generated_at"] = now_iso
                    updated["abstract_ja_auto_fallback"] = mapped_fallback
                    abstract_ja_updated += 1
                    updated_papers.append(updated)

                updates["papers"] = updated_papers

            updated_docs += 1
            done_rows.append(
                {
                    "doc_id": doc.id,
                    "name": clean_abstract_text(str(data.get("name", ""))),
                    "papers_used": len(papers_for_prompt),
                    "abstract_ja_updated": abstract_ja_updated,
                    "usage_summary_len": len(usage_summary),
                    "status": "ok",
                    "error": "",
                }
            )

            if not args.dry_run:
                batch.update(doc.reference, updates)
                pending += 1
                if pending >= args.batch_size:
                    commit_batch(batch, pending, args.sleep)
                    batch = client.batch()
                    pending = 0

            if args.sleep > 0:
                time.sleep(args.sleep)

            if args.log_every and target_docs % args.log_every == 0:
                print(
                    f"Processed target docs={target_docs} updated={updated_docs} failed={failed_docs}",
                    flush=args.flush_logs,
                )
            if args.limit_docs and target_docs >= args.limit_docs:
                break

        last_doc = docs[-1]
        if args.limit_docs and target_docs >= args.limit_docs:
            break

    if not args.dry_run and pending:
        commit_batch(batch, pending, args.sleep)

    done_path = write_csv(
        args.done_csv,
        done_rows,
        ["doc_id", "name", "papers_used", "abstract_ja_updated", "usage_summary_len", "status", "error"],
    )
    error_path = write_csv(args.error_csv, error_rows, ["doc_id", "name", "error"])

    print(
        (
            f"Done usage_from_abstract. scanned_docs={scanned_docs} target_docs={target_docs} "
            f"updated_docs={updated_docs} failed_docs={failed_docs} skipped_manual_docs={skipped_manual_docs} "
            f"mode={args.generation_mode} "
            f"done_csv={done_path} error_csv={error_path}"
        ),
        flush=args.flush_logs,
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
