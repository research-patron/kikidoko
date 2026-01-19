from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.erec.kumamoto-u.ac.jp/list/index.html"
ORG_NAME = "熊本大学工学部附属工学研究機器センター"
PREFECTURE = "熊本県"

DATA_LABELS = {
    "機器室名": "room",
    "内線": "extension",
    "管理責任者": "manager",
    "E-Mail": "email",
}


def fetch_kumamoto_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    detail_map = _build_detail_map(soup, timeout)
    records: list[RawEquipment] = []

    for area in soup.find_all(id="listArea"):
        section_title = _extract_section_title(area)
        for item in area.select("div.equipName2"):
            name = _extract_name(item)
            if not name:
                continue

            detail_href = _select_detail_link(item)
            source_url = urljoin(LIST_URL, detail_href) if detail_href else LIST_URL
            details = detail_map.get(_detail_key(source_url), {})
            if details.get("name"):
                name = details["name"]

            equipment_id = _build_equipment_id(source_url)
            address_raw = _build_address(details.get("room", ""), section_title)
            conditions_note = _build_conditions_note(details)
            category_general = section_title or details.get("room", "")

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=category_general,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=address_raw,
                    external_use="要相談",
                    conditions_note=conditions_note,
                    source_url=source_url,
                )
            )

            if limit and len(records) >= limit:
                return records

    return records


def _extract_section_title(area: Tag) -> str:
    header = area.find_previous("h3")
    if not header:
        return ""
    img = header.find("img", alt=True)
    if img and img.get("alt"):
        return clean_text(img["alt"])
    return clean_text(header.get_text(" ", strip=True))


def _extract_name(item: Tag) -> str:
    name_tag = item.select_one("p.left")
    if not name_tag:
        return ""
    return clean_text(name_tag.get_text(" ", strip=True))


def _select_detail_link(item: Tag) -> str:
    for anchor in item.select("a[href]"):
        href = anchor.get("href", "")
        if ".html" in href and "list" in href and "oic.kumamoto-u.ac.jp" not in href:
            return href
    anchor = item.select_one("a[href]")
    return anchor.get("href", "") if anchor else ""


def _build_detail_map(list_soup: BeautifulSoup, timeout: int) -> dict[str, dict[str, str]]:
    detail_urls: set[str] = set()
    base_netloc = urlparse(LIST_URL).netloc
    for anchor in list_soup.select("div#listArea a[href]"):
        href = anchor.get("href", "")
        full_url = urljoin(LIST_URL, href)
        parsed = urlparse(full_url)
        if parsed.netloc != base_netloc:
            continue
        if not parsed.path.endswith(".html"):
            continue
        detail_urls.add(parsed.scheme + "://" + parsed.netloc + parsed.path)

    detail_map: dict[str, dict[str, str]] = {}
    for url in sorted(detail_urls):
        detail_map.update(_parse_detail_page(url, timeout))
    return detail_map


def _parse_detail_page(url: str, timeout: int) -> dict[str, dict[str, str]]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    page_key = urlparse(url).path
    details: dict[str, dict[str, str]] = {}
    for anchor in soup.find_all("a", attrs={"name": True}):
        anchor_name = clean_text(anchor.get("name", ""))
        if not anchor_name:
            continue
        title = anchor.find_next("h4", class_="equipTitle")
        if not title:
            continue
        detail = title.find_next_sibling("div", class_="equipDetail")
        if not detail:
            continue
        description = _extract_description(detail)
        data_fields = _extract_data_fields(detail)
        details[f"{page_key}#{anchor_name}"] = {
            "name": clean_text(title.get_text(" ", strip=True)),
            "description": description,
            **data_fields,
        }
    return details


def _extract_description(detail: Tag) -> str:
    desc = detail.select_one("p.cmt")
    if not desc:
        return ""
    return clean_text(desc.get_text(" ", strip=True))


def _extract_data_fields(detail: Tag) -> dict[str, str]:
    raw_fields: dict[str, str] = {}
    for data_line in detail.select("p.data"):
        raw_fields.update(_parse_data_line(data_line))

    fields: dict[str, str] = {}
    for label, value in raw_fields.items():
        key = DATA_LABELS.get(label)
        if key and value:
            fields[key] = value
    return fields


def _parse_data_line(tag: Tag) -> dict[str, str]:
    data: dict[str, str] = {}
    current_label = ""
    for child in tag.children:
        if isinstance(child, Tag) and child.name == "img":
            label = _normalize_label(child.get("alt", ""))
            current_label = label
            continue
        if isinstance(child, NavigableString):
            text = clean_text(str(child))
            if not text or not current_label:
                continue
            data[current_label] = _merge_value(data.get(current_label, ""), text)
    return data


def _normalize_label(label: str) -> str:
    return clean_text(label).replace("：", "").replace(":", "")


def _merge_value(existing: str, new: str) -> str:
    if not existing:
        return new
    if new in existing:
        return existing
    return f"{existing} {new}"


def _build_equipment_id(source_url: str) -> str:
    parsed = urlparse(source_url)
    if not parsed.path:
        return ""
    slug = parsed.path.rsplit("/", 1)[-1].replace(".html", "")
    if parsed.fragment:
        slug = f"{slug}-{parsed.fragment}"
    if not slug:
        return ""
    return f"KUMAMOTO-{slug}"


def _detail_key(source_url: str) -> str:
    parsed = urlparse(source_url)
    return f"{parsed.path}#{parsed.fragment}".strip("#")


def _build_address(room: str, section: str) -> str:
    detail = room or section
    if detail:
        return f"{ORG_NAME} {detail}"
    return ORG_NAME


def _build_conditions_note(details: dict[str, str]) -> str:
    parts: list[str] = []
    if details.get("description"):
        parts.append(details["description"])
    if details.get("extension"):
        parts.append(f"内線: {details['extension']}")
    if details.get("manager"):
        parts.append(f"管理責任者: {details['manager']}")
    if details.get("email"):
        parts.append(f"E-Mail: {details['email']}")
    return " / ".join(parts)
