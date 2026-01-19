from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://whs.nagaokaut.ac.jp/nutaic/equipment.html"
ORG_NAME = "長岡技術科学大学 分析計測センター"
PREFECTURE = "新潟県"


def fetch_nagaoka_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for gallery in soup.select("div.sp-item-gallery"):
        section = _extract_section(gallery)
        for item in gallery.select("li.item-gallery-item"):
            name = _extract_item_name(item)
            if not name:
                continue
            link = item.select_one("a[href]")
            detail_url = urljoin(LIST_URL, link["href"]) if link else ""
            if detail_url.rstrip("/") == LIST_URL.rstrip("/") or detail_url.endswith(
                "/equipment.html"
            ):
                detail_url = ""
            detail = _fetch_detail(detail_url, timeout) if detail_url else {}

            if detail.get("name"):
                name = detail["name"]

            location = detail.get("location")
            address_raw = _build_address(location)
            conditions_note = _build_conditions_note(detail)
            equipment_id = _build_equipment_id(detail_url)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general="分析計測センター",
                    category_detail=section,
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


def _extract_section(gallery: Tag) -> str:
    header = gallery.find_previous(["h3", "h4"])
    if not header:
        return ""
    return clean_text(header.get_text(" ", strip=True))


def _extract_item_name(item: Tag) -> str:
    name_tag = item.select_one("p.item-gallery-title")
    if not name_tag:
        return ""
    return clean_text(name_tag.get_text(" ", strip=True))


def _fetch_detail(url: str, timeout: int) -> dict[str, str]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    name = _extract_detail_name(soup)
    summary = _extract_summary_block(soup)
    features = _extract_features(soup)

    return {
        "name": name,
        "model": summary.get("機種", ""),
        "location": summary.get("設置場所", ""),
        "teachers": summary.get("担当教員", ""),
        "staff": summary.get("担当技術職員", ""),
        "features": features,
    }


def _extract_detail_name(soup: BeautifulSoup) -> str:
    for heading in soup.find_all("h1"):
        text = clean_text(heading.get_text(" ", strip=True))
        if text and text != "メニュー":
            return text
    return ""


def _extract_summary_block(soup: BeautifulSoup) -> dict[str, str]:
    block = soup.select_one("div.sp-part-top.sp-block-container p.paragraph")
    if not block:
        return {}
    lines = [clean_text(line) for line in block.get_text("\n", strip=True).splitlines()]
    summary: dict[str, str] = {}
    for line in lines:
        if "：" not in line:
            continue
        label, value = line.split("：", 1)
        label = clean_text(label)
        value = clean_text(value)
        if not label or not value:
            continue
        summary[label] = value
    return summary


def _extract_features(soup: BeautifulSoup) -> str:
    parts = [clean_text(tag.get_text(" ", strip=True)) for tag in soup.select("b.character")]
    parts = [part for part in parts if part]
    return " / ".join(parts)


def _build_address(location: str) -> str:
    if not location:
        return ORG_NAME
    if ORG_NAME in location:
        return location
    if location.startswith("分析計測センター"):
        location = location.replace("分析計測センター", "", 1).strip()
    return f"{ORG_NAME} {location}".strip()


def _build_conditions_note(detail: dict[str, str]) -> str:
    parts: list[str] = []
    if detail.get("model"):
        parts.append(f"機種: {detail['model']}")
    if detail.get("teachers"):
        parts.append(f"担当教員: {detail['teachers']}")
    if detail.get("staff"):
        parts.append(f"担当技術職員: {detail['staff']}")
    if detail.get("features"):
        parts.append(f"特徴: {detail['features']}")
    return " / ".join(parts)


def _build_equipment_id(source_url: str) -> str:
    if not source_url:
        return ""
    slug = urlparse(source_url).path.rsplit("/", 1)[-1].replace(".html", "")
    if not slug:
        return ""
    return f"NAGAOKA-{slug}"
