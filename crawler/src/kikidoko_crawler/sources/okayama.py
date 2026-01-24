from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://dia.kikibun.okayama-u.ac.jp/equipments"
ORG_NAME = "岡山大学 自然生命科学研究支援センター 分析計測・極低温部門 分析計測分野"
PREFECTURE = "岡山県"
CATEGORY_GENERAL = "分析計測分野"


def fetch_okayama_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    name_seen: set[str] = set()
    for card in soup.select("div.equipment"):
        name = _extract_name(card)
        if not name:
            continue
        detail_url = _extract_detail_url(card)
        description = _extract_description(card)
        year = _extract_year(card)
        model = _extract_model(card)
        labels = _extract_labels(card)

        detail_info = _fetch_detail(detail_url, timeout) if detail_url else {}
        category_detail = _pick_category_detail(detail_info)
        address_raw = _build_address(detail_info)
        fee_note = detail_info.get("費用負担", "")
        conditions_note = _build_conditions_note(
            description=description,
            model=model,
            year=year,
            labels=labels,
            detail_info=detail_info,
        )
        external_use = "可" if "学外" in labels else "不可"

        display_name = _disambiguate_name(name, detail_url, model, name_seen)
        records.append(
            RawEquipment(
                equipment_id=_build_equipment_id(detail_url),
                name=display_name,
                category_general=CATEGORY_GENERAL,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use=external_use,
                fee_note=fee_note,
                conditions_note=conditions_note,
                source_url=detail_url or LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _extract_name(card: BeautifulSoup) -> str:
    name_node = card.select_one("h3")
    if not name_node:
        return ""
    return clean_text(name_node.get_text(" ", strip=True))


def _extract_detail_url(card: BeautifulSoup) -> str:
    anchor = card.select_one("a[href*='/equipments/view/']")
    if not anchor:
        return ""
    href = anchor.get("href", "")
    return urljoin(LIST_URL, href)


def _extract_description(card: BeautifulSoup) -> str:
    info = card.select_one("span.content")
    if not info:
        return ""
    return clean_text(info.get("data-content", ""))


def _extract_year(card: BeautifulSoup) -> str:
    text = clean_text(card.get_text(" ", strip=True))
    match = re.search(r"設置年[:：]?\s*(\d{4})", text)
    return match.group(1) if match else ""


def _extract_model(card: BeautifulSoup) -> str:
    caption = card.select_one(".caption")
    if not caption:
        return ""
    for para in caption.find_all("p"):
        text = clean_text(para.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _extract_labels(card: BeautifulSoup) -> list[str]:
    labels = []
    for label in card.select(".label"):
        text = clean_text(label.get_text(" ", strip=True))
        if text:
            labels.append(text)
    return labels


def _fetch_detail(url: str, timeout: int) -> dict[str, str]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    detail: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = clean_text(cells[0].get_text(" ", strip=True))
        value = clean_text(cells[1].get_text(" ", strip=True))
        if label:
            detail[label] = value
    return detail


def _pick_category_detail(detail_info: dict[str, str]) -> str:
    for key in ("装置カテゴリ", "適合分野"):
        value = detail_info.get(key, "")
        if value:
            return value
    return ""


def _build_address(detail_info: dict[str, str]) -> str:
    location = detail_info.get("拠点", "")
    if location:
        return f"岡山大学 {location}"
    return "岡山大学"


def _build_conditions_note(
    description: str,
    model: str,
    year: str,
    labels: list[str],
    detail_info: dict[str, str],
) -> str:
    parts: list[str] = []
    if description:
        parts.append(f"概要: {description}")
    if model:
        parts.append(f"機種: {model}")
    if year:
        parts.append(f"設置年: {year}")
    if labels:
        parts.append(f"利用区分: {', '.join(labels)}")
    caution = detail_info.get("利用にあたっての留意事項", "")
    if caution:
        parts.append(f"留意事項: {caution}")
    analysis = detail_info.get("分析内容", "")
    if analysis:
        parts.append(f"分析内容: {analysis}")
    return " / ".join(parts)


def _build_equipment_id(detail_url: str) -> str:
    if not detail_url:
        return ""
    path = urlparse(detail_url).path
    slug = path.rsplit("/", 1)[-1]
    return f"OKAYAMA-{slug}" if slug else ""


def _disambiguate_name(
    name: str, detail_url: str, model: str, seen: set[str]
) -> str:
    if name not in seen:
        seen.add(name)
        return name
    suffix = clean_text(model)
    if not suffix:
        suffix = _build_equipment_id(detail_url)
    if suffix and suffix not in name:
        updated = f"{name} ({suffix})"
    else:
        updated = name
    seen.add(updated)
    return updated
