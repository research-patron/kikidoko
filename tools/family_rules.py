#!/usr/bin/env python3
"""Deterministic equipment family rules for manual curation queues."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple


PRINCIPLE_PATTERNS: Sequence[Tuple[str, re.Pattern[str]]] = (
    ("nmr", re.compile(r"\bNMR\b|核磁気", re.IGNORECASE)),
    ("sem_tem", re.compile(r"\bSEM\b|\bTEM\b|電子顕微|顕微鏡", re.IGNORECASE)),
    ("xray", re.compile(r"\bXRD\b|\bXRF\b|X線|回折", re.IGNORECASE)),
    ("chromatography", re.compile(r"\bHPLC\b|\bGC\b|クロマト", re.IGNORECASE)),
    ("mass", re.compile(r"\bLCMS\b|\bGCMS\b|\bMS\b|質量分析", re.IGNORECASE)),
    ("flow", re.compile(r"\bFACS\b|フローサイトメトリー|セルソーター", re.IGNORECASE)),
    ("sequencer", re.compile(r"シーケンサー|sequencer|次世代シーケンス", re.IGNORECASE)),
    ("spectroscopy", re.compile(r"分光|吸光|蛍光|FTIR|Raman", re.IGNORECASE)),
    ("thermal", re.compile(r"\bDSC\b|\bTGA\b|熱分析", re.IGNORECASE)),
)

SAMPLE_PATTERNS: Sequence[Tuple[str, re.Pattern[str]]] = (
    ("bio_liquid", re.compile(r"生体|細胞|DNA|RNA|血液|培養|タンパク", re.IGNORECASE)),
    ("solid_powder", re.compile(r"固体|粉末|薄膜|結晶|金属|材料", re.IGNORECASE)),
    ("liquid", re.compile(r"液体|溶液|溶媒", re.IGNORECASE)),
    ("gas", re.compile(r"気体|ガス|気相", re.IGNORECASE)),
)

PURPOSE_PATTERNS: Sequence[Tuple[str, re.Pattern[str]]] = (
    ("analysis", re.compile(r"分析|解析|評価|characteriz", re.IGNORECASE)),
    ("observation", re.compile(r"観察|イメージ|撮像|顕微", re.IGNORECASE)),
    ("processing", re.compile(r"加工|前処理|蒸着|スパッタ", re.IGNORECASE)),
    ("separation", re.compile(r"分離|精製|分画", re.IGNORECASE)),
    ("synthesis", re.compile(r"合成|反応", re.IGNORECASE)),
)

NAME_STOPWORDS = {
    "装置",
    "機器",
    "機",
    "システム",
    "system",
    "instrument",
    "analyzer",
    "analysis",
    "device",
    "model",
    "型",
    "用",
}

MODEL_TOKEN_PATTERN = re.compile(
    r"[a-z]{1,4}\d{2,}[a-z0-9\-]*|\d+(?:mhz|ghz|khz|ev|kv|nm|um|mm)\b",
    re.IGNORECASE,
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\-]+|[一-龠々ぁ-んァ-ヶー]+")


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _classify(patterns: Sequence[Tuple[str, re.Pattern[str]]], text: str, default: str) -> str:
    for label, pattern in patterns:
        if pattern.search(text):
            return label
    return default


def normalize_name(name: Any) -> str:
    raw = unicodedata.normalize("NFKC", normalize_text(name)).lower()
    if not raw:
        return "unknown"
    cleaned = re.sub(r"[\"'“”‘’「」『』【】()（）［］\[\]{}<>《》、。,:;!?！？/\\|+_]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "unknown"

    tokens: List[str] = []
    model_tokens = MODEL_TOKEN_PATTERN.findall(cleaned)
    if model_tokens:
        tokens.extend([token.lower() for token in model_tokens[:3]])

    for token in TOKEN_PATTERN.findall(cleaned):
        t = token.strip().lower()
        if not t:
            continue
        if t in NAME_STOPWORDS:
            continue
        if t.isdigit():
            continue
        if len(t) == 1 and re.fullmatch(r"[a-z]", t):
            continue
        if t not in tokens:
            tokens.append(t)
        if len(tokens) >= 6:
            break

    return "-".join(tokens[:6]) if tokens else "unknown"


def build_family_id(item: Dict[str, Any]) -> str:
    category_general = normalize_text(item.get("category_general")) or "未分類"
    category_detail = normalize_text(item.get("category_detail")) or "未分類"
    name = normalize_text(item.get("name"))
    source = " ".join(
        [
            name,
            category_general,
            category_detail,
            normalize_text(item.get("summary")),
        ]
    )
    principle_class = _classify(PRINCIPLE_PATTERNS, source, "other")
    sample_class = _classify(SAMPLE_PATTERNS, source, "other")
    purpose_class = _classify(PURPOSE_PATTERNS, source, "other")
    normalized_name = normalize_name(name)
    return "|".join(
        [
            category_general,
            category_detail,
            normalized_name,
            principle_class,
            sample_class,
            purpose_class,
        ]
    )


def item_primary_id(item: Dict[str, Any], index: int) -> str:
    doc_id = normalize_text(item.get("doc_id"))
    if doc_id:
        return doc_id
    equipment_id = normalize_text(item.get("equipment_id"))
    if equipment_id:
        return equipment_id
    return f"row-{index:06d}"


def build_family_map(items: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        result[item_primary_id(item, idx)] = build_family_id(item)
    return result


def select_deterministic_by_family(
    rows: Sequence[Tuple[int, Dict[str, Any]]],
    limit: int,
) -> Tuple[List[Tuple[int, Dict[str, Any]]], Dict[str, List[Tuple[int, Dict[str, Any]]]]]:
    grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for idx, item in rows:
        grouped[build_family_id(item)].append((idx, item))

    family_ids = sorted(grouped.keys())
    if limit <= 0:
        return [], {family_id: grouped[family_id] for family_id in family_ids}

    selected: List[Tuple[int, Dict[str, Any]]] = []
    pointer: Dict[str, int] = {}

    # Pass 1: choose one representative per family.
    for family_id in family_ids:
        members = grouped[family_id]
        if not members:
            continue
        selected.append(members[0])
        pointer[family_id] = 1
        if len(selected) >= limit:
            return selected, {k: grouped[k] for k in family_ids}

    # Pass 2: fill remaining slots in family-id order.
    while len(selected) < limit:
        picked = 0
        for family_id in family_ids:
            members = grouped[family_id]
            cursor = int(pointer.get(family_id, 0))
            if cursor >= len(members):
                continue
            selected.append(members[cursor])
            pointer[family_id] = cursor + 1
            picked += 1
            if len(selected) >= limit:
                break
        if picked == 0:
            break

    return selected, {k: grouped[k] for k in family_ids}
