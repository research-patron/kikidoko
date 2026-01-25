from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://www.iac.ynu.ac.jp"
LIST_URL = f"{BASE_URL}/item_search/machine_list"
ORG_NAME = "横浜国立大学 機器分析評価センター"
PREFECTURE = "神奈川県"
CATEGORY_GENERAL = "研究設備"


def fetch_ynu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    response = session.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    detail_urls = _collect_detail_urls(soup)
    records: list[RawEquipment] = []
    seen: set[str] = set()
    for url in detail_urls:
        record = _fetch_detail(session, url, timeout)
        if not record:
            continue
        dedupe_key = record.equipment_id or f"{record.name}:{record.source_url}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(record)
        if limit and len(records) >= limit:
            return records
    return records


def _collect_detail_urls(soup: BeautifulSoup) -> list[str]:
    urls: set[str] = set()
    for anchor in soup.select('a[href*="/item_search/machine_list/"]'):
        href = anchor.get("href", "")
        if not href:
            continue
        full_url = urljoin(BASE_URL, href)
        if urlparse(full_url).path.rstrip("/") == "/item_search/machine_list":
            continue
        urls.add(full_url)
    return sorted(urls)


def _fetch_detail(
    session: requests.Session, url: str, timeout: int
) -> RawEquipment | None:
    soup = _fetch_detail_page(session, url, timeout)
    if not soup:
        return None
    item = soup.select_one(".result-item")
    if not item:
        return None

    info = _extract_info(item)
    name = info.get("機器名", "") or _extract_title_name(soup)
    if not name:
        return None

    address_raw = info.get("設置場所") or info.get("場所") or ORG_NAME
    external_use = info.get("利用対象", "")
    fee_note = info.get("利用料金") or info.get("料金") or ""
    conditions_note = _build_conditions_note(info)

    return RawEquipment(
        equipment_id=_build_equipment_id(url),
        name=name,
        category_general=CATEGORY_GENERAL,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=address_raw,
        external_use=external_use,
        fee_note=fee_note,
        conditions_note=conditions_note,
        source_url=url,
    )


def _fetch_detail_page(
    session: requests.Session, url: str, timeout: int
) -> BeautifulSoup | None:
    for attempt in range(2):
        try:
            effective_timeout = timeout if attempt == 0 else max(timeout, 60)
            response = session.get(url, timeout=effective_timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException:
            if attempt == 0:
                continue
            return None
    return None


def _extract_info(item: BeautifulSoup) -> dict[str, str]:
    info: dict[str, str] = {}
    for li in item.select("li"):
        title = li.select_one(".summary-title")
        text = li.select_one(".summary-text")
        if not title or not text:
            continue
        label = clean_text(title.get_text(" ", strip=True))
        value = clean_text(text.get_text(" ", strip=True))
        if label and value:
            info[label] = value
    return info


def _build_conditions_note(info: dict[str, str]) -> str:
    parts: list[str] = []
    if info.get("機器名(英語)"):
        parts.append(f"機器名(英語): {info['機器名(英語)']}")
    if info.get("メーカー"):
        parts.append(f"メーカー: {info['メーカー']}")
    if info.get("メーカー(英語)"):
        parts.append(f"メーカー(英語): {info['メーカー(英語)']}")
    if info.get("型式"):
        parts.append(f"型式: {info['型式']}")
    if info.get("利用目的"):
        parts.append(f"利用目的: {info['利用目的']}")
    if info.get("担当"):
        parts.append(f"担当: {info['担当']}")
    if info.get("連絡先"):
        parts.append(f"連絡先: {info['連絡先']}")
    return " / ".join(parts)


def _build_equipment_id(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    if not slug:
        return ""
    return f"YNU-{slug.upper()}"


def _extract_title_name(soup: BeautifulSoup) -> str:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if not title:
        return ""
    if "|" in title:
        title = title.split("|", 1)[0]
    return clean_text(title)
