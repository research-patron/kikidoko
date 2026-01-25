from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://openfacility.sec.tsukuba.ac.jp/public_eq/front.php"
ORG_NAME = "筑波大学 オープンファシリティー推進機構"
PREFECTURE = "茨城県"
DEFAULT_PARAMS = {
    "cont": "eq_index",
    "sortid": "0",
    "p": "1",
    "recmax": "50",
    "div_id": "0",
    "cat_id": "0",
    "app_flag": "0",
    "form_sharing_outside_flag": "0",
    "form_trust_outside_flag": "0",
}


def fetch_tsukuba_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    records: list[RawEquipment] = []
    seen: set[str] = set()

    page = 1
    total_pages = 1
    while page <= total_pages:
        params = dict(DEFAULT_PARAMS)
        params["p"] = str(page)
        soup = _fetch_list(session, params, timeout)
        total_pages = _extract_total_pages(soup) or total_pages

        for summary in _extract_list_rows(soup):
            detail_url = summary.get("detail_url")
            if not detail_url:
                continue
            detail = _fetch_detail(session, detail_url, timeout)
            record = _build_record(summary, detail)
            if not record:
                continue
            key = record.equipment_id or f"{record.name}:{record.source_url}"
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if limit and len(records) >= limit:
                return records

        page += 1

    return records


def _fetch_list(
    session: requests.Session, params: dict[str, str], timeout: int
) -> BeautifulSoup:
    response = session.get(LIST_URL, params=params, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_total_pages(soup: BeautifulSoup) -> int:
    header = soup.select_one("th#res_title")
    if not header:
        return 0
    text = clean_text(header.get_text(" ", strip=True))
    match = re.search(r"(\d+)ページ中", text)
    return int(match.group(1)) if match else 0


def _extract_list_rows(soup: BeautifulSoup) -> list[dict[str, str]]:
    table = None
    for candidate in soup.find_all("table"):
        if candidate.select_one("th#res_title"):
            table = candidate
            break
    if not table:
        return []

    rows: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        name_cell = row.select_one("td.name a[href]")
        if not name_cell:
            continue
        href = name_cell.get("href", "")
        if "cont=eq_detail" not in href:
            continue
        detail_url = urljoin(LIST_URL, href)
        rows.append(
            {
                "detail_url": detail_url,
                "name": clean_text(name_cell.get_text(" ", strip=True)),
                "department": _cell_text(row, "td.div_name"),
                "category": _cell_text(row, "td.cat_name"),
                "maker": _cell_text(row, "td.maker"),
                "fee": _cell_text(row, "td.fee"),
                "trust_fee": _cell_text(row, "td.trust_fee"),
            }
        )
    return rows


def _fetch_detail(
    session: requests.Session, url: str, timeout: int
) -> dict[str, str]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    info: dict[str, str] = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            label = cells[0]
            value = cells[1]
            if label and value:
                info[label] = value
    return info


def _build_record(summary: dict[str, str], detail: dict[str, str]) -> RawEquipment | None:
    detail_url = summary.get("detail_url", "")
    if not detail_url:
        return None

    name = _prefer(detail.get("機器名（委託内容）"), summary.get("name", ""))
    if not name:
        return None

    category = _strip_english(detail.get("カテゴリー")) or summary.get("category", "")
    department = _strip_english(detail.get("部署")) or summary.get("department", "")
    location = _strip_english(detail.get("設置場所"))
    maker = detail.get("メーカー（型式）") or summary.get("maker", "")
    equipment_id = _extract_equipment_id(detail_url)
    fee_note = _join_fees(detail, summary)
    conditions_note = _join_notes(
        _format_note("メーカー/型式", maker),
        detail.get("機器担当者", ""),
        detail.get("相談窓口", ""),
    )

    return RawEquipment(
        equipment_id=_format_equipment_id(equipment_id),
        name=name,
        category_general=category,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=_join_notes(department, location),
        fee_note=fee_note,
        conditions_note=conditions_note,
        source_url=detail_url,
    )


def _cell_text(row: BeautifulSoup, selector: str) -> str:
    cell = row.select_one(selector)
    if not cell:
        return ""
    return clean_text(cell.get_text(" ", strip=True))


def _extract_equipment_id(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return query.get("id", [""])[0]


def _format_equipment_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return f"TSUKUBA-{raw_id}"


def _prefer(primary: str | None, fallback: str) -> str:
    return clean_text(primary or "") or clean_text(fallback or "")


def _strip_english(value: str | None) -> str:
    if not value:
        return ""
    text = clean_text(value)
    for index, char in enumerate(text):
        if "A" <= char <= "Z" or "a" <= char <= "z":
            return text[:index].strip()
    return text


def _join_fees(detail: dict[str, str], summary: dict[str, str]) -> str:
    parts: list[str] = []
    for key in ("利用単価", "委託単価"):
        value = detail.get(key, "")
        if value:
            parts.append(f"{key}: {value}")
    if not parts:
        fee = summary.get("fee", "")
        trust_fee = summary.get("trust_fee", "")
        if fee:
            parts.append(f"利用単価: {fee}")
        if trust_fee:
            parts.append(f"委託単価: {trust_fee}")
    return " / ".join([part for part in parts if part])


def _format_note(label: str, value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    return f"{label}: {value}"


def _join_notes(*notes: str) -> str:
    cleaned = [clean_text(note) for note in notes if clean_text(note)]
    return " / ".join(cleaned)
