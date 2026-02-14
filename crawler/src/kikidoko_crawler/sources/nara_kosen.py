from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.nit-nara-ia-center.share-ac.jp/facilities/"
ORG_NAME = "奈良工業高等専門学校 共通機器管理センター"
PREFECTURE = "奈良県"
CATEGORY_GENERAL = "共同利用設備"
DETAIL_ID_RE = re.compile(r"detail\.php\?id=(\d+)")


def fetch_nara_kosen_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    detail_links = _extract_detail_links(soup)
    records: list[RawEquipment] = []
    seen_ids: set[str] = set()
    session = requests.Session()
    for detail_url, list_name in detail_links:
        detail_id = _extract_detail_id(detail_url)
        equipment_id = f"NARA-KOSEN-{detail_id}" if detail_id else ""
        if equipment_id and equipment_id in seen_ids:
            continue

        detail = _fetch_detail(session, detail_url, timeout)
        if not detail:
            continue

        name = detail.get("name") or list_name
        if not name:
            continue
        if not equipment_id:
            equipment_id = f"NARA-KOSEN-{len(records) + 1:03d}"
        seen_ids.add(equipment_id)

        conditions_note = _build_conditions_note(detail)
        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=detail.get("location", ""),
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=detail.get("location", ORG_NAME),
                external_use="可",
                fee_note=_truncate(detail.get("fee", ""), 280),
                conditions_note=_truncate(conditions_note, 1200),
                source_url=detail_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _extract_detail_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = clean_text(anchor.get("href", ""))
        if "detail.php?id=" not in href:
            continue
        detail_url = urljoin(LIST_URL, href)
        if detail_url in seen:
            continue
        seen.add(detail_url)
        list_name = _normalize_list_name(anchor.get_text(" ", strip=True))
        links.append((detail_url, list_name))
    return links


def _normalize_list_name(value: str) -> str:
    text = clean_text(value)
    # e.g. "- C1 - XXX 物質化学工学科" -> "XXX"
    text = re.sub(r"^-\s*[A-Za-z0-9]+\s*-\s*", "", text)
    text = re.sub(r"\s+物質化学工学科$", "", text)
    return clean_text(text)


def _extract_detail_id(url: str) -> str:
    match = DETAIL_ID_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    value = (params.get("id") or [""])[0]
    return clean_text(value)


def _fetch_detail(session: requests.Session, detail_url: str, timeout: int) -> dict[str, str]:
    response = session.get(detail_url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    detail: dict[str, str] = {
        "name": clean_text(
            (soup.select_one(".title_underline") or soup.select_one(".page_title")).get_text(
                " ", strip=True
            )
            if (soup.select_one(".title_underline") or soup.select_one(".page_title"))
            else ""
        ),
        "location": clean_text(soup.select_one(".location").get_text(" ", strip=True))
        if soup.select_one(".location")
        else "",
        "fee": "",
    }

    for h4 in soup.select(".fac_text h4"):
        key = clean_text(h4.get_text(" ", strip=True))
        if not key:
            continue
        values: list[str] = []
        node = h4.find_next_sibling()
        while node and getattr(node, "name", "") != "h4":
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                values.append(text)
            node = node.find_next_sibling()
        if not values:
            continue
        detail[key] = " / ".join(values)
        if key == "利用料金":
            detail["fee"] = detail[key]

    return detail


def _build_conditions_note(detail: dict[str, str]) -> str:
    order = ["仕様", "概要・性能", "利用の注意事項", "機器設置部局"]
    parts: list[str] = []
    for label in order:
        value = clean_text(detail.get(label, ""))
        if value:
            parts.append(f"{label}: {value}")
    return " / ".join(parts)


def _truncate(value: str, max_len: int) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"

