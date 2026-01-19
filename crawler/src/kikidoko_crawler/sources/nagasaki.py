from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://nushare.ura.nagasaki-u.ac.jp/equipment/equipmentlist.php"
DETAIL_URL = "https://nushare.ura.nagasaki-u.ac.jp/equipment/equipmentdetail.php"
ORG_NAME = "長崎大学"
PREFECTURE = "長崎県"

DETAIL_FIELDS = (
    "メーカー",
    "型番",
    "装置の特徴",
    "設置部局",
    "連絡担当者",
    "管理責任者",
    "備考",
    "利用可能時間帯",
    "利用可能な単位",
    "利用資格",
    "予約時承認",
)


def fetch_nagasaki_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    soup = _fetch_page(session, LIST_URL, timeout)
    if not soup:
        return []

    records: list[RawEquipment] = []
    for eq_no, fallback in _extract_list_entries(soup):
        detail = _fetch_detail(session, eq_no, timeout)
        name = detail.get("name") or fallback.get("name", "")
        if not name:
            continue

        category_general = detail.get("システム") or fallback.get("system", "")
        category_detail = detail.get("カテゴリ", "")
        address_raw = _build_address(detail.get("設置場所", "") or fallback.get("location", ""))
        fee_note = detail.get("機器利用", "")
        conditions_note = _build_conditions_note(detail, fallback)
        records.append(
            RawEquipment(
                equipment_id=f"NAGASAKI-{eq_no}" if eq_no else "",
                name=name,
                category_general=category_general,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use="要相談",
                fee_note=fee_note,
                conditions_note=conditions_note,
                source_url=LIST_URL,
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


def _extract_list_entries(soup: BeautifulSoup) -> list[tuple[str, dict[str, str]]]:
    table = soup.find("table")
    if not table:
        return []

    entries: list[tuple[str, dict[str, str]]] = []
    for row in table.find_all("tr"):
        button = row.find("button", onclick=True)
        if not button:
            continue
        eq_no = _extract_eq_no(button.get("onclick", ""))
        if not eq_no:
            continue
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) < 7:
            continue
        entry = {
            "system": cells[1],
            "name": cells[2],
            "maker": cells[3],
            "location": cells[4],
            "admin": cells[5],
            "manager": cells[6],
        }
        entries.append((eq_no, entry))
    return entries


def _extract_eq_no(value: str) -> str:
    match = re.search(r"fncDetails\((\d+)\)", value)
    return match.group(1) if match else ""


def _fetch_detail(
    session: requests.Session, eq_no: str, timeout: int
) -> dict[str, str]:
    if not eq_no:
        return {}
    response = session.post(DETAIL_URL, data={"eq_no": eq_no}, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    details: dict[str, str] = {}
    name_tag = soup.select_one("div.syscolor1")
    if name_tag:
        details["name"] = _strip_english(clean_text(name_tag.get_text(" ", strip=True)))

    for item in soup.select("div.outbox_item"):
        label_tag = item.select_one(".box_th")
        value_tag = item.select_one(".box_td")
        if not label_tag or not value_tag:
            continue
        label = _normalize_label(label_tag.get_text(" ", strip=True))
        value = _strip_english(clean_text(value_tag.get_text(" ", strip=True)))
        if label and not _is_placeholder(value):
            details[label] = value

    return details


def _normalize_label(label: str) -> str:
    label = clean_text(label)
    return label.split(" ", 1)[0] if label else ""


def _strip_english(value: str) -> str:
    if " / " in value:
        return value.split(" / ", 1)[0].strip()
    return value.strip()


def _is_placeholder(value: str) -> bool:
    return value in {"", "-", "ー", "―", "—"}


def _build_address(location: str) -> str:
    if not location:
        return ORG_NAME
    if "長崎" in location or "大学" in location:
        return location
    return f"{ORG_NAME} {location}"


def _build_conditions_note(details: dict[str, str], fallback: dict[str, str]) -> str:
    parts: list[str] = []
    maker = details.get("メーカー") or fallback.get("maker", "")
    if maker:
        parts.append(f"メーカー: {maker}")
    model = details.get("型番", "")
    if model:
        parts.append(f"型番: {model}")

    for key in DETAIL_FIELDS:
        value = details.get(key, "")
        if value and key not in {"メーカー", "型番"}:
            parts.append(f"{key}: {value}")

    admin = fallback.get("admin", "")
    if admin and "連絡担当者" not in details:
        parts.append(f"連絡担当者: {admin}")
    manager = fallback.get("manager", "")
    if manager and "管理責任者" not in details:
        parts.append(f"管理責任者: {manager}")

    return " / ".join(dict.fromkeys(parts))
