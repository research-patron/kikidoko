from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.oif.mie-u.ac.jp/equipment-list"
ORG_NAME = "三重大学 研究基盤推進機構 先端科学研究支援センター オープンイノベーション施設"
PREFECTURE = "三重県"


def fetch_mie_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for section in soup.select("h3"):
        category = clean_text(section.get_text(" ", strip=True))
        table = section.find_next_sibling("div", class_="device_table")
        if not table:
            continue
        for row in table.select("div.tr"):
            link_tag = row.find("a", href=True)
            if not link_tag:
                continue
            detail_url = urljoin(LIST_URL, link_tag["href"])
            name, maker, model, summary = _extract_row_values(link_tag)
            if not name:
                continue
            details = _fetch_detail(detail_url, timeout)
            source_url = detail_url
            if not details:
                source_url = LIST_URL
            detail_name = details.get("機器名称")
            if detail_name:
                name = detail_name

            address_raw = details.get("設置場所", "")
            if not address_raw:
                address_raw = "オープンイノベーション施設"
            contact = details.get("連絡先", "")
            usage = details.get("用途", "")
            features = details.get("仕様・特徴", "")
            maker_model = details.get("メーカー・型番", "")
            equipment_id = _build_equipment_id(detail_url)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=category,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=address_raw,
                    external_use="要相談",
                    fee_note="",
                    conditions_note=_build_conditions_note(
                        maker_model, maker, model, summary, usage, features, contact
                    ),
                    source_url=source_url,
                )
            )

            if limit and len(records) >= limit:
                return records

    return records


def _extract_row_values(link_tag: Tag) -> tuple[str, str, str, str]:
    cols = [clean_text(div.get_text(" ", strip=True)) for div in link_tag.find_all("div", recursive=False)]
    name = cols[0] if len(cols) > 0 else ""
    maker = cols[1] if len(cols) > 1 else ""
    model = cols[2] if len(cols) > 2 else ""
    summary = cols[3] if len(cols) > 3 else ""
    maker = maker.replace("／", "").replace("/", "").strip()
    return name, maker, model, summary


def _fetch_detail(url: str, timeout: int) -> dict[str, str]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    details: dict[str, str] = {}
    for block in soup.select("div.detail_single"):
        label_tag = block.select_one("p.midashi")
        if not label_tag:
            continue
        label = clean_text(label_tag.get_text(" ", strip=True))
        value = _extract_detail_value(block, label_tag)
        if label:
            details[label] = value
    return details


def _extract_detail_value(block: Tag, label_tag: Tag) -> str:
    for candidate in block.find_all(["h2", "p"]):
        if candidate is label_tag:
            continue
        if "midashi" in (candidate.get("class") or []):
            continue
        text = clean_text(candidate.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _build_equipment_id(source_url: str) -> str:
    parsed = urlparse(source_url)
    slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if slug:
        return f"MIE-{slug}"
    return ""


def _build_conditions_note(
    maker_model: str,
    maker: str,
    model: str,
    summary: str,
    usage: str,
    features: str,
    contact: str,
) -> str:
    parts: list[str] = []
    if maker_model:
        parts.append(f"メーカー・型番: {maker_model}")
    else:
        if maker:
            parts.append(f"メーカー: {maker}")
        if model:
            parts.append(f"型番: {model}")
    if summary:
        parts.append(f"機器概要: {summary}")
    if usage:
        parts.append(f"用途: {usage}")
    if features:
        parts.append(f"仕様・特徴: {features}")
    if contact:
        parts.append(f"連絡先: {contact}")
    return " / ".join(parts)
