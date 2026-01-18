from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://www.ics-com.biz/todai_kyouyou/portals/machine/"
DETAIL_PATH = "/todai_kyouyou/portals/machine_detail/"

LIST_LINK_PATTERNS = ("/portals/machine/",)


@dataclass(frozen=True)
class ColumnIndex:
    equipment_id: int | None = None
    name: int | None = None
    campus: int | None = None
    location: int | None = None
    scope: int | None = None
    detail: int | None = None


_SESSION: requests.Session | None = None


class LegacyTLSAdapter(HTTPAdapter):
    def __init__(self, ssl_context, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = self._ssl_context
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def fetch_utokyo_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = _get_session()
    records: list[RawEquipment] = []
    seen: set[str] = set()
    queue = [BASE_URL]
    visited: set[str] = set()

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        soup = _fetch_page(session, url, timeout)
        if not soup:
            continue

        table = _find_equipment_table(soup)
        if table:
            for record in _extract_records(table, url):
                dedupe_hint = record.equipment_id or record.name or record.source_url
                if dedupe_hint and dedupe_hint in seen:
                    continue
                if dedupe_hint:
                    seen.add(dedupe_hint)
                records.append(record)
                if limit and len(records) >= limit:
                    return records

        for link in _collect_list_links(soup, url):
            if link not in visited:
                queue.append(link)

        for link in _collect_pagination_links(soup, url):
            if link not in visited:
                queue.append(link)

    return records


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    context = create_urllib3_context()
    # Allow legacy DH parameters on older TLS endpoints.
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    adapter = LegacyTLSAdapter(context)
    session = requests.Session()
    session.mount("https://www.ics-com.biz/", adapter)
    _SESSION = session
    return session


def _fetch_page(session: requests.Session, url: str, timeout: int) -> BeautifulSoup | None:
    response = session.get(url, timeout=timeout)
    if response.apparent_encoding:
        response.encoding = response.apparent_encoding
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _collect_list_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if any(pattern in href for pattern in LIST_LINK_PATTERNS) and DETAIL_PATH not in href:
            full_url = urljoin(base_url, href)
            if _same_domain(full_url, base_url):
                urls.add(full_url)
    return sorted(urls)


def _collect_pagination_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "page=" in href or "Page=" in href or "?p=" in href or "&p=" in href:
            full_url = urljoin(base_url, href)
            if _same_domain(full_url, base_url):
                urls.add(full_url)
    return sorted(urls)


def _same_domain(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _find_equipment_table(soup: BeautifulSoup) -> BeautifulSoup | None:
    for table in soup.find_all("table"):
        headers = [clean_text(th.get_text(" ", strip=True)) for th in table.find_all("th")]
        if any("研究設備名称" in header for header in headers):
            return table
    return None


def _extract_records(table: BeautifulSoup, base_url: str) -> list[RawEquipment]:
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [clean_text(th.get_text(" ", strip=True)) for th in rows[0].find_all(["th", "td"])]
    indices = _map_headers(headers)
    records: list[RawEquipment] = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        name = _cell_text(cells, indices.name)
        if not name:
            continue
        equipment_id = _cell_text(cells, indices.equipment_id)
        campus = _cell_text(cells, indices.campus)
        location = _cell_text(cells, indices.location)
        scope = _cell_text(cells, indices.scope)
        detail_url = _extract_detail_url(cells, base_url, indices.detail)
        if not equipment_id:
            equipment_id = _extract_id_from_url(detail_url)

        records.append(
            RawEquipment(
                equipment_id=_format_equipment_id(equipment_id),
                name=name,
                category="研究設備",
                org_name="東京大学",
                address_raw=_join_location(campus, location),
                external_use=_normalize_scope(scope),
                source_url=detail_url or base_url,
            )
        )
    return records


def _map_headers(headers: list[str]) -> ColumnIndex:
    indices = ColumnIndex()
    for idx, header in enumerate(headers):
        if "研究設備ID" in header or header.endswith("ID"):
            indices = indices.__class__(**{**indices.__dict__, "equipment_id": idx})
        elif "研究設備名称" in header or "設備名称" in header:
            indices = indices.__class__(**{**indices.__dict__, "name": idx})
        elif "設置キャンパス" in header:
            indices = indices.__class__(**{**indices.__dict__, "campus": idx})
        elif "設置場所" in header:
            indices = indices.__class__(**{**indices.__dict__, "location": idx})
        elif "対象" in header:
            indices = indices.__class__(**{**indices.__dict__, "scope": idx})
        elif "詳細" in header or "予約" in header:
            indices = indices.__class__(**{**indices.__dict__, "detail": idx})
    return indices


def _cell_text(cells: list[BeautifulSoup], index: int | None) -> str:
    if index is None or index >= len(cells) or index < 0:
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def _extract_detail_url(
    cells: list[BeautifulSoup], base_url: str, preferred_index: int | None
) -> str:
    candidates = []
    if preferred_index is not None and 0 <= preferred_index < len(cells):
        candidates.append(cells[preferred_index])
    candidates.extend(cells)
    for cell in candidates:
        for anchor in cell.find_all("a", href=True):
            href = anchor.get("href", "")
            if DETAIL_PATH in href:
                return urljoin(base_url, href)
    return ""


def _extract_id_from_url(url: str) -> str:
    match = re.search(r"/machine_detail/(\d+)", url or "")
    return match.group(1) if match else ""


def _format_equipment_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return f"UTOKYO-{raw_id}"


def _join_location(campus: str, location: str) -> str:
    campus = campus.strip()
    location = location.strip()
    if campus and location:
        return f"{campus} {location}"
    return campus or location


def _normalize_scope(value: str) -> str:
    if not value:
        return ""
    if "要相談" in value:
        return "要相談"
    if "学外可" in value or "学内外" in value or "学外利用可" in value:
        return "可"
    if "学内限定" in value or "学内専用" in value or "学内のみ" in value or "学外不可" in value:
        return "不可"
    return ""
