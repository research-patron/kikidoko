from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from ..models import RawEquipment
from ..utils import clean_text, normalize_label

HEADER_KEYWORDS = {
    "name": ["機器名", "設備名", "装置名", "機器・施設名", "機器名称", "設備名称", "装置名称", "名称"],
    "category": ["分類", "カテゴリ", "カテゴリー", "種別", "分野", "区分"],
    "location": ["所在地", "設置場所", "設置", "場所", "キャンパス", "所在", "管轄"],
    "contact": ["担当", "連絡先", "問い合わせ", "問合せ", "窓口"],
    "fee": ["料金", "利用料", "費用", "価格", "料金区分"],
    "note": ["備考", "摘要", "その他", "備考等"],
    "id": ["機器番号", "装置番号", "番号", "No", "NO", "ID"],
}


@dataclass(frozen=True)
class TableSource:
    key: str
    org_name: str
    url: str
    org_type: str = ""
    category_hint: str = ""
    external_use: str = ""
    link_patterns: tuple[str, ...] = ()
    required_table_links: tuple[str, ...] = ()


TABLE_SOURCES: list[TableSource] = [
    TableSource(
        key="riken",
        org_name="理化学研究所",
        url="https://www.innovation-riken.jp/riken-facilities/",
        category_hint="研究施設",
    ),
    TableSource(
        key="utokyo",
        org_name="東京大学",
        url="https://www.ics-com.biz/todai_kyouyou/portals/machine/",
        link_patterns=("/portals/machine/",),
        required_table_links=("/portals/machine_detail/",),
    ),
    TableSource(
        key="tsukuba",
        org_name="筑波大学",
        url="https://openfacility.sec.tsukuba.ac.jp/public_eq/front.php?cont=eq_index",
    ),
    TableSource(
        key="tmd",
        org_name="東京医科歯科大学",
        url="https://www.tmd.ac.jp/rcmd/equipment/",
    ),
]

RELAXED_TLS_HOSTS = {"www.ics-com.biz"}
FORCE_APPARENT_ENCODING_HOSTS = {"www.ics-com.biz"}
_DEFAULT_SESSION = requests.Session()
_RELAXED_SESSION: requests.Session | None = None


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


def fetch_table_source(source_key: str, timeout: int, limit: int = 0) -> list[RawEquipment]:
    source = next((item for item in TABLE_SOURCES if item.key == source_key), None)
    if not source:
        raise ValueError(f"Unknown table source: {source_key}")
    return _fetch_source(source, timeout, limit)


def fetch_table_bulk(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    for source in TABLE_SOURCES:
        remaining = 0 if limit == 0 else max(limit - len(records), 0)
        records.extend(_fetch_source(source, timeout, remaining))
        if limit and len(records) >= limit:
            return records
    return records


def _fetch_source(source: TableSource, timeout: int, limit: int) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    seen: set[str] = set()
    queue = [source.url]
    visited: set[str] = set()

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        soup = _fetch_page(url, timeout)
        if not soup:
            continue

        tables = soup.find_all("table")
        for table in tables:
            for record in _extract_records_from_table(table, url, source):
                key = f"{record.org_name}:{record.name}:{record.source_url}"
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
                if limit and len(records) >= limit:
                    return records

        for extra in _collect_links(soup, url, source.link_patterns):
            if extra not in visited:
                queue.append(extra)
        for page in _collect_pagination_links(soup, url):
            if page not in visited:
                queue.append(page)

    return records


def _fetch_page(url: str, timeout: int) -> BeautifulSoup | None:
    session = _get_session(url)
    response = session.get(url, timeout=timeout)
    if urlparse(url).netloc in FORCE_APPARENT_ENCODING_HOSTS and response.apparent_encoding:
        response.encoding = response.apparent_encoding
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _get_session(url: str) -> requests.Session:
    host = urlparse(url).netloc
    if host not in RELAXED_TLS_HOSTS:
        return _DEFAULT_SESSION
    global _RELAXED_SESSION
    if _RELAXED_SESSION is None:
        context = create_urllib3_context()
        # Allow legacy DH parameters on older TLS endpoints (e.g. ics-com.biz).
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        adapter = LegacyTLSAdapter(context)
        session = requests.Session()
        session.mount(f"https://{host}/", adapter)
        _RELAXED_SESSION = session
    return _RELAXED_SESSION

def _collect_links(
    soup: BeautifulSoup, base_url: str, patterns: Iterable[str]
) -> list[str]:
    if not patterns:
        return []
    urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if any(pattern in href for pattern in patterns):
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


def _extract_records_from_table(
    table: BeautifulSoup, base_url: str, source: TableSource
) -> list[RawEquipment]:
    if source.required_table_links and not _table_has_link(table, source.required_table_links):
        return []
    rows = table.find_all("tr")
    if not rows:
        return []

    headers, header_row_index = _detect_headers(rows)
    mapping = _map_headers(headers)
    data_rows = rows[header_row_index + 1 :] if header_row_index is not None else rows

    records: list[RawEquipment] = []
    for row in data_rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        name = _cell_text(cells, mapping.get("name", 0))
        if not name:
            name = _extract_link_text(cells)
        if not name:
            continue
        category = _cell_text(cells, mapping.get("category"))
        location = _cell_text(cells, mapping.get("location"))
        contact = _cell_text(cells, mapping.get("contact"))
        fee = _cell_text(cells, mapping.get("fee"))
        note = _cell_text(cells, mapping.get("note"))
        equipment_id = _cell_text(cells, mapping.get("id"))
        source_url = _extract_link(cells, base_url, mapping.get("name")) or base_url
        if not equipment_id and source.key == "utokyo":
            equipment_id = _extract_id_from_url(source_url)

        conditions_note = _join_notes(contact, note)
        category_value = category or source.category_hint

        records.append(
            RawEquipment(
                equipment_id=_format_equipment_id(source.key, equipment_id),
                name=name,
                category=category_value,
                org_name=source.org_name,
                org_type=source.org_type,
                address_raw=location,
                external_use=source.external_use,
                fee_note=fee,
                conditions_note=conditions_note,
                source_url=source_url,
            )
        )
    return records


def _detect_headers(rows: list[BeautifulSoup]) -> tuple[list[str], int | None]:
    for index, row in enumerate(rows):
        header_cells = row.find_all("th")
        if header_cells:
            return [_cell_text(header_cells, i) for i in range(len(header_cells))], index
    if rows:
        first_cells = rows[0].find_all(["td", "th"])
        labels = [_cell_text(first_cells, i) for i in range(len(first_cells))]
        if _looks_like_header(labels):
            return labels, 0
    return [], None


def _looks_like_header(labels: list[str]) -> bool:
    for label in labels:
        for keywords in HEADER_KEYWORDS.values():
            if any(keyword in label for keyword in keywords):
                return True
    return False


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        normalized = normalize_label(header)
        for key, keywords in HEADER_KEYWORDS.items():
            if key == "name" and ("ID" in normalized or "番号" in normalized):
                continue
            if any(keyword in normalized for keyword in keywords):
                mapping.setdefault(key, index)
    return mapping


def _cell_text(cells: list[BeautifulSoup], index: int | None) -> str:
    if index is None or index >= len(cells) or index < 0:
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def _extract_link(
    cells: list[BeautifulSoup], base_url: str, preferred_index: int | None
) -> str:
    if preferred_index is not None and 0 <= preferred_index < len(cells):
        anchor = cells[preferred_index].find("a", href=True)
        if anchor:
            return urljoin(base_url, anchor["href"])
    for cell in cells:
        anchor = cell.find("a", href=True)
        if anchor:
            return urljoin(base_url, anchor["href"])
    return ""


def _extract_link_text(cells: list[BeautifulSoup]) -> str:
    for cell in cells:
        anchor = cell.find("a")
        if anchor:
            text = clean_text(anchor.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _extract_id_from_url(source_url: str) -> str:
    if not source_url:
        return ""
    match = re.search(r"/machine_detail/(\\d+)", source_url)
    if not match:
        return ""
    return match.group(1)


def _join_notes(*notes: str) -> str:
    cleaned = [note for note in [clean_text(note) for note in notes] if note]
    return " / ".join(cleaned)


def _format_equipment_id(source_key: str, raw_id: str) -> str:
    if not raw_id:
        return ""
    safe_key = "".join(char if char.isalnum() else "-" for char in source_key.upper())
    return f"{safe_key}-{raw_id}"


def _table_has_link(table: BeautifulSoup, patterns: tuple[str, ...]) -> bool:
    for anchor in table.select("a[href]"):
        href = anchor.get("href", "")
        if any(pattern in href for pattern in patterns):
            return True
    return False
