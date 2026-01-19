from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://fsc-out-ap.vss.miyazaki-u.ac.jp/equipmentdb/equipment"
ORG_PREFIX = "宮崎大学"
PREFECTURE = "宮崎県"


def fetch_miyazaki_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    rows = table.find_all("tr")
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        major = clean_text(cells[0].get_text(" ", strip=True))
        minor = clean_text(cells[1].get_text(" ", strip=True))
        org = clean_text(cells[2].get_text(" ", strip=True))
        dept = clean_text(cells[3].get_text(" ", strip=True))
        name_cell = cells[5]
        usage = clean_text(cells[6].get_text(" ", strip=True))
        name = clean_text(name_cell.get_text(" ", strip=True))
        if not name:
            continue

        detail_url = _extract_detail_url(name_cell)
        detail = _fetch_detail(detail_url, timeout) if detail_url else {}

        if detail.get("設備名称"):
            name = detail["設備名称"]
        category_general = detail.get("大項目") or major
        category_detail = detail.get("小項目") or minor

        org_name = _build_org_name(org, dept)
        address_raw = detail.get("設置場所") or org_name
        if _is_masked_address(address_raw):
            address_raw = org_name
        conditions_note = _build_conditions_note(usage, detail)
        equipment_id = _build_equipment_id(detail_url)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=category_general,
                category_detail=category_detail,
                org_name=org_name,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use="要相談",
                fee_note="",
                conditions_note=conditions_note,
                source_url=detail_url or LIST_URL,
            )
        )

        if limit and len(records) >= limit:
            return records

    return records


def _extract_detail_url(cell: Tag) -> str:
    anchor = cell.find("a", href=True)
    if not anchor:
        return ""
    return urljoin(LIST_URL, anchor["href"])


def _fetch_detail(url: str, timeout: int) -> dict[str, str]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return {}

    rows = table.find_all("tr")
    details: dict[str, str] = {}
    index = 0
    while index < len(rows):
        row = rows[index]
        headers = row.find_all("th")
        cells = row.find_all("td")
        if headers and cells:
            label = clean_text(headers[0].get_text(" ", strip=True))
            if label == "分類":
                if index + 1 < len(rows):
                    values = rows[index + 1].find_all("td")
                    if values:
                        details["大項目"] = clean_text(values[0].get_text(" ", strip=True))
                        if len(values) > 1:
                            details["小項目"] = clean_text(values[1].get_text(" ", strip=True))
                    index += 1
            else:
                value = clean_text(" ".join(cell.get_text(" ", strip=True) for cell in cells))
                if label and value:
                    details[label] = value
        index += 1

    return details


def _build_org_name(org: str, dept: str) -> str:
    parts: list[str] = []
    if org:
        parts.append(org)
    if dept:
        parts.append(dept)
    name = " ".join(parts).strip()
    if not name:
        return ORG_PREFIX
    if ORG_PREFIX not in name:
        return f"{ORG_PREFIX} {name}"
    return name


def _is_masked_address(value: str) -> bool:
    if not value:
        return True
    stripped = value.replace("※", "").strip()
    return stripped == ""


def _build_equipment_id(detail_url: str) -> str:
    if not detail_url:
        return ""
    slug = detail_url.rstrip("/").rsplit("/", 1)[-1]
    if not slug:
        return ""
    return f"MIYAZAKI-{slug}"


def _build_conditions_note(usage: str, detail: dict[str, str]) -> str:
    parts: list[str] = []
    if detail.get("メーカー"):
        parts.append(f"メーカー: {detail['メーカー']}")
    if detail.get("型番"):
        parts.append(f"型番: {detail['型番']}")
    if usage:
        parts.append(f"用途: {usage}")
    if detail.get("留意事項"):
        parts.append(f"留意事項: {detail['留意事項']}")
    return " / ".join(parts)
