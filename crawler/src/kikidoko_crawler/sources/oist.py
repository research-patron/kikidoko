from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

CATEGORY_URLS = (
    "https://groups.oist.jp/ias/research-equipment-gallery-mass-spectrometry-0",
    "https://groups.oist.jp/ias/research-equipment-gallery-flow-cytometry-0",
    "https://groups.oist.jp/ias/research-equipment-gallery-nmr-spectroscopy-0",
    "https://groups.oist.jp/ias/other-analytical-instrument",
    "https://groups.oist.jp/ias/bio-sample-preparation-tool",
)
ORG_NAME = "沖縄科学技術大学院大学 Instrumental Analysis Section"
PREFECTURE = "沖縄県"
EXTERNAL_USE = "要相談"
REQUEST_DELAY_SECONDS = 10


def fetch_oist_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    name_seen: set[str] = set()
    for index, url in enumerate(CATEGORY_URLS):
        soup = _fetch_page(url, timeout)
        category = _extract_category(soup)
        contact_note = _extract_contact_note(soup)

        for card in _iter_cards(soup):
            name = _extract_name(card)
            if not name:
                continue
            maker, model, features = _extract_details(card)
            display_name = _disambiguate_name(name, model, maker, name_seen)
            conditions_note = _build_conditions_note(
                maker=maker,
                model=model,
                features=features,
                contact_note=contact_note,
            )
            records.append(
                RawEquipment(
                    name=display_name,
                    category_general=category,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    external_use=EXTERNAL_USE,
                    conditions_note=conditions_note,
                    source_url=url,
                )
            )
            if limit and len(records) >= limit:
                return records

        if REQUEST_DELAY_SECONDS and index < len(CATEGORY_URLS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    return records


def _fetch_page(url: str, timeout: int) -> BeautifulSoup:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def _extract_category(soup: BeautifulSoup) -> str:
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    return title.split("|", 1)[0].strip()


def _extract_contact_note(soup: BeautifulSoup) -> str:
    body = soup.select_one(".field-name-body")
    if not body:
        return ""
    header = body.select_one(".row.two-col-left")
    if not header:
        return ""
    text = clean_text(header.get_text(" ", strip=True))
    email_match = re.search(r"[\w.+-]+\*[\w.-]+\.[A-Za-z]{2,}", text)
    if email_match:
        email = email_match.group(0).replace("*", "@")
        return f"連絡先: {email}"
    return ""


def _iter_cards(soup: BeautifulSoup) -> list[BeautifulSoup]:
    body = soup.select_one(".field-name-body")
    if not body:
        return []
    cards = []
    for card in body.select(".col-md-4, .col-md-3"):
        if card.find("strong"):
            cards.append(card)
    return cards


def _extract_name(card: BeautifulSoup) -> str:
    strong = card.find("strong")
    if not strong:
        return ""
    return clean_text(strong.get_text(" ", strip=True))


def _extract_details(card: BeautifulSoup) -> tuple[str, str, str]:
    lines = []
    for node in card.find_all(["p", "li"]):
        text = clean_text(node.get_text(" ", strip=True))
        if text:
            lines.append(text)
    maker = _find_labeled_value(lines, "Maker")
    model = _find_labeled_value(lines, "Model")
    features = _find_labeled_value(lines, "Features")
    return maker, model, features


def _find_labeled_value(lines: list[str], label: str) -> str:
    prefix = f"{label}:"
    for line in lines:
        if line.startswith(prefix):
            return clean_text(line[len(prefix) :])
    return ""


def _build_conditions_note(
    maker: str, model: str, features: str, contact_note: str
) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if features:
        parts.append(f"特徴: {features}")
    if contact_note:
        parts.append(contact_note)
    return " / ".join(parts)


def _disambiguate_name(
    name: str, model: str, maker: str, seen: set[str]
) -> str:
    if name not in seen:
        seen.add(name)
        return name
    suffix = clean_text(model) or clean_text(maker)
    if suffix and suffix not in name:
        updated = f"{name} ({suffix})"
    else:
        updated = name
    seen.add(updated)
    return updated
