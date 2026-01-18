from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://facilities-ap.irp.niigata-u.ac.jp"
LIST_URL_TEMPLATE = f"{BASE_URL}/niigataequipmentdb/equipment/list?page={{page}}"
ORG_FILTER = "新潟大学"
PREFECTURE = "新潟県"

DETAIL_LABELS = {
    "設備名称",
    "機関・部局名",
    "設置場所",
    "共同利用の可否",
    "どのような分析・計測ができるのか",
    "設備の仕様",
    "キーワード",
    "担当者氏名",
}


@dataclass(frozen=True)
class ListRow:
    category_general: str
    category_detail: str
    org_name: str
    department: str
    name: str
    detail_url: str
    analysis_example: str


def fetch_niigata_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    first_page = _fetch_page(session, 0, timeout)
    max_page = _extract_max_page(first_page)

    records: list[RawEquipment] = []
    for page in range(max_page + 1):
        soup = first_page if page == 0 else _fetch_page(session, page, timeout)
        for row in _parse_list_rows(soup):
            if ORG_FILTER not in row.org_name:
                continue
            detail_data = _fetch_detail(session, row.detail_url, timeout)
            name = detail_data.get("設備名称") or row.name
            org_name = detail_data.get("機関・部局名") or row.org_name
            location = detail_data.get("設置場所", "")
            external_use = _normalize_external_use(detail_data.get("共同利用の可否", ""))
            fee_note = detail_data.get("料金体系", "") or "料金要相談"
            conditions_note = _build_conditions_note(
                department=row.department,
                contact=detail_data.get("担当者氏名", ""),
                keywords=detail_data.get("キーワード", ""),
                analysis_example=row.analysis_example,
                analysis_detail=detail_data.get("どのような分析・計測ができるのか", ""),
                specs=detail_data.get("設備の仕様", ""),
            )
            address_raw = _build_address(org_name, location)

            records.append(
                RawEquipment(
                    equipment_id=_format_equipment_id(row.detail_url),
                    name=name,
                    category_general=row.category_general,
                    category_detail=row.category_detail,
                    org_name=org_name,
                    prefecture=PREFECTURE,
                    address_raw=address_raw,
                    external_use=external_use,
                    fee_note=fee_note,
                    conditions_note=conditions_note,
                    source_url=row.detail_url,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _fetch_page(session: requests.Session, page: int, timeout: int) -> BeautifulSoup:
    url = LIST_URL_TEMPLATE.format(page=page)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_max_page(soup: BeautifulSoup) -> int:
    pages: list[int] = []
    for anchor in soup.select("a[href*='equipment/list?page=']"):
        href = anchor.get("href", "")
        match = re.search(r"page=(\d+)", href)
        if match:
            pages.append(int(match.group(1)))
    return max(pages) if pages else 0


def _parse_list_rows(soup: BeautifulSoup) -> list[ListRow]:
    table = soup.find("table")
    if not table:
        return []
    rows: list[ListRow] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        category_general = clean_text(cells[0].get_text(" ", strip=True))
        category_detail = clean_text(cells[1].get_text(" ", strip=True))
        org_name = clean_text(cells[2].get_text(" ", strip=True))
        department = clean_text(cells[3].get_text(" ", strip=True))
        name, detail_url = _extract_name_and_url(cells[5])
        if not name:
            continue
        analysis_example = (
            clean_text(cells[6].get_text(" ", strip=True)) if len(cells) > 6 else ""
        )
        rows.append(
            ListRow(
                category_general=category_general,
                category_detail=category_detail,
                org_name=org_name,
                department=department,
                name=name,
                detail_url=detail_url,
                analysis_example=analysis_example,
            )
        )
    return rows


def _extract_name_and_url(cell: BeautifulSoup) -> tuple[str, str]:
    anchor = cell.find("a", href=True)
    if anchor:
        return (
            clean_text(anchor.get_text(" ", strip=True)),
            urljoin(BASE_URL, anchor["href"]),
        )
    return clean_text(cell.get_text(" ", strip=True)), LIST_URL_TEMPLATE.format(page=0)


def _fetch_detail(
    session: requests.Session, detail_url: str, timeout: int
) -> dict[str, str]:
    try:
        response = session.get(detail_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return {}
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    details: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = [clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
        if not cells:
            continue
        label = cells[0]
        if label in DETAIL_LABELS:
            value = " / ".join([cell for cell in cells[1:] if cell])
            if value:
                details[label] = value

    fee_note = _extract_fee_note(soup)
    if fee_note:
        details["料金体系"] = fee_note
    return details


def _extract_fee_note(soup: BeautifulSoup) -> str:
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = [clean_text(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        if not header_cells or "料金体系" not in " ".join(header_cells):
            continue
        if len(rows) <= 1:
            continue
        fee_items: list[str] = []
        for row in rows[1:]:
            cells = [clean_text(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            fee_items.append(" / ".join([cell for cell in cells if cell]))
        if fee_items:
            return " / ".join(fee_items)
    return ""


def _normalize_external_use(value: str) -> str:
    text = value or ""
    if "学外" in text or "企業" in text:
        return "可"
    if "学内" in text:
        return "不可"
    return text


def _build_address(org_name: str, location: str) -> str:
    parts = [part for part in (org_name, location) if part]
    if parts:
        return " ".join(parts)
    return "新潟大学"


def _build_conditions_note(
    department: str,
    contact: str,
    keywords: str,
    analysis_example: str,
    analysis_detail: str,
    specs: str,
) -> str:
    parts: list[str] = []
    if department:
        parts.append(f"部署名: {department}")
    if contact:
        parts.append(f"担当者: {contact}")
    if keywords:
        parts.append(f"キーワード: {keywords}")
    if analysis_example:
        parts.append(f"分析事例: {analysis_example}")
    if analysis_detail:
        parts.append(f"分析・計測: {analysis_detail}")
    if specs:
        parts.append(f"仕様: {specs}")
    return " / ".join(parts)


def _format_equipment_id(detail_url: str) -> str:
    match = re.search(r"/equipment/detail/(\\d+)/(\\d+)", detail_url)
    if not match:
        return ""
    return f"NIIGATA-{match.group(1)}-{match.group(2)}"
