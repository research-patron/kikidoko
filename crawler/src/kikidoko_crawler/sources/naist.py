from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://cmp.naist.jp/"
LIST_URL = urljoin(BASE_URL, "arim/instrument/")
ORG_NAME = "奈良先端科学技術大学院大学 マテリアル先端リサーチインフラ事業"
PREFECTURE = "奈良県"
BASE_ADDRESS = "奈良先端科学技術大学院大学"

DETAIL_LABELS = {"設備ID", "メーカー", "型式", "仕様", "概要", "担当者", "利用料", "備考"}


def fetch_naist_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    soup = _fetch_page(session, LIST_URL, timeout)
    if not soup:
        return []

    content = soup.find("main") or soup
    records: list[RawEquipment] = []
    current_category = ""

    for node in content.find_all(["h2", "h3", "h4", "table"]):
        if node.name in {"h2", "h3", "h4"}:
            heading = clean_text(node.get_text(" ", strip=True))
            if heading and "共用設備一覧" not in heading:
                current_category = heading
            continue

        if node.name != "table":
            continue
        if not _is_equipment_table(node):
            continue

        for row in node.find_all("tr")[1:]:
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if len(cells) < 6:
                continue
            equipment_code = cells[0]
            name = cells[1]
            maker = cells[2]
            model = cells[3]
            data_reg = cells[4]
            availability = cells[5]
            detail_url = _extract_detail_url(row)

            detail = _fetch_detail(session, detail_url, timeout) if detail_url else {}
            if detail.get("name"):
                name = detail["name"]
            fee_note = detail.get("利用料", "")
            conditions_note = _build_conditions_note(maker, model, data_reg, availability, detail)

            records.append(
                RawEquipment(
                    equipment_id=f"NAIST-{equipment_code}" if equipment_code else "",
                    name=name,
                    category_general=current_category,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=BASE_ADDRESS,
                    external_use="可" if availability == "○" else "要相談",
                    fee_note=fee_note,
                    conditions_note=conditions_note,
                    source_url=detail_url or LIST_URL,
                )
            )

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


def _is_equipment_table(table: Tag) -> bool:
    header_row = table.find("tr")
    if not header_row:
        return False
    headers = [
        clean_text(cell.get_text(" ", strip=True))
        for cell in header_row.find_all(["th", "td"])
    ]
    return "設備ID" in headers


def _extract_detail_url(row: Tag) -> str:
    anchor = row.find("a", href=True)
    if not anchor:
        return ""
    return urljoin(LIST_URL, anchor["href"])


def _fetch_detail(
    session: requests.Session, url: str, timeout: int
) -> dict[str, str]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    details: dict[str, str] = {}
    name_tag = soup.find("h1")
    if name_tag:
        details["name"] = clean_text(name_tag.get_text(" ", strip=True))

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = clean_text(th.get_text(" ", strip=True))
            if label not in DETAIL_LABELS:
                continue
            value = clean_text(td.get_text(" ", strip=True))
            if label and value:
                details[label] = value
    return details


def _build_conditions_note(
    maker: str,
    model: str,
    data_reg: str,
    availability: str,
    detail: dict[str, str],
) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if data_reg:
        parts.append(f"データ登録: {data_reg}")
    if availability:
        parts.append(f"機器利用可能: {availability}")
    spec = detail.get("仕様", "")
    if spec:
        parts.append(f"仕様: {spec}")
    overview = detail.get("概要", "")
    if overview:
        parts.append(f"概要: {overview}")
    contact = detail.get("担当者", "")
    if contact:
        parts.append(f"担当者: {contact}")
    note = detail.get("備考", "")
    if note:
        parts.append(f"備考: {note}")
    return " / ".join(parts)
