from __future__ import annotations

import hashlib
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "http://ic.ims.ac.jp/"
LIST_URL = urljoin(BASE_URL, "kiki.html")


def fetch_ims_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    default_address = _extract_address(soup)
    records: list[RawEquipment] = []

    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        if not dt:
            continue
        if "syonai" in (dt.get("class") or []):
            continue
        anchor = dt.find("a", href=True)
        if not anchor:
            continue
        href = urljoin(LIST_URL, anchor["href"])
        if "imsonly" in href:
            continue

        name = clean_text(anchor.get_text(" ", strip=True))
        if not name:
            continue

        location = ""
        notes: list[str] = []
        for dd in dl.find_all("dd"):
            text = clean_text(dd.get_text(" ", strip=True))
            if not text:
                continue
            if "設置場所" in text:
                location = _extract_location(text)
            else:
                notes.append(text)

        address_raw = _combine_address(default_address, location)
        equipment_id = _build_equipment_id(href, name)
        conditions_note = " / ".join(notes)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general="研究設備",
                org_name="分子科学研究所 機器センター",
                address_raw=address_raw,
                external_use="可",
                conditions_note=conditions_note,
                source_url=href,
            )
        )

        if limit and len(records) >= limit:
            return records

    return records


def _extract_address(soup: BeautifulSoup) -> str:
    for paragraph in soup.find_all("p"):
        text = clean_text(paragraph.get_text(" ", strip=True))
        if "〒" in text:
            return text
    return ""


def _extract_location(text: str) -> str:
    cleaned = (
        text.replace("［", "")
        .replace("］", "")
        .replace("[", "")
        .replace("]", "")
        .strip()
    )
    if "設置場所" in cleaned:
        cleaned = cleaned.split("設置場所", 1)[-1].lstrip(":：")
    return clean_text(cleaned)


def _combine_address(address: str, location: str) -> str:
    if address and location:
        return f"{address} {location}"
    return address or location


def _build_equipment_id(href: str, name: str) -> str:
    slug = urlparse(href).path.rstrip("/").split("/")[-1]
    if not slug:
        slug = "item"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
    return f"IMS-{slug}-{digest}"
