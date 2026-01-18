from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://portal.cfc.tohoku.ac.jp/"
LIST_URL = urljoin(BASE_URL, "devices/")
PAGE_TEMPLATE = urljoin(BASE_URL, "devices/page/{page}/")


def fetch_tohoku_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    max_page = _discover_max_page(session, timeout)
    records: list[RawEquipment] = []
    seen: set[str] = set()

    for page in range(1, max_page + 1):
        list_url = LIST_URL if page == 1 else PAGE_TEMPLATE.format(page=page)
        soup = _fetch_page(session, list_url, timeout)
        if not soup:
            continue
        for detail_url in _extract_detail_urls(soup):
            record = _fetch_detail_record(session, detail_url, timeout)
            if not record:
                continue
            dedupe_hint = record.equipment_id or record.name or record.source_url
            if dedupe_hint and dedupe_hint in seen:
                continue
            if dedupe_hint:
                seen.add(dedupe_hint)
            records.append(record)
            if limit and len(records) >= limit:
                return records

    return records


def _discover_max_page(session: requests.Session, timeout: int) -> int:
    soup = _fetch_page(session, LIST_URL, timeout)
    if not soup:
        return 1
    max_page = 1
    for anchor in soup.select("a.page-numbers"):
        text = anchor.get_text(strip=True)
        if text.isdigit():
            max_page = max(max_page, int(text))
    return max_page


def _fetch_page(
    session: requests.Session, url: str, timeout: int
) -> BeautifulSoup | None:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_detail_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    for anchor in soup.select("ul.item__list a[href]"):
        href = anchor.get("href", "")
        if "/devices/" not in href or "post-" not in href:
            continue
        urls.append(urljoin(BASE_URL, href))
    return list(dict.fromkeys(urls))


def _fetch_detail_record(
    session: requests.Session, url: str, timeout: int
) -> RawEquipment | None:
    soup = _fetch_page(session, url, timeout)
    if not soup:
        return None
    title = _extract_title(soup)
    details = _extract_details(soup)
    equipment_id = _format_equipment_id(details.get("ID"), url)
    category_general, category_detail = _split_category(details.get("設備・機器分類", ""))
    campus = details.get("キャンパス", "")
    department = details.get("部局", "")
    address_raw = _join_address(campus, department)
    external_use = _normalize_external_use(details.get("利用区分", ""))
    fee_note = _extract_fee(details)
    conditions_note = _build_conditions_note(details)

    return RawEquipment(
        equipment_id=equipment_id,
        name=title,
        category_general=category_general,
        category_detail=category_detail,
        org_name="東北大学",
        prefecture="宮城県",
        address_raw=address_raw,
        external_use=external_use,
        fee_note=fee_note,
        conditions_note=conditions_note,
        source_url=url,
    )


def _extract_title(soup: BeautifulSoup) -> str:
    heading = soup.find("h2")
    if heading:
        return clean_text(heading.get_text(" ", strip=True))
    return ""


def _extract_details(soup: BeautifulSoup) -> dict[str, str]:
    details: dict[str, str] = {}
    detail_list = soup.select_one("dl.devices__detail")
    if not detail_list:
        return details
    for dt in detail_list.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        label = clean_text(dt.get_text(" ", strip=True))
        value = clean_text(dd.get_text(" ", strip=True))
        if label:
            details[label] = value
    return details


def _split_category(value: str) -> tuple[str, str]:
    if not value:
        return "", ""
    normalized = value.replace("｜", "|")
    parts = [clean_text(part) for part in normalized.split("|") if clean_text(part)]
    if not parts:
        return "", ""
    general = parts[0]
    detail = parts[1] if len(parts) > 1 else ""
    return general, detail


def _normalize_external_use(value: str) -> str:
    if not value:
        return ""
    if "学外" not in value:
        return ""
    if any(mark in value for mark in ["学外：〇", "学外:〇", "学外：○", "学外:○"]):
        return "可"
    if any(mark in value for mark in ["学外：×", "学外:×", "学外：✕", "学外:✕"]):
        return "不可"
    if "学外：△" in value or "学外:△" in value:
        return "要相談"
    return ""


def _extract_fee(details: dict[str, str]) -> str:
    for label, value in details.items():
        if "料金" in label:
            return value
    return ""


def _build_conditions_note(details: dict[str, str]) -> str:
    parts: list[str] = []
    maker = details.get("メーカー", "")
    model = details.get("型式", "")
    spec = details.get("仕様・特徴", "")
    usage = details.get("用途・使用目的", "")
    unit = details.get("管理部署", "")
    manager = details.get("設備担当者", "")
    reservation = details.get("予約サイトのURL", "")
    note = details.get("備考", "")

    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if spec and spec != "ー":
        parts.append(f"仕様: {spec}")
    if usage and usage != "ー":
        parts.append(f"用途: {usage}")
    if unit and unit != "ー":
        parts.append(f"管理部署: {unit}")
    if manager and manager != "ー":
        parts.append(f"設備担当者: {manager}")
    if reservation and reservation != "ー":
        parts.append(f"予約サイト: {reservation}")
    if note and note != "ー":
        parts.append(f"備考: {note}")
    return " / ".join(parts)


def _format_equipment_id(raw_id: str | None, url: str) -> str:
    raw_id = clean_text(raw_id or "")
    if raw_id:
        return f"TOHOKU-{raw_id}"
    match = re.search(r"post-(\\d+)", url)
    if match:
        return f"TOHOKU-{match.group(1)}"
    return ""


def _join_address(campus: str, department: str) -> str:
    campus = clean_text(campus)
    department = clean_text(department)
    if campus and department:
        return f"{campus} {department}"
    return campus or department
