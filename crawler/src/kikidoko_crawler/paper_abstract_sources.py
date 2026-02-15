from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

import requests

ELSEVIER_ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi/{doi}"
OPENALEX_WORKS_URL = "https://api.openalex.org/works/https://doi.org/{doi}"
CROSSREF_WORKS_URL = "https://api.crossref.org/works/{doi}"

ABSTRACT_MAX_LENGTH = 6000
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DOI_PREFIX_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def clean_abstract_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > ABSTRACT_MAX_LENGTH:
        text = text[: ABSTRACT_MAX_LENGTH - 1].rstrip() + "…"
    return text


def normalize_doi(value: str) -> str:
    doi = str(value or "").strip()
    doi = _DOI_PREFIX_RE.sub("", doi)
    return doi.lower().strip()


def _join_text_chunks(chunks: list[str]) -> str:
    if not chunks:
        return ""
    joined = " ".join(chunk for chunk in chunks if chunk)
    return clean_abstract_text(joined)


def _flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_abstract_text(value)
    if isinstance(value, list):
        return _join_text_chunks([_flatten_value(item) for item in value])
    if isinstance(value, dict):
        preferred_keys = ["$"]
        for key in preferred_keys:
            text = _flatten_value(value.get(key))
            if text:
                return text
        return _join_text_chunks([_flatten_value(item) for item in value.values()])
    return clean_abstract_text(str(value))


def _deep_get(payload: dict[str, Any], path: list[str]) -> Any:
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


def _collect_values_for_keys(node: Any, keys: set[str], out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in keys:
                text = _flatten_value(value)
                if text:
                    out.append(text)
            _collect_values_for_keys(value, keys, out)
        return
    if isinstance(node, list):
        for item in node:
            _collect_values_for_keys(item, keys, out)


def _extract_elsevier_abstract(payload: dict[str, Any]) -> str:
    roots: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        roots.append(payload)
        response_root = payload.get("abstracts-retrieval-response")
        if isinstance(response_root, dict):
            roots.append(response_root)
        fulltext_root = payload.get("full-text-retrieval-response")
        if isinstance(fulltext_root, dict):
            roots.append(fulltext_root)

    candidate_paths = [
        ["coredata", "dc:description"],
        ["coredata", "description"],
        ["item", "bibrecord", "head", "abstracts"],
        ["item", "bibrecord", "head", "abstract"],
        ["head", "abstracts"],
    ]

    for root in roots:
        for path in candidate_paths:
            value = _deep_get(root, path)
            text = _flatten_value(value)
            if text:
                return text

    key_hits: list[str] = []
    interesting_keys = {
        "dc:description",
        "description",
        "abstract",
        "abstracts",
        "ce:abstract",
        "ce:para",
        "ce:simple-para",
    }
    for root in roots:
        _collect_values_for_keys(root, interesting_keys, key_hits)
    if key_hits:
        return _join_text_chunks(key_hits)
    return ""


def _parse_openalex_inverted_index(index: Any) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    position_map: dict[int, str] = {}
    for token, positions in index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and pos not in position_map:
                position_map[pos] = str(token)
    if not position_map:
        return ""
    ordered = [position_map[pos] for pos in sorted(position_map)]
    return clean_abstract_text(" ".join(ordered))


def build_fallback_abstract(paper: dict[str, Any]) -> str:
    title = clean_abstract_text(str(paper.get("title", "")))
    source = clean_abstract_text(str(paper.get("source", "")))
    year = clean_abstract_text(str(paper.get("year", "")))
    genre = clean_abstract_text(str(paper.get("genre", "")))

    if title:
        parts = [f"要旨未取得のため、論文題名「{title}」を基にした暫定要約です。"]
    else:
        parts = ["要旨未取得のため、書誌情報を基にした暫定要約です。"]
    details: list[str] = []
    if source:
        details.append(f"掲載誌: {source}")
    if year:
        details.append(f"出版年: {year}")
    if genre:
        details.append(f"分野: {genre}")
    if details:
        parts.append(" ".join(details))
    parts.append("具体的な手法・条件は「別タブで開く」から原文をご確認ください。")
    return clean_abstract_text(" ".join(parts))


def fetch_elsevier_abstract(
    session: requests.Session,
    doi: str,
    api_key: str,
    timeout: float,
) -> tuple[str, str]:
    if not api_key:
        return "", "elsevier_api_key_missing"
    if not doi:
        return "", "doi_missing"
    url = ELSEVIER_ABSTRACT_URL.format(doi=quote(doi, safe=""))
    try:
        response = session.get(
            url,
            headers={"Accept": "application/json", "X-ELS-APIKey": api_key},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        return "", f"elsevier_request_error:{exc}"
    if response.status_code in (401, 403):
        return "", f"elsevier_auth_error:{response.status_code}"
    if response.status_code == 404:
        return "", "elsevier_not_found"
    if response.status_code == 429:
        return "", "elsevier_rate_limited"
    if not response.ok:
        return "", f"elsevier_http_error:{response.status_code}"
    try:
        payload = response.json()
    except ValueError as exc:
        return "", f"elsevier_json_error:{exc}"
    text = _extract_elsevier_abstract(payload if isinstance(payload, dict) else {})
    if text:
        return text, ""
    return "", "elsevier_abstract_missing"


def fetch_openalex_abstract(
    session: requests.Session,
    doi: str,
    timeout: float,
) -> tuple[str, str]:
    if not doi:
        return "", "doi_missing"
    url = OPENALEX_WORKS_URL.format(doi=quote(doi, safe=""))
    try:
        response = session.get(url, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        return "", f"openalex_request_error:{exc}"
    if response.status_code == 404:
        return "", "openalex_not_found"
    if response.status_code == 429:
        return "", "openalex_rate_limited"
    if not response.ok:
        return "", f"openalex_http_error:{response.status_code}"
    try:
        payload = response.json()
    except ValueError as exc:
        return "", f"openalex_json_error:{exc}"
    if not isinstance(payload, dict):
        return "", "openalex_payload_invalid"
    text = _parse_openalex_inverted_index(payload.get("abstract_inverted_index"))
    if text:
        return text, ""
    return "", "openalex_abstract_missing"


def fetch_crossref_abstract(
    session: requests.Session,
    doi: str,
    timeout: float,
) -> tuple[str, str]:
    if not doi:
        return "", "doi_missing"
    url = CROSSREF_WORKS_URL.format(doi=quote(doi, safe=""))
    try:
        response = session.get(url, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        return "", f"crossref_request_error:{exc}"
    if response.status_code == 404:
        return "", "crossref_not_found"
    if response.status_code == 429:
        return "", "crossref_rate_limited"
    if not response.ok:
        return "", f"crossref_http_error:{response.status_code}"
    try:
        payload = response.json()
    except ValueError as exc:
        return "", f"crossref_json_error:{exc}"
    if not isinstance(payload, dict):
        return "", "crossref_payload_invalid"
    message = payload.get("message")
    if not isinstance(message, dict):
        return "", "crossref_message_missing"
    text = clean_abstract_text(str(message.get("abstract", "") or ""))
    if text:
        return text, ""
    return "", "crossref_abstract_missing"


def resolve_abstract_for_paper(
    session: requests.Session,
    paper: dict[str, Any],
    elsevier_api_key: str,
    timeout: float,
) -> dict[str, Any]:
    doi = normalize_doi(str(paper.get("doi", "")))
    errors: list[str] = []

    abstract, error = fetch_elsevier_abstract(session, doi, elsevier_api_key, timeout)
    if abstract:
        return {"abstract": abstract, "source": "elsevier", "status": "ready", "error": ""}
    if error:
        errors.append(error)

    abstract, error = fetch_openalex_abstract(session, doi, timeout)
    if abstract:
        return {"abstract": abstract, "source": "openalex", "status": "ready", "error": ""}
    if error:
        errors.append(error)

    abstract, error = fetch_crossref_abstract(session, doi, timeout)
    if abstract:
        return {"abstract": abstract, "source": "crossref", "status": "ready", "error": ""}
    if error:
        errors.append(error)

    fallback = build_fallback_abstract(paper)
    if fallback:
        return {
            "abstract": fallback,
            "source": "fallback",
            "status": "fallback",
            "error": " | ".join(errors),
        }

    return {"abstract": "", "source": "missing", "status": "missing", "error": " | ".join(errors)}
