from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.yamaguchi-u.ac.jp/facility/facilist/"
ORG_NAME = "山口大学 リサーチファシリティマネジメントセンター"
PREFECTURE = "山口県"
CATEGORY_FALLBACK = "研究設備"

CLASSIFICATION_LABELS = {
    "一般全学共用機器",
    "コアファシリティ機器",
    "準コアファシリティ機器",
    "その他主要機器",
}
MODE_LABELS = {"自己測定", "依頼測定"}


def fetch_yamaguchi_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen: set[str] = set()

    for item in soup.select(".faci_item"):
        record = _parse_item(item)
        if not record:
            continue
        dedupe_key = record.equipment_id or f"{record.name}:{record.source_url}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _parse_item(item: BeautifulSoup) -> RawEquipment | None:
    anchor = item.find("a", href=True)
    name = clean_text(anchor.get_text(" ", strip=True)) if anchor else ""
    if not name:
        lines = _extract_lines(item)
        if lines:
            name = lines[0]
    if not name:
        return None

    source_url = LIST_URL
    if anchor and anchor.get("href"):
        source_url = urljoin(LIST_URL, anchor["href"])

    lines = _extract_lines(item)
    lines = [line for line in lines if line and line != name]

    used: set[int] = set()
    category, used = _extract_label_value(lines, "カテゴリ", used)
    year, used = _extract_label_value(lines, "設置年度", used)
    department, used = _extract_label_value(lines, "管理部局", used)
    model_parts = [line for idx, line in enumerate(lines) if idx not in used]
    model_text = " ".join(model_parts).strip()

    alts = _extract_alts(item)
    classification = [alt for alt in alts if alt in CLASSIFICATION_LABELS]
    location = next((alt for alt in alts if "地区" in alt), "")
    usage_modes = [alt for alt in alts if alt in MODE_LABELS]

    external_use = ""
    if "学外" in alts:
        external_use = "可"
    elif "学内" in alts:
        external_use = "不可"

    category_general = category or (classification[0] if classification else CATEGORY_FALLBACK)
    category_detail = " / ".join(classification) if classification else ""

    conditions_note = _build_conditions_note(model_text, year, department, usage_modes)
    address_raw = f"山口大学 {location}" if location else "山口大学"
    equipment_id = _build_equipment_id(item, source_url, name)

    return RawEquipment(
        equipment_id=equipment_id,
        name=name,
        category_general=category_general,
        category_detail=category_detail,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=address_raw,
        external_use=external_use,
        conditions_note=conditions_note,
        source_url=source_url,
    )


def _extract_lines(item: BeautifulSoup) -> list[str]:
    lines = [clean_text(line) for line in item.get_text("\n", strip=True).split("\n")]
    return [line for line in lines if line]


def _extract_label_value(
    lines: list[str], label: str, used: set[int]
) -> tuple[str, set[int]]:
    for idx, line in enumerate(lines):
        if idx in used:
            continue
        if line.startswith(label):
            used.add(idx)
            value = ""
            if "：" in line:
                value = clean_text(line.split("：", 1)[1])
            if value:
                return value, used
            if idx + 1 < len(lines):
                used.add(idx + 1)
                return clean_text(lines[idx + 1]), used
    return "", used


def _extract_alts(item: BeautifulSoup) -> list[str]:
    alts: list[str] = []
    for img in item.find_all("img"):
        alt = clean_text(img.get("alt", ""))
        if alt:
            alts.append(alt)
    return alts


def _build_conditions_note(
    model_text: str, year: str, department: str, usage_modes: list[str]
) -> str:
    parts: list[str] = []
    if model_text:
        parts.append(f"機種: {model_text}")
    if year:
        parts.append(f"設置年度: {year}")
    if department:
        parts.append(f"管理部局: {department}")
    if usage_modes:
        parts.append(f"利用形態: {', '.join(usage_modes)}")
    return " / ".join(parts)


def _build_equipment_id(item: BeautifulSoup, source_url: str, name: str) -> str:
    slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
    if slug and slug != "facilist":
        return f"YAMAGUCHI-{slug}"
    for class_name in item.get("class", []):
        if class_name.startswith("kiki"):
            return f"YAMAGUCHI-{class_name.upper()}"
    if name:
        safe = "".join(char if char.isalnum() else "-" for char in name).strip("-")
        if safe:
            return f"YAMAGUCHI-{safe}"
    return ""
