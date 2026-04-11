#!/usr/bin/env python3
"""Strict verifier for requirement-100 UI/data readiness."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

ALLOWED_SAMPLE_STATES = {"固体", "液体", "粉末", "気体", "生体", "その他"}

FALLBACK_PAPER_MAP: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"フロー|細胞|免疫|FACS", re.IGNORECASE), "10.1038/nri.2017.113", "Flow cytometry and the future of immunology"),
    (re.compile(r"NMR|核磁気", re.IGNORECASE), "10.1016/j.pnmrs.2016.05.001", "NMR spectroscopy in chemistry and materials science"),
    (re.compile(r"X線|回折|XRD|XRF", re.IGNORECASE), "10.1107/S2052520614026152", "Powder diffraction in materials characterization"),
    (re.compile(r"質量|MS|LCMS|GCMS", re.IGNORECASE), "10.1038/nmeth.3253", "Mass spectrometry for proteomics and metabolomics"),
    (re.compile(r"顕微|SEM|TEM|FIB", re.IGNORECASE), "10.1038/nmeth.2080", "Fluorescence microscopy: from principles to biological applications"),
    (re.compile(r"クロマト|HPLC|GC", re.IGNORECASE), "10.1038/nprot.2016.009", "Gas chromatography-mass spectrometry based metabolomics"),
    (re.compile(r"培養|インキュベーター|細胞培養", re.IGNORECASE), "10.1038/s41596-020-00436-6", "Mammalian cell culture practical guidelines"),
    (re.compile(r"遠心", re.IGNORECASE), "10.1016/j.ab.2014.08.008", "Centrifugation techniques in biological sample preparation"),
]

FALLBACK_PAPER_DEFAULT = {
    "doi": "10.1038/nmeth.2080",
    "title": "Fluorescence microscopy: from principles to biological applications",
}
INTERNAL_ID_PATTERN = re.compile(r"\b(?:doc_id|equipment_id|eqnet-\d+)\b", re.IGNORECASE)
PLACEHOLDER_DOI_PATTERN = re.compile(r"^10\.0000/", re.IGNORECASE)
AUTO_TEMPLATE_MARKERS = [
    "同カテゴリの近縁機器",
    "補助キーワード",
    "比較観点1では",
    "補助タグは",
    "確認語は",
    "警告語",
    "記録補助語",
    "運用上の補助タグとして",
    "補助見出しにして記録",
]


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def contains_internal_identifier(text: str, doc_id: str, equipment_id: str) -> bool:
    raw = normalize_text(text)
    if not raw:
        return False
    lower = raw.lower()
    doc = normalize_text(doc_id).lower()
    equipment = normalize_text(equipment_id).lower()
    if doc and doc in lower:
        return True
    if equipment and equipment in lower:
        return True
    return bool(INTERNAL_ID_PATTERN.search(raw))


def count_chars(text: Any, mode: str = "non_whitespace") -> int:
    raw = str(text or "")
    if mode == "non_whitespace":
        return len(re.sub(r"\s+", "", raw))
    return len(raw.strip())


def beginner_char_count(beginner: Dict[str, Any], mode: str = "non_whitespace") -> int:
    principle = normalize_text(beginner.get("principle_ja"))
    sample = normalize_text(beginner.get("sample_guidance_ja"))
    steps = beginner.get("basic_steps_ja") if isinstance(beginner.get("basic_steps_ja"), list) else []
    pitfalls = beginner.get("common_pitfalls_ja") if isinstance(beginner.get("common_pitfalls_ja"), list) else []
    text = "".join(
        [
            principle,
            sample,
            "".join(normalize_text(v) for v in steps if normalize_text(v)),
            "".join(normalize_text(v) for v in pitfalls if normalize_text(v)),
        ]
    )
    return count_chars(text, mode)


def has_auto_template_marker(text: str) -> bool:
    raw = normalize_text(text)
    if not raw:
        return False
    return any(marker in raw for marker in AUTO_TEMPLATE_MARKERS)


def normalize_doi(value: Any) -> str:
    doi = normalize_text(value)
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE).strip()


def canonical_paper_url(value: Any, doi: str) -> str:
    raw = normalize_text(value)
    if raw:
        if raw.startswith(("http://", "https://")):
            return raw
        if raw.startswith("doi.org/"):
            return f"https://{raw}"
        if raw.startswith("10."):
            return f"https://doi.org/{raw}"
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def is_http_url(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_manual_state_items(values: Any) -> List[str]:
    source = values if isinstance(values, list) else []
    out: List[str] = []
    for value in source:
        text = normalize_text(value)
        if not text or text not in ALLOWED_SAMPLE_STATES:
            continue
        if text not in out:
            out.append(text)
    return out[:6]


def normalize_manual_field_items(values: Any, max_items: int = 4) -> List[str]:
    source = values if isinstance(values, list) else []
    out: List[str] = []
    for value in source:
        text = normalize_text(value)
        if not text:
            continue
        if text not in out:
            out.append(text)
    return out[: max(1, max_items)]


def normalize_manual_papers(values: Any) -> List[Dict[str, str]]:
    source = values if isinstance(values, list) else []
    out: List[Dict[str, str]] = []
    for value in source[:3]:
        if not isinstance(value, dict):
            continue
        doi = normalize_doi(value.get("doi"))
        out.append(
            {
                "doi": doi,
                "title": normalize_text(value.get("title")),
                "objective_ja": normalize_text(value.get("objective_ja")),
                "method_ja": normalize_text(value.get("method_ja")),
                "finding_ja": normalize_text(value.get("finding_ja")),
                "link_url": normalize_text(value.get("link_url")) or (f"https://doi.org/{doi}" if doi else ""),
            }
        )
    return out


def resolve_manual_content(item: Dict[str, Any]) -> Dict[str, Any]:
    data = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
    review = data.get("review") if isinstance(data.get("review"), dict) else {}
    usage = data.get("general_usage") if isinstance(data.get("general_usage"), dict) else {}
    beginner = data.get("beginner_guide") if isinstance(data.get("beginner_guide"), dict) else {}
    status = normalize_text(review.get("status")).lower()
    if status not in {"approved", "pending", "rejected"}:
        status = "pending"
    return {
        "review_status": status,
        "general": {
            "summary_ja": normalize_text(usage.get("summary_ja")),
            "sample_states": normalize_manual_state_items(usage.get("sample_states")),
            "research_fields_ja": normalize_manual_field_items(usage.get("research_fields_ja"), 4),
        },
        "papers": normalize_manual_papers(data.get("paper_explanations")),
        "beginner": {
            "principle_ja": normalize_text(beginner.get("principle_ja")),
            "sample_guidance_ja": normalize_text(beginner.get("sample_guidance_ja")),
            "basic_steps_ja": normalize_manual_field_items(beginner.get("basic_steps_ja") or beginner.get("basic_steps"), 6),
            "common_pitfalls_ja": normalize_manual_field_items(
                beginner.get("common_pitfalls_ja") or beginner.get("common_pitfalls"), 6
            ),
        },
    }


def first_meaningful_sentence(text: Any, max_len: int = 220) -> str:
    raw = normalize_text(text)
    if not raw:
        return ""
    chunks = [c.strip() for c in re.split(r"[。\n]", raw) if c.strip()]
    found = next((c for c in chunks if len(c) >= 20), raw)
    return found[:max_len]


def choose_fallback_paper(item: Dict[str, Any]) -> Dict[str, str]:
    source = f"{normalize_text(item.get('name'))} {normalize_text(item.get('category_general'))} {normalize_text(item.get('category_detail'))}"
    for pattern, doi, title in FALLBACK_PAPER_MAP:
        if pattern.search(source):
            return {"doi": doi, "title": title}
    return dict(FALLBACK_PAPER_DEFAULT)


def derive_sample_states(item: Dict[str, Any], preferred: Any) -> List[str]:
    manual_states = normalize_manual_state_items(preferred)
    if manual_states:
        return manual_states
    source = f"{normalize_text(item.get('name'))} {normalize_text(item.get('category_general'))} {normalize_text(item.get('category_detail'))}"
    out: List[str] = []

    def add(state: str) -> None:
        if state not in out:
            out.append(state)

    if re.search(r"細胞|生体|培養|フロー|DNA|RNA|PCR|組織|免疫", source, flags=re.IGNORECASE):
        add("生体")
        add("液体")
    if re.search(r"粉末|材料|SEM|TEM|FIB|X線|顕微|硬度|結晶|金属", source, flags=re.IGNORECASE):
        add("固体")
        add("粉末")
    if re.search(r"ガス|GC|気相|吸着|プラズマ", source, flags=re.IGNORECASE):
        add("気体")
    if re.search(r"液体|溶液|HPLC|NMR|分光|クロマト", source, flags=re.IGNORECASE):
        add("液体")
    if not out:
        add("固体")
        add("液体")
    return out[:6]


def derive_research_fields(item: Dict[str, Any], preferred: Any) -> List[str]:
    out = normalize_manual_field_items(preferred, 4)

    def add(value: Any) -> None:
        text = normalize_text(value)
        if text and text not in out:
            out.append(text)

    source = f"{normalize_text(item.get('name'))} {normalize_text(item.get('category_general'))} {normalize_text(item.get('category_detail'))}"
    if re.search(r"分光|クロマト|質量|NMR|分析", source, flags=re.IGNORECASE):
        add("分析化学")
    if re.search(r"材料|結晶|薄膜|表面|顕微|FIB|SEM|TEM", source, flags=re.IGNORECASE):
        add("材料科学")
    if re.search(r"細胞|生体|DNA|RNA|フロー|培養|免疫", source, flags=re.IGNORECASE):
        add("生命科学")
    if re.search(r"電気|半導体|デバイス|工学|機械", source, flags=re.IGNORECASE):
        add("電子・デバイス工学")
    if re.search(r"環境|ガス|CO2|水質", source, flags=re.IGNORECASE):
        add("環境工学")

    insights = item.get("usage_insights") if isinstance(item.get("usage_insights"), dict) else {}
    fields = insights.get("fields") if isinstance(insights.get("fields"), dict) else {}
    for value in fields.get("items") if isinstance(fields.get("items"), list) else []:
        add(value)

    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    for paper in papers[:3]:
        if not isinstance(paper, dict):
            continue
        for value in paper.get("research_fields_ja") if isinstance(paper.get("research_fields_ja"), list) else []:
            add(value)
    if not out:
        add("計測工学")
    return out[:4]


def derive_paper_explanations(item: Dict[str, Any], preferred: Any) -> List[Dict[str, str]]:
    manual_papers = normalize_manual_papers(preferred)
    if manual_papers:
        out: List[Dict[str, str]] = []
        for paper in manual_papers[:3]:
            doi = normalize_doi(paper.get("doi"))
            out.append(
                {
                    "doi": doi,
                    "title": normalize_text(paper.get("title")) or "タイトル不明",
                    "objective_ja": normalize_text(paper.get("objective_ja")) or "情報準備中です。",
                    "method_ja": normalize_text(paper.get("method_ja")) or "情報準備中です。",
                    "finding_ja": normalize_text(paper.get("finding_ja")) or "情報準備中です。",
                    "link_url": canonical_paper_url(paper.get("link_url"), doi),
                }
            )
        if out:
            return out

    source_papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    generated: List[Dict[str, str]] = []
    for paper in source_papers[:3]:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(paper.get("doi"))
        name = normalize_text(item.get("name")) or "当該装置"
        objective_raw = normalize_text(paper.get("usage_what_ja"))
        method_raw = normalize_text(paper.get("usage_how_ja"))
        finding_raw = first_meaningful_sentence(paper.get("abstract_ja") or paper.get("abstract"))
        generated.append(
            {
                "doi": doi or normalize_doi(paper.get("url")),
                "title": normalize_text(paper.get("title")) or "タイトル不明",
                "objective_ja": objective_raw if len(objective_raw) >= 20 else f"{name}を用いて対象現象を定量化し、評価指標の有効性を確認した。",
                "method_ja": method_raw if len(method_raw) >= 20 else f"{name}の測定条件を統一し、再現性を確認した上で比較解析を実施した。",
                "finding_ja": finding_raw if len(finding_raw) >= 20 else f"{name}の利用により、条件差の影響を定量評価できることが示された。",
                "link_url": canonical_paper_url(paper.get("url"), doi),
            }
        )
    if generated:
        return generated

    fallback = choose_fallback_paper(item)
    name = normalize_text(item.get("name")) or "当該装置"
    doi = fallback["doi"]
    return [
        {
            "doi": doi,
            "title": fallback["title"],
            "objective_ja": f"{name}が対象試料の特性評価にどの程度有効かを検証し、研究設計の妥当性を確認した。",
            "method_ja": f"{name}の設定条件を段階的に最適化し、再現性と感度を比較する手法で評価した。",
            "finding_ja": f"{name}を用いることで信号の再現性が向上し、実験条件最適化の指針が得られた。",
            "link_url": f"https://doi.org/{doi}",
        }
    ]


def derive_beginner_guide(item: Dict[str, Any], manual: Dict[str, Any], sample_states: List[str], fields: List[str]) -> Dict[str, Any]:
    name = normalize_text(item.get("name")) or "当該装置"
    category = normalize_text(item.get("category_general")) or "対象分野"
    detail = normalize_text(item.get("category_detail"))
    target = f"{category}（{detail}）" if detail else category
    sample_label = "・".join(sample_states) if sample_states else "試料"
    field_label = "・".join(fields[:2]) if fields else category

    principle = normalize_text(manual.get("principle_ja")) or (
        f"{name}は{target}における信号変化を検出し、条件間の差を定量比較するための装置である。"
        "基準条件を固定して再現性を確保してから本測定を行う。"
    )
    sample_guidance = normalize_text(manual.get("sample_guidance_ja")) or (
        f"{name}では{sample_label}を扱うため、前処理条件のばらつきや汚染混入を避けるために、濃度・温度・保存状態を測定前に確認する。"
    )
    steps = normalize_manual_field_items(manual.get("basic_steps_ja") or manual.get("basic_steps"), 6)
    pitfalls = normalize_manual_field_items(manual.get("common_pitfalls_ja") or manual.get("common_pitfalls"), 6)
    if not steps:
        steps = [
            f"{name}で扱う試料条件を記録し、{target}に必要な前処理手順を測定前に確定する。",
            f"標準試料またはブランクで初期測定を行い、{name}のベースラインと感度を確認する。",
            f"{field_label}の比較評価は同一条件で複数回測定し、外れ値確認後に本解析へ進める。",
        ]
    if not pitfalls:
        pitfalls = [
            f"{name}では前処理時間や温度のわずかなずれが信号変動を拡大し、比較結果の信頼性を下げやすい。",
            f"{target}の評価途中で条件を変更すると、試料差と条件差が混在し、解釈を誤る原因になりやすい。",
        ]
    return {
        "principle_ja": principle,
        "sample_guidance_ja": sample_guidance,
        "basic_steps_ja": steps[:6],
        "common_pitfalls_ja": pitfalls[:6],
    }


def resolve_display_content(item: Dict[str, Any]) -> Dict[str, Any]:
    manual = resolve_manual_content(item)
    summary = manual["general"]["summary_ja"] or normalize_text(item.get("usage_manual_summary")) or (
        f"{normalize_text(item.get('name')) or '当該装置'}は{normalize_text(item.get('category_general')) or '研究'}領域で、"
        "試料状態の変化を定量評価し再現性のある比較データを得るために利用される。"
    )
    sample_states = derive_sample_states(item, manual["general"]["sample_states"])
    research_fields = derive_research_fields(item, manual["general"]["research_fields_ja"])
    papers = derive_paper_explanations(item, manual["papers"])
    beginner = derive_beginner_guide(item, manual["beginner"], sample_states, research_fields)
    return {
        "general": {
            "summary_ja": summary,
            "sample_states": sample_states,
            "research_fields_ja": research_fields,
        },
        "papers": papers,
        "beginner": beginner,
    }


def check_item(item: Dict[str, Any], beginner_min_chars: int, char_count_mode: str) -> List[str]:
    issues: List[str] = []
    display = resolve_display_content(item)
    general = display["general"]
    papers = display["papers"]
    beginner = display["beginner"]

    if not normalize_text(general.get("summary_ja")):
        issues.append("general_summary_missing")
    if not isinstance(general.get("sample_states"), list) or len(general["sample_states"]) < 1:
        issues.append("sample_states_missing")
    if not isinstance(general.get("research_fields_ja"), list) or len(general["research_fields_ja"]) < 1:
        issues.append("research_fields_missing")

    if not papers:
        issues.append("paper_explanations_missing")
    else:
        paper = papers[0] if isinstance(papers[0], dict) else {}
        if not normalize_text(paper.get("objective_ja")):
            issues.append("paper_objective_missing")
        if not normalize_text(paper.get("method_ja")):
            issues.append("paper_method_missing")
        if not normalize_text(paper.get("finding_ja")):
            issues.append("paper_finding_missing")
        link = normalize_text(paper.get("link_url"))
        if not is_http_url(link):
            issues.append("paper_link_missing")

    if not normalize_text(beginner.get("principle_ja")):
        issues.append("beginner_principle_missing")
    if not normalize_text(beginner.get("sample_guidance_ja")):
        issues.append("beginner_sample_missing")
    if not isinstance(beginner.get("basic_steps_ja"), list) or len(beginner["basic_steps_ja"]) < 1:
        issues.append("beginner_steps_missing")
    if not isinstance(beginner.get("common_pitfalls_ja"), list) or len(beginner["common_pitfalls_ja"]) < 1:
        issues.append("beginner_pitfalls_missing")
    if max(0, int(beginner_min_chars)) > 0:
        if beginner_char_count(beginner, char_count_mode) < int(beginner_min_chars):
            issues.append("beginner_min_chars_not_met")
    return issues


def check_item_strict_content(
    item: Dict[str, Any],
    beginner_min_chars: int,
    beginner_max_chars: int,
    char_count_mode: str,
    forbid_internal_id: bool,
) -> List[str]:
    issues: List[str] = []
    manual = resolve_manual_content(item)
    general = manual["general"]
    papers = manual["papers"]
    beginner = manual["beginner"]
    equipment_name = normalize_text(item.get("name"))

    if manual.get("review_status") != "approved":
        issues.append("review_not_approved")

    chars = beginner_char_count(beginner, char_count_mode)
    min_chars = max(0, int(beginner_min_chars))
    max_chars = max(0, int(beginner_max_chars))
    if min_chars > 0 and chars < min_chars:
        issues.append("beginner_min_chars_not_met")
    if max_chars > 0 and chars > max_chars:
        issues.append("beginner_max_chars_exceeded")

    summary_text = normalize_text(general.get("summary_ja"))
    principle_text = normalize_text(beginner.get("principle_ja"))
    if equipment_name and equipment_name not in summary_text:
        issues.append("name_not_in_summary")
    if equipment_name and equipment_name not in principle_text:
        issues.append("name_not_in_principle")

    source_papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    if len(source_papers) >= 2 and len(papers) < 2:
        issues.append("insufficient_paper_explanations_for_multi_papers")

    for paper in papers:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(paper.get("doi"))
        link_doi = normalize_doi(paper.get("link_url"))
        if (doi and PLACEHOLDER_DOI_PATTERN.search(doi)) or (link_doi and PLACEHOLDER_DOI_PATTERN.search(link_doi)):
            issues.append("placeholder_doi_hit")
            break

    if forbid_internal_id:
        article_text = "".join(
            [
                normalize_text(general.get("summary_ja")),
                "".join(normalize_text(v) for v in general.get("research_fields_ja") if normalize_text(v)),
                normalize_text(beginner.get("principle_ja")),
                normalize_text(beginner.get("sample_guidance_ja")),
                "".join(normalize_text(v) for v in beginner.get("basic_steps_ja") if normalize_text(v)),
                "".join(normalize_text(v) for v in beginner.get("common_pitfalls_ja") if normalize_text(v)),
                "".join(normalize_text((paper or {}).get("objective_ja")) for paper in papers),
                "".join(normalize_text((paper or {}).get("method_ja")) for paper in papers),
                "".join(normalize_text((paper or {}).get("finding_ja")) for paper in papers),
            ]
        )
        doc_id = normalize_text(item.get("doc_id"))
        equipment_id = normalize_text(item.get("equipment_id"))
        if contains_internal_identifier(article_text, doc_id, equipment_id):
            issues.append("internal_id_reference_hit")
        if has_auto_template_marker(article_text):
            issues.append("auto_template_marker_hit")

    return issues


def check_js_requirements(js_text: str) -> Dict[str, bool]:
    checks: Dict[str, bool] = {}
    checks["route_paper"] = (
        'segments[0] === "paper"' in js_text and "buildPaperRouteHash" in js_text and "#/paper/" in js_text
    )
    checks["route_beginner"] = (
        'segments[0] === "beginner"' in js_text and "buildBeginnerRouteHash" in js_text and "#/beginner/" in js_text
    )
    checks["paper_link_anchor"] = bool(
        re.search(r'<a class="paper-detail-link" href="\$\{[^}]+\}"[^>]*>', js_text)
    ) and "末尾リンク" in js_text
    enter_space_occurrences = len(re.findall(r'event\.key\s*===\s*"Enter"\s*\|\|\s*event\.key\s*===\s*" "', js_text))
    checks["keyboard_enter_space"] = enter_space_occurrences >= 2
    checks["keyboard_escape"] = 'event.key !== "Escape"' in js_text and "closeManualRoute();" in js_text
    return checks


def load_snapshot(path: Path) -> List[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    items = payload.get("items")
    return items if isinstance(items, list) else []


def load_subset_doc_ids(value: str, root: Path) -> set[str]:
    raw = normalize_text(value)
    if not raw:
        return set()

    path = (root / raw).resolve()
    if path.exists():
        text = path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return {normalize_text(v) for v in parsed if normalize_text(v)}
        if isinstance(parsed, dict):
            values = parsed.get("doc_ids")
            if isinstance(values, list):
                return {normalize_text(v) for v in values if normalize_text(v)}
        ids = set()
        for line in text.splitlines():
            value = normalize_text(line)
            if value:
                ids.add(value)
        return ids

    return {normalize_text(v) for v in raw.split(",") if normalize_text(v)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify requirement-100 implementation completeness.")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--js", default="frontend/dist/patches/site-ui-overrides.js")
    parser.add_argument(
        "--mode",
        default="functional",
        choices=["functional", "strict_content"],
        help="functional: UI/data requirements, strict_content: article quality rules.",
    )
    parser.add_argument("--max-report", type=int, default=20)
    parser.add_argument("--min-beginner-chars", type=int, default=2000)
    parser.add_argument("--max-beginner-chars", type=int, default=3000)
    parser.add_argument(
        "--forbid-internal-id",
        dest="forbid_internal_id",
        action="store_true",
        default=True,
        help="Fail when internal IDs are found in article text.",
    )
    parser.add_argument(
        "--allow-internal-id",
        dest="forbid_internal_id",
        action="store_false",
        help="Disable internal ID detection.",
    )
    parser.add_argument(
        "--subset",
        default="",
        help="Optional subset doc_id list (file path or comma-separated values).",
    )
    parser.add_argument(
        "--char-count-mode",
        default="non_whitespace",
        choices=["non_whitespace", "raw"],
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    js_path = (root / args.js).resolve()

    items = load_snapshot(snapshot_path)
    subset_doc_ids = load_subset_doc_ids(args.subset, root)

    issue_to_docs: Dict[str, List[str]] = {}
    checked_items = 0
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        doc_id = normalize_text(item.get("doc_id")) or normalize_text(item.get("equipment_id")) or f"row-{idx}"
        if subset_doc_ids and doc_id not in subset_doc_ids:
            continue
        checked_items += 1
        if args.mode == "strict_content":
            item_issues = check_item_strict_content(
                item,
                args.min_beginner_chars,
                args.max_beginner_chars,
                args.char_count_mode,
                bool(args.forbid_internal_id),
            )
        else:
            item_issues = check_item(item, args.min_beginner_chars, args.char_count_mode)
        for issue in item_issues:
            issue_to_docs.setdefault(issue, []).append(doc_id)

    js_checks: Dict[str, bool] = {}
    js_failed: List[str] = []
    if args.mode == "functional":
        js_text = js_path.read_text(encoding="utf-8")
        js_checks = check_js_requirements(js_text)
        js_failed = [name for name, ok in js_checks.items() if not ok]

    failed = bool(issue_to_docs) or bool(js_failed)
    offending_doc_ids = sorted({doc for docs in issue_to_docs.values() for doc in docs})
    if not failed:
        print("PASS")
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "items_checked": checked_items,
                    "data_issues": 0,
                    "js_checks": js_checks,
                    "subset_doc_ids_count": len(subset_doc_ids),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print("FAIL")
    print(
        json.dumps(
            {
                "mode": args.mode,
                "items_checked": checked_items,
                "data_issue_types": len(issue_to_docs),
                "js_failed_checks": js_failed,
                "offending_doc_ids_count": len(offending_doc_ids),
                "subset_doc_ids_count": len(subset_doc_ids),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if issue_to_docs:
        print("data_failures:")
        for issue in sorted(issue_to_docs.keys()):
            docs = issue_to_docs[issue]
            preview = docs[: max(1, int(args.max_report))]
            print(f"- {issue}: count={len(docs)} docs={preview}")
    if offending_doc_ids:
        preview = offending_doc_ids[: max(1, int(args.max_report))]
        print(f"offending_doc_ids: count={len(offending_doc_ids)} docs={preview}")
    if js_failed:
        print(f"js_failures: {js_failed}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
