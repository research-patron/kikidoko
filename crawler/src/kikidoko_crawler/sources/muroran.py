from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://u.muroran-it.ac.jp/kiban-kiki/list/"
ORG_NAME = "室蘭工業大学 研究基盤設備共用センター"
PREFECTURE = "北海道"


def fetch_muroran_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for block in soup.select("div.parts_thumblink"):
        name = _extract_title(block)
        if not name:
            continue
        category = _extract_category(block)
        detail_url = _extract_detail_url(block)
        detail = _fetch_detail(detail_url, timeout) if detail_url else {}

        if detail.get("name"):
            name = detail["name"]

        location = detail.get("location") or _extract_location(block)
        address_raw = _build_address(location)
        conditions_note = _build_conditions_note(detail)
        equipment_id = _build_equipment_id(detail_url)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=category,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use="要相談",
                conditions_note=conditions_note,
                source_url=detail_url or LIST_URL,
            )
        )

        if limit and len(records) >= limit:
            return records

    return records


def _extract_title(block: Tag) -> str:
    title_tag = block.select_one("div.parts_thumblink_title")
    if not title_tag:
        return ""
    return clean_text(title_tag.get_text(" ", strip=True))


def _extract_category(block: Tag) -> str:
    header = block.find_previous("h2")
    if not header:
        return ""
    return clean_text(header.get_text(" ", strip=True))


def _extract_detail_url(block: Tag) -> str:
    anchor = block.find("a", href=True)
    if not anchor:
        return ""
    return urljoin(LIST_URL, anchor["href"])


def _extract_location(block: Tag) -> str:
    text_tag = block.select_one("div.parts_thumblink_text")
    if not text_tag:
        return ""
    text = clean_text(text_tag.get_text(" ", strip=True))
    match = re.search(r"設置場所[:：]\\s*(.+)", text)
    if not match:
        return ""
    location = match.group(1)
    if "管理者" in location:
        location = location.split("管理者", 1)[0]
    return clean_text(location)


def _fetch_detail(url: str, timeout: int) -> dict[str, str]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    name = _extract_detail_name(soup)
    manager, manager_ext, contact, contact_ext = _extract_contacts(soup)
    qualification = _extract_section_text(soup, "利用者資格")
    comment = _extract_section_text(soup, "コメント")
    location = _extract_access_location(soup)

    return {
        "name": name,
        "manager": manager,
        "manager_ext": manager_ext,
        "contact": contact,
        "contact_ext": contact_ext,
        "qualification": qualification,
        "comment": comment,
        "location": location,
    }


def _extract_detail_name(soup: BeautifulSoup) -> str:
    for heading in soup.find_all("h1"):
        text = clean_text(heading.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _extract_contacts(soup: BeautifulSoup) -> tuple[str, str, str, str]:
    block = soup.select_one("div.wp-block-columns")
    if not block:
        return "", "", "", ""
    lines = [
        clean_text(line)
        for line in block.get_text("\n", strip=True).splitlines()
        if clean_text(line)
    ]
    manager = ""
    manager_ext = ""
    contact = ""
    contact_ext = ""
    current = ""

    for line in lines:
        if "管理者" in line:
            current = "manager"
            continue
        if "利用者申込先" in line:
            current = "contact"
            continue

        name, ext = _split_extension(line)
        if current == "manager":
            manager = name or manager
            manager_ext = ext or manager_ext
        elif current == "contact":
            contact = name or contact
            contact_ext = ext or contact_ext

    return manager, manager_ext, contact, contact_ext


def _split_extension(text: str) -> tuple[str, str]:
    if "内線" not in text:
        return text, ""
    parts = re.split(r"内線[:：]", text, maxsplit=1)
    name = clean_text(parts[0]) if parts else ""
    ext = clean_text(parts[1]) if len(parts) > 1 else ""
    return name, ext


def _extract_section_text(soup: BeautifulSoup, heading: str) -> str:
    header = soup.find(lambda tag: tag.name in {"h2", "h3"} and heading in tag.get_text())
    if not header:
        return ""
    parts: list[str] = []
    for sibling in header.find_next_siblings():
        if sibling.name in {"h2", "h3"}:
            break
        text = clean_text(sibling.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return " ".join(parts)


def _extract_access_location(soup: BeautifulSoup) -> str:
    header = soup.find(lambda tag: tag.name == "h2" and "アクセス" in tag.get_text())
    if not header:
        return ""
    location = header.find_next("h3")
    if not location:
        return ""
    return clean_text(location.get_text(" ", strip=True))


def _build_address(location: str) -> str:
    if location:
        return f"{ORG_NAME} {location}"
    return ORG_NAME


def _build_conditions_note(detail: dict[str, str]) -> str:
    parts: list[str] = []
    if detail.get("manager"):
        parts.append(f"管理者: {detail['manager']}")
    if detail.get("manager_ext"):
        parts.append(f"管理者内線: {detail['manager_ext']}")
    if detail.get("contact"):
        parts.append(f"利用者申込先: {detail['contact']}")
    if detail.get("contact_ext"):
        parts.append(f"利用者申込先内線: {detail['contact_ext']}")
    if detail.get("qualification"):
        parts.append(f"利用者資格: {detail['qualification']}")
    if detail.get("comment"):
        parts.append(detail["comment"])
    return " / ".join(parts)


def _build_equipment_id(source_url: str) -> str:
    if not source_url:
        return ""
    slug = urlparse(source_url).path.rstrip("/").rsplit("/", 1)[-1]
    if not slug:
        return ""
    return f"MURORAN-{slug}"
