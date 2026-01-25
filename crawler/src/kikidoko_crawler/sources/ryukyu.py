from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://ur-core.lab.u-ryukyu.ac.jp/ur-core"
LIST_URL = f"{BASE_URL}/equipment/list"
ORG_PREFIX = "琉球大学"
PREFECTURE = "沖縄県"


def fetch_ryukyu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    first_page = _fetch_page(session, f"{LIST_URL}?page=0", timeout)
    if not first_page:
        return []
    max_page = _extract_max_page(first_page)

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for page in range(0, max_page + 1):
        soup = _fetch_page(session, f"{LIST_URL}?page={page}", timeout)
        if not soup:
            continue
        table = soup.find("table")
        if not table:
            continue
        for row in table.find_all("tr")[1:]:
            record = _parse_list_row(session, row, timeout)
            if not record:
                continue
            dedupe = record.equipment_id or f"{record.name}:{record.source_url}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            records.append(record)
            if limit and len(records) >= limit:
                return records
    return records


def _fetch_page(
    session: requests.Session, url: str, timeout: int
) -> BeautifulSoup | None:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_max_page(soup: BeautifulSoup) -> int:
    pages: list[int] = []
    for anchor in soup.select('a[href*="page="]'):
        href = anchor.get("href", "")
        match = re.search(r"page=(\d+)", href)
        if match:
            pages.append(int(match.group(1)))
    return max(pages) if pages else 0


def _parse_list_row(
    session: requests.Session, row: BeautifulSoup, timeout: int
) -> RawEquipment | None:
    cells = row.find_all("td")
    if len(cells) < 4:
        return None

    detail_link = cells[0].find("a", href=True)
    detail_url = urljoin(BASE_URL, detail_link["href"]) if detail_link else ""
    category_general = clean_text(cells[1].get_text(" ", strip=True))
    department = clean_text(cells[2].get_text(" ", strip=True))
    name = clean_text(cells[3].get_text(" ", strip=True))
    analysis_case = clean_text(cells[5].get_text(" ", strip=True)) if len(cells) > 5 else ""
    if not name:
        return None

    detail = _fetch_detail(session, detail_url, timeout) if detail_url else {}
    category_detail = detail.get("小項目", "")
    equipment_id = _build_equipment_id(detail_url, name)
    org_name = _build_org_name(department or detail.get("設置部局", ""))
    address_raw = detail.get("設置場所", "") or department

    conditions_note = _build_conditions_note(detail, analysis_case)
    external_use = detail.get("共用利用形態", "")
    fee_note = detail.get("利用料金", "")

    return RawEquipment(
        equipment_id=equipment_id,
        name=name,
        category_general=category_general,
        category_detail=category_detail,
        org_name=org_name,
        prefecture=PREFECTURE,
        address_raw=address_raw,
        external_use=external_use,
        fee_note=fee_note,
        conditions_note=conditions_note,
        source_url=detail_url or LIST_URL,
    )


def _fetch_detail(
    session: requests.Session, url: str, timeout: int
) -> dict[str, str]:
    soup = _fetch_page(session, url, timeout)
    if not soup:
        return {}

    table = soup.find("table")
    if not table:
        return {}

    info: dict[str, str] = {}
    rows = table.find_all("tr")
    for index, row in enumerate(rows):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) >= 2:
            label = cells[0]
            value = cells[1]
            if label:
                info[label] = value
        if cells == ["大項目", "小項目"] and index + 1 < len(rows):
            next_cells = [
                clean_text(cell.get_text(" ", strip=True))
                for cell in rows[index + 1].find_all(["th", "td"])
            ]
            if len(next_cells) >= 2:
                info["大項目"] = next_cells[0]
                info["小項目"] = next_cells[1]
    return info


def _build_equipment_id(detail_url: str, name: str) -> str:
    match = re.search(r"/detail/\d+/(\d+)", detail_url or "")
    if match:
        return f"RYUKYU-{match.group(1)}"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(name)).strip("-")
    return f"RYUKYU-{slug}" if slug else ""


def _build_org_name(department: str) -> str:
    department = clean_text(department)
    if not department:
        return f"{ORG_PREFIX} 研究基盤統括センター"
    if department.startswith(ORG_PREFIX):
        return department
    return f"{ORG_PREFIX} {department}"


def _build_conditions_note(detail: dict[str, str], analysis_case: str) -> str:
    parts: list[str] = []
    maker = detail.get("メーカー", "")
    model = detail.get("型番", "")
    general_name = detail.get("一般名称", "")
    overview = detail.get("概要", "")
    cautions = detail.get("留意事項", "")
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型番: {model}")
    if general_name:
        parts.append(f"一般名称: {general_name}")
    if overview:
        parts.append(f"概要: {overview}")
    if analysis_case:
        parts.append(f"分析事例: {analysis_case}")
    if cautions:
        parts.append(f"留意事項: {cautions}")
    return " / ".join([part for part in parts if part])
