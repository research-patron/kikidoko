from __future__ import annotations

from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://www.nims-open-facility.jp/"
LIST_URL = urljoin(BASE_URL, "page/page000124.html")
BASE_ADDRESS = "茨城県つくば市"


def fetch_nims_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    soup = _fetch_page(session, LIST_URL, timeout)
    if not soup:
        return []

    records: list[RawEquipment] = []
    for table in soup.find_all("table"):
        headers = _extract_headers(table)
        if "装置名" not in headers:
            continue
        category_general = _extract_heading(table, "h2")
        category_detail = _extract_heading(table, "h3")
        rows = table.find_all("tr")
        for row in rows[1:]:
            if limit and len(records) >= limit:
                return records
            cells = row.find_all("td")
            if not cells:
                continue
            name, detail_url = _extract_name_and_url(cells[0])
            if not name:
                continue
            maker = _cell_text(cells, 1)
            model = _cell_text(cells, 2)

            detail = _fetch_detail(session, detail_url, timeout) if detail_url else {}
            detail_name = detail.get("装置名称")
            if detail_name:
                name = detail_name
            equipment_id = _format_equipment_id(detail.get("装置ID"), detail_url)
            location = detail.get("設置場所", "")
            fee_note = detail.get("料金案内", "")
            external_use = _normalize_external_use(
                detail.get("マテリアル先端リサーチインフラの利用", "")
            )
            conditions_note = _build_conditions_note(maker, model, detail)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=category_general,
                    category_detail=category_detail,
                    org_name="物質・材料研究機構 NIMS Open Facility",
                    address_raw=_build_address(location),
                    external_use=external_use,
                    fee_note=fee_note,
                    conditions_note=conditions_note,
                    source_url=detail_url or LIST_URL,
                )
            )

    return records


def _fetch_page(
    session: requests.Session, url: str, timeout: int
) -> BeautifulSoup | None:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_headers(table: BeautifulSoup) -> list[str]:
    header_row = table.find("tr")
    if not header_row:
        return []
    return [
        clean_text(cell.get_text(" ", strip=True))
        for cell in header_row.find_all(["td", "th"])
    ]


def _extract_heading(table: BeautifulSoup, tag: str) -> str:
    for prev in table.find_all_previous([tag]):
        text = clean_text(prev.get_text(" ", strip=True))
        if text:
            return _strip_english(text)
    return ""


def _strip_english(text: str) -> str:
    for index, char in enumerate(text):
        if "A" <= char <= "Z" or "a" <= char <= "z":
            return text[:index].strip()
    return text.strip()


def _extract_name_and_url(cell: BeautifulSoup) -> tuple[str, str]:
    anchor = cell.find("a", href=True)
    if anchor:
        name = clean_text(anchor.get_text(" ", strip=True))
        return name, urljoin(LIST_URL, anchor["href"])
    return clean_text(cell.get_text(" ", strip=True)), ""


def _cell_text(cells: list[BeautifulSoup], index: int) -> str:
    if index < 0 or index >= len(cells):
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def _fetch_detail(
    session: requests.Session, url: str, timeout: int
) -> dict[str, str]:
    if not url:
        return {}
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    if "html" not in (response.headers.get("content-type") or ""):
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    details: dict[str, str] = {}
    for row in soup.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = clean_text(th.get_text(" ", strip=True))
        value = clean_text(td.get_text(" ", strip=True))
        if label and value:
            details[label] = value
    return details


def _format_equipment_id(raw_id: str | None, url: str) -> str:
    code = _extract_code(url)
    if code and raw_id:
        return f"NIMS-{code}-{raw_id}"
    if code:
        return f"NIMS-{code}"
    if raw_id:
        return f"NIMS-{raw_id}"
    return ""


def _extract_code(url: str) -> str:
    if not url:
        return ""
    query = parse_qs(urlparse(url).query)
    return query.get("code", [""])[0]


def _normalize_external_use(value: str) -> str:
    if "○" in value:
        return "可"
    if "×" in value:
        return "不可"
    return ""


def _build_conditions_note(
    maker: str, model: str, detail: dict[str, str]
) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型番: {model}")
    usage = detail.get("用途")
    if usage:
        parts.append(f"用途: {usage}")
    spec = detail.get("仕様")
    if spec:
        parts.append(f"仕様: {spec}")
    usage_type = detail.get("利用可能形態")
    if usage_type:
        parts.append(f"利用可能形態: {usage_type}")
    usage_unit = detail.get("利用時間単位")
    if usage_unit:
        parts.append(f"利用時間単位: {usage_unit}")
    contact = detail.get("問い合わせ先部署")
    if contact:
        parts.append(f"問い合わせ先: {contact}")
    return " / ".join(parts)


def _build_address(location: str) -> str:
    if not location:
        return BASE_ADDRESS
    if "茨城県" in location:
        return location
    return f"{BASE_ADDRESS} {location}"
