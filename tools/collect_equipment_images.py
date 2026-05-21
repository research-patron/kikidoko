#!/usr/bin/env python3
"""Collect equipment images from source pages and attach image_v1 metadata."""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import gzip
import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


USER_AGENT = (
    "Mozilla/5.0 (compatible; KikidokoImageCollector/1.0; "
    "+https://kikidoko.org/)"
)

BAD_IMAGE_TERMS = {
    "arrow",
    "avatar",
    "background",
    "badge",
    "banner",
    "bg",
    "btn",
    "button",
    "common",
    "dummy",
    "facebook",
    "favicon",
    "footer",
    "header",
    "icon",
    "instagram",
    "line",
    "loading",
    "logo",
    "map",
    "menu",
    "nav",
    "navi",
    "noimage",
    "no-image",
    "placeholder",
    "qr",
    "sns",
    "sprite",
    "spinner",
    "twitter",
}

GOOD_IMAGE_TERMS = {
    "apparatus",
    "device",
    "eq",
    "equipment",
    "image",
    "img",
    "instrument",
    "machine",
    "photo",
    "picture",
    "upload",
}

REFERENCE_SOURCE_TYPES = {
    "manufacturer_official",
    "company_official",
    "institution_official",
    "wikimedia",
}

APPROVED_REVIEW_VALUES = {
    "approved",
    "clear",
    "ok",
    "pass",
    "passed",
    "目視確認済み",
    "承認",
}

MIN_REFERENCE_NAME_MATCH_SCORE = 0.9

MODEL_TOKEN_RE = re.compile(
    r"[A-Za-z]{2,}[-_A-Za-z0-9]*|\d{3,}|[\u3040-\u30ff\u3400-\u9fff]{2,}"
)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def write_snapshot(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent), suffix=".tmp") as tmp:
        tmp_path = Path(tmp.name)
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def item_key(item: Dict[str, Any], index: int) -> str:
    for key in ("equipment_id", "doc_id"):
        value = normalize_text(item.get(key))
        if value:
            return value
    return f"item-{index:06d}"


def detail_key(item: Dict[str, Any], equipment_id: str) -> str:
    doc_id = normalize_text(item.get("doc_id"))
    return doc_id or equipment_id


def shard_key(equipment_id: str, shard_count: int) -> str:
    digest = hashlib.md5(equipment_id.encode("utf-8")).digest()
    return f"{digest[0] % shard_count:02x}"


def safe_file_stem(value: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z_.-]+", "_", value).strip("._-")
    return stem or "equipment"


def page_fetch_url(source_url: str) -> str:
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.netloc.lower() == "eqnet.jp" and parsed.fragment:
        match = re.search(r"/public/equipment/(\d+)", parsed.fragment)
        if match:
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, f"/public/equipment/{match.group(1)}", "", ""))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


def decode_html(data: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type or "", re.I)
    encodings = []
    if charset_match:
        encodings.append(charset_match.group(1))
    encodings.extend(["utf-8", "cp932", "shift_jis", "euc_jp", "latin-1"])
    seen = set()
    for encoding in encodings:
        if encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def fetch_bytes(
    url: str,
    timeout: float,
    max_bytes: int,
    ssl_context: Optional[ssl.SSLContext],
) -> Tuple[bytes, str, str]:
    req = urllib.request.Request(request_safe_url(url), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as res:
        final_url = res.geturl()
        content_type = normalize_text(res.headers.get("content-type"))
        length = normalize_text(res.headers.get("content-length"))
        if length and length.isdigit() and int(length) > max_bytes:
            raise ValueError(f"response too large: {length} bytes")
        data = res.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"response too large: over {max_bytes} bytes")
    return data, content_type, final_url


def request_safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    if parts.username:
        userinfo = urllib.parse.quote(parts.username, safe="")
        if parts.password:
            userinfo += ":" + urllib.parse.quote(parts.password, safe="")
        host = f"{userinfo}@{host}"
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/%:@")
    query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="=&?/%:@,+;")
    fragment = urllib.parse.quote(urllib.parse.unquote(parts.fragment), safe="/%:@")
    return urllib.parse.urlunsplit((parts.scheme, host, path, query, fragment))


def parse_srcset(value: str) -> List[str]:
    candidates: List[Tuple[float, str]] = []
    for raw in value.split(","):
        part = raw.strip()
        if not part:
            continue
        bits = part.split()
        if not bits:
            continue
        score = 1.0
        if len(bits) >= 2:
            descriptor = bits[1].strip().lower()
            try:
                if descriptor.endswith("w"):
                    score = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    score = float(descriptor[:-1]) * 1000
            except ValueError:
                score = 1.0
        candidates.append((score, bits[0]))
    return [url for _, url in sorted(candidates, reverse=True)]


@dataclass
class ImageCandidate:
    url: str
    role: str
    attrs: Dict[str, str] = field(default_factory=dict)
    score: int = 0


class CandidateHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: List[ImageCandidate] = []
        self._picture_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_name = tag.lower()
        attr_map = {str(k).lower(): normalize_text(v) for k, v in attrs}
        if tag_name == "picture":
            self._picture_depth += 1
            return
        if tag_name == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                self.add_candidate(attr_map.get("content"), "meta", attr_map)
            return
        if tag_name == "link":
            rel = attr_map.get("rel", "").lower()
            if "image_src" in rel or "preload" in rel and attr_map.get("as") == "image":
                self.add_candidate(attr_map.get("href"), "link", attr_map)
            return
        if tag_name == "source":
            for src in parse_srcset(attr_map.get("srcset", "")):
                self.add_candidate(src, "picture" if self._picture_depth else "source", attr_map)
            return
        if tag_name == "img":
            for key in (
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-echo",
                "data-url",
            ):
                self.add_candidate(attr_map.get(key), "img", attr_map)
            for src in parse_srcset(attr_map.get("srcset", "")):
                self.add_candidate(src, "img", attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "picture" and self._picture_depth:
            self._picture_depth -= 1

    def add_candidate(self, raw_url: Optional[str], role: str, attrs: Dict[str, str]) -> None:
        raw = normalize_text(raw_url)
        if not raw or raw.startswith(("data:", "javascript:", "mailto:")):
            return
        url = urllib.parse.urljoin(self.base_url, raw)
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return
        self.candidates.append(ImageCandidate(url=url, role=role, attrs=dict(attrs)))


def text_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for match in MODEL_TOKEN_RE.findall(value):
            token = match.lower()
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def candidate_text(candidate: ImageCandidate) -> str:
    attrs = candidate.attrs
    return " ".join(
        [
            candidate.url,
            attrs.get("alt", ""),
            attrs.get("title", ""),
            attrs.get("aria-label", ""),
            attrs.get("class", ""),
            attrs.get("id", ""),
        ]
    )


def score_candidate(candidate: ImageCandidate, item: Dict[str, Any]) -> int:
    text = candidate_text(candidate)
    lower = text.lower()
    score = 0
    if candidate.role == "meta":
        score += 8
    elif candidate.role == "picture":
        score += 6
    elif candidate.role == "img":
        score += 4
    elif candidate.role == "link":
        score += 3

    path = urllib.parse.urlsplit(candidate.url).path.lower()
    ext = Path(path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        score += 4
    if ext in {".svg", ".ico"}:
        score -= 40
    if any(term in lower for term in BAD_IMAGE_TERMS):
        score -= 30
    if any(term in lower for term in GOOD_IMAGE_TERMS):
        score += 3

    width = parse_int(candidate.attrs.get("width"))
    height = parse_int(candidate.attrs.get("height"))
    if width and height:
        if width < 90 or height < 70:
            score -= 25
        elif width >= 300 and height >= 180:
            score += 6
        elif width >= 120 and height >= 90:
            score += 3

    item_tokens = text_tokens(
        normalize_text(item.get("name")),
        normalize_text(item.get("category_detail")),
        normalize_text(item.get("category_general")),
    )
    candidate_tokens = text_tokens(lower)
    matched = item_tokens & candidate_tokens
    score += min(12, len(matched) * 4)

    return score


def parse_int(value: Any) -> Optional[int]:
    text = normalize_text(value)
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def unique_scored_candidates(
    candidates: Iterable[ImageCandidate],
    item: Dict[str, Any],
    min_score: int,
) -> List[ImageCandidate]:
    by_url: Dict[str, ImageCandidate] = {}
    for candidate in candidates:
        score = score_candidate(candidate, item)
        candidate.score = score
        if score < min_score:
            continue
        current = by_url.get(candidate.url)
        if current is None or score > current.score:
            by_url[candidate.url] = candidate
    return sorted(by_url.values(), key=lambda c: c.score, reverse=True)


def image_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return webp_size(data)
    if data.startswith(b"\xff\xd8"):
        return jpeg_size(data)
    return None, None


def jpeg_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2:
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if index + 7 <= len(data):
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return width, height
            break
        index += length
    return None, None


def webp_size(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    if len(data) < 30:
        return None, None
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        if data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    return None, None


def content_type_for(url: str, header_value: str) -> str:
    content_type = normalize_text(header_value).split(";", 1)[0].lower()
    if content_type:
        return content_type
    guessed = mimetypes.guess_type(urllib.parse.urlsplit(url).path)[0]
    return guessed or ""


def is_candidate_image(
    data: bytes,
    content_type: str,
    min_bytes: int,
    min_width: int,
    min_height: int,
) -> Tuple[bool, Optional[int], Optional[int], str]:
    if len(data) < min_bytes:
        return False, None, None, "image_too_small_bytes"
    kind = content_type.split(";", 1)[0].lower()
    if kind in {"image/svg+xml", "image/x-icon"}:
        return False, None, None, "unsupported_image_type"
    if kind and not kind.startswith("image/"):
        return False, None, None, "not_image_content_type"
    width, height = image_size(data)
    if width is None or height is None:
        return False, None, None, "unknown_image_dimensions"
    if width < min_width or height < min_height:
        return False, width, height, "image_too_small_dimensions"
    return True, width, height, ""


def optimize_to_jpeg(input_path: Path, output_path: Path, timeout: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sips = shutil.which("sips")
    if sips:
        try:
            result = subprocess.run(
                [
                    sips,
                    "-s",
                    "format",
                    "jpeg",
                    "-s",
                    "formatOptions",
                    "75",
                    "-Z",
                    "900",
                    str(input_path),
                    "--out",
                    str(output_path),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=max(2.0, timeout),
            )
        except subprocess.TimeoutExpired:
            result = None
        if result and result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return
    data = input_path.read_bytes()
    if data.startswith(b"\xff\xd8"):
        shutil.copyfile(input_path, output_path)
        return
    raise RuntimeError("sips conversion failed and source is not JPEG")


def download_and_store_image(
    candidate_url: str,
    output_path: Path,
    timeout: float,
    max_bytes: int,
    min_bytes: int,
    min_width: int,
    min_height: int,
    ssl_context: Optional[ssl.SSLContext],
) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        data, content_type_header, final_url = fetch_bytes(candidate_url, timeout, max_bytes, ssl_context)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return None, f"download_failed:{exc}"

    content_type = content_type_for(final_url, content_type_header)
    ok, width, height, reason = is_candidate_image(data, content_type, min_bytes, min_width, min_height)
    if not ok:
        return None, reason

    suffix = mimetypes.guess_extension(content_type) or Path(urllib.parse.urlsplit(final_url).path).suffix
    suffix = suffix if suffix and len(suffix) <= 8 else ".img"
    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        optimize_to_jpeg(tmp_path, output_path, timeout)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return None, f"optimize_failed:{exc}"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    final_data = output_path.read_bytes()
    final_width, final_height = image_size(final_data)
    return (
        {
            "original_url": final_url,
            "content_type": "image/jpeg",
            "width": final_width or width,
            "height": final_height or height,
            "sha256": hashlib.sha256(final_data).hexdigest(),
        },
        "",
    )


def load_reference_map(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return {
                normalize_text(item.get("key")): item
                for item in data["items"]
                if isinstance(item, dict) and normalize_text(item.get("key"))
            }
        return {normalize_text(k): v for k, v in data.items() if isinstance(v, dict)}
    if isinstance(data, list):
        return {
            normalize_text(item.get("key")): item
            for item in data
            if isinstance(item, dict) and normalize_text(item.get("key"))
        }
    return {}


def reference_override_for(item: Dict[str, Any], equipment_id: str, refs: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    keys = [
        normalize_text(item.get("doc_id")),
        equipment_id,
        normalize_text(item.get("name")),
    ]
    for key in keys:
        if key and key in refs:
            return refs[key]
    return None


def normalize_for_name_match(value: Any) -> str:
    text = unicodedata.normalize("NFKC", normalize_text(value)).lower()
    text = re.sub(r"[\s\"'“”‘’`´＂＇「」『』（）()\[\]【】<>＜＞:：/／,，、。・･\-‐‑‒–—ー_]+", "", text)
    return text


def reference_name_match_score(expected: Any, matched: Any) -> float:
    left = normalize_for_name_match(expected)
    right = normalize_for_name_match(matched)
    if not left or not right:
        return 0.0
    sequence_score = difflib.SequenceMatcher(None, left, right).ratio()
    containment_score = 0.0
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if shorter and shorter in longer:
        containment_score = len(shorter) / len(longer)
    return max(sequence_score, containment_score)


def get_first_reference_value(ref: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value: Any = ref
        for part in key.split("."):
            if not isinstance(value, dict):
                value = ""
                break
            value = value.get(part)
        text = normalize_text(value)
        if text:
            return text
    return ""


def reference_review_approved(ref: Dict[str, Any], *keys: str) -> bool:
    value = get_first_reference_value(ref, *keys).lower()
    return value in APPROVED_REVIEW_VALUES


def reference_reviewer_is_codex(ref: Dict[str, Any], *keys: str) -> bool:
    value = get_first_reference_value(ref, *keys).lower()
    return "codex" in value


def validate_reference_override(ref: Dict[str, Any], item: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    image_url = normalize_text(ref.get("image_url"))
    source_page_url = normalize_text(ref.get("source_page_url"))
    attribution_label = normalize_text(ref.get("attribution_label"))
    source_type = normalize_text(ref.get("reference_source_type") or ref.get("source_type"))
    matched_name = get_first_reference_value(
        ref,
        "matched_name",
        "matched_equipment_name",
        "equipment_name_on_page",
        "official_name",
    )
    computed_score = reference_name_match_score(item.get("name"), matched_name)
    provided_score = ref.get("name_match_score")
    try:
        provided_score_value = float(provided_score)
    except (TypeError, ValueError):
        provided_score_value = -1.0

    evidence = {
        "matched_name": matched_name,
        "computed_name_match_score": round(computed_score, 4),
        "name_match_score": round(provided_score_value, 4),
        "reference_source_type": source_type,
        "visual_review_status": get_first_reference_value(
            ref,
            "visual_review.status",
            "codex_visual_review.status",
            "visual_review_status",
        ),
        "second_review_status": get_first_reference_value(
            ref,
            "second_review.status",
            "codex_second_review.status",
            "double_check.status",
            "second_review_status",
            "double_check_status",
        ),
    }

    if not image_url:
        return False, "reference_rejected:missing_image_url", evidence
    if not source_page_url:
        return False, "reference_rejected:missing_source_page_url", evidence
    if not attribution_label:
        return False, "reference_rejected:missing_attribution_label", evidence
    if source_type not in REFERENCE_SOURCE_TYPES:
        return False, "reference_rejected:unsupported_source_type", evidence
    if not matched_name:
        return False, "reference_rejected:missing_matched_name", evidence
    if provided_score_value < MIN_REFERENCE_NAME_MATCH_SCORE:
        return False, "reference_rejected:name_match_below_0_90", evidence
    if not reference_review_approved(ref, "visual_review.status", "codex_visual_review.status", "visual_review_status"):
        return False, "reference_rejected:visual_review_not_approved", evidence
    if not reference_review_approved(
        ref,
        "second_review.status",
        "codex_second_review.status",
        "double_check.status",
        "second_review_status",
        "double_check_status",
    ):
        return False, "reference_rejected:second_review_not_approved", evidence
    if not reference_reviewer_is_codex(ref, "visual_review.reviewer", "codex_visual_review.reviewer", "visual_review_reviewer"):
        return False, "reference_rejected:visual_review_reviewer_not_codex", evidence
    if not reference_reviewer_is_codex(
        ref,
        "second_review.reviewer",
        "codex_second_review.reviewer",
        "double_check.reviewer",
        "second_review_reviewer",
        "double_check_reviewer",
    ):
        return False, "reference_rejected:second_review_reviewer_not_codex", evidence
    return True, "", evidence


def html_candidates_from_source(
    source_url: str,
    timeout: float,
    max_bytes: int,
    ssl_context: Optional[ssl.SSLContext],
) -> Tuple[List[ImageCandidate], str, str]:
    fetch_url = page_fetch_url(source_url)
    try:
        data, content_type, final_url = fetch_bytes(fetch_url, timeout, max_bytes, ssl_context)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return [], fetch_url, f"source_fetch_failed:{exc}"

    media_type = content_type_for(final_url, content_type)
    if "pdf" in media_type or final_url.lower().endswith(".pdf"):
        return [], final_url, "pdf_requires_explicit_extractor"
    if media_type and "html" not in media_type and "xml" not in media_type:
        return [], final_url, f"unsupported_source_content_type:{media_type}"

    html = decode_html(data, content_type)
    parser = CandidateHTMLParser(final_url)
    parser.feed(html)
    return parser.candidates, final_url, ""


def available_image_metadata(
    *,
    item: Dict[str, Any],
    source_kind: str,
    display_path: str,
    image_info: Dict[str, Any],
    source_page_url: str,
    attribution_label: str,
) -> Dict[str, Any]:
    name = normalize_text(item.get("name")) or "研究機器"
    return {
        "status": "available",
        "source_kind": source_kind,
        "display_url": display_path,
        "original_url": normalize_text(image_info.get("original_url")),
        "source_page_url": source_page_url,
        "attribution_label": attribution_label,
        "alt_ja": f"{name}の機器画像",
        "fetched_at": utc_now(),
        "content_type": "image/jpeg",
        "width": image_info.get("width"),
        "height": image_info.get("height"),
        "sha256": normalize_text(image_info.get("sha256")),
    }


def unavailable_image_metadata(status: str, source_url: str, reason: str) -> Dict[str, Any]:
    return {
        "status": status,
        "source_kind": "",
        "display_url": "",
        "original_url": "",
        "source_page_url": source_url,
        "attribution_label": "",
        "alt_ja": "",
        "fetched_at": utc_now(),
        "content_type": "",
        "width": None,
        "height": None,
        "sha256": "",
        "reason": reason,
    }


def select_items(
    items: List[Dict[str, Any]],
    *,
    offset: int,
    limit: Optional[int],
    doc_ids: set[str],
    hosts: set[str],
) -> List[Tuple[int, Dict[str, Any]]]:
    selected: List[Tuple[int, Dict[str, Any]]] = []
    for index, item in enumerate(items):
        if index < offset:
            continue
        source_url = normalize_text(item.get("source_url"))
        eq_id = item_key(item, index)
        doc_id = normalize_text(item.get("doc_id"))
        if doc_ids and eq_id not in doc_ids and doc_id not in doc_ids:
            continue
        if hosts and host_of(source_url) not in hosts:
            continue
        selected.append((index, item))
        if limit is not None and len(selected) >= limit:
            break
    return selected


def process_item(
    *,
    item: Dict[str, Any],
    index: int,
    args: argparse.Namespace,
    refs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    equipment_id = item_key(item, index)
    output_key = detail_key(item, equipment_id)
    shard = shard_key(equipment_id, max(1, int(args.shard_count)))
    output_path = Path(args.images_root) / shard / f"{safe_file_stem(output_key)}.jpg"
    display_path = "/" + str(output_path.relative_to(Path(args.public_root))).replace(os.sep, "/")
    source_url = normalize_text(item.get("source_url"))

    existing = item.get("image_v1") if isinstance(item.get("image_v1"), dict) else {}
    if (
        not args.force
        and normalize_text(existing.get("status")) == "available"
        and normalize_text(existing.get("display_url"))
        and (Path(args.public_root) / normalize_text(existing.get("display_url")).lstrip("/")).exists()
    ):
        return {
            "doc_id": normalize_text(item.get("doc_id")),
            "equipment_id": equipment_id,
            "name": normalize_text(item.get("name")),
            "source_url": source_url,
            "status": "skipped_existing",
            "display_url": normalize_text(existing.get("display_url")),
        }

    if (
        not args.force
        and args.skip_existing_terminal
        and normalize_text(existing.get("status")) in {"not_found", "fetch_failed", "needs_review"}
    ):
        return {
            "doc_id": normalize_text(item.get("doc_id")),
            "equipment_id": equipment_id,
            "name": normalize_text(item.get("name")),
            "source_url": source_url,
            "status": "skipped_existing_terminal",
            "reason": normalize_text(existing.get("reason")),
        }

    if not source_url:
        item["image_v1"] = unavailable_image_metadata("not_found", "", "missing_source_url")
        return {
            "doc_id": normalize_text(item.get("doc_id")),
            "equipment_id": equipment_id,
            "name": normalize_text(item.get("name")),
            "source_url": "",
            "status": "not_found",
            "reason": "missing_source_url",
        }

    candidates, source_page_url, source_reason = html_candidates_from_source(
        source_url,
        float(args.timeout),
        int(args.max_source_bytes),
        args.ssl_context,
    )
    scored = unique_scored_candidates(candidates, item, int(args.min_score))
    last_reason = source_reason or "no_candidate_image"

    for candidate in scored[: max(1, int(args.max_candidates))]:
        image_info, reason = download_and_store_image(
            candidate.url,
            output_path,
            float(args.timeout),
            int(args.max_image_bytes),
            int(args.min_image_bytes),
            int(args.min_width),
            int(args.min_height),
            args.ssl_context,
        )
        if image_info:
            item["image_v1"] = available_image_metadata(
                item=item,
                source_kind="source_page",
                display_path=display_path,
                image_info=image_info,
                source_page_url=source_page_url,
                attribution_label=host_of(source_page_url),
            )
            return {
                "doc_id": normalize_text(item.get("doc_id")),
                "equipment_id": equipment_id,
                "name": normalize_text(item.get("name")),
                "source_url": source_url,
                "status": "available",
                "source_kind": "source_page",
                "display_url": display_path,
                "original_url": image_info.get("original_url"),
                "candidate_score": candidate.score,
                "candidate_count": len(scored),
            }
        last_reason = reason or last_reason

    ref = reference_override_for(item, equipment_id, refs)
    if ref and normalize_text(ref.get("image_url")):
        ref_ok, ref_reason, ref_evidence = validate_reference_override(ref, item)
        if not ref_ok:
            last_reason = ref_reason
            status = "needs_review"
            item["image_v1"] = unavailable_image_metadata(status, source_page_url or source_url, last_reason)
            item["image_v1"]["reference_review_v1"] = ref_evidence
            return {
                "doc_id": normalize_text(item.get("doc_id")),
                "equipment_id": equipment_id,
                "name": normalize_text(item.get("name")),
                "source_url": source_url,
                "status": status,
                "reason": last_reason,
                "reference_review_v1": ref_evidence,
                "candidate_count": len(scored),
            }
        ref_url = normalize_text(ref.get("image_url"))
        image_info, reason = download_and_store_image(
            ref_url,
            output_path,
            float(args.timeout),
            int(args.max_image_bytes),
            int(args.min_image_bytes),
            int(args.min_width),
            int(args.min_height),
            args.ssl_context,
        )
        if image_info:
            item["image_v1"] = available_image_metadata(
                item=item,
                source_kind="official_reference",
                display_path=display_path,
                image_info=image_info,
                source_page_url=normalize_text(ref.get("source_page_url")) or ref_url,
                attribution_label=normalize_text(ref.get("attribution_label")) or host_of(ref_url),
            )
            item["image_v1"]["reference_review_v1"] = ref_evidence
            item["image_v1"]["reference_note_ja"] = (
                "情報元ページに画像がなかったため、装置名称から取得した参考画像です。"
            )
            return {
                "doc_id": normalize_text(item.get("doc_id")),
                "equipment_id": equipment_id,
                "name": normalize_text(item.get("name")),
                "source_url": source_url,
                "status": "available",
                "source_kind": "official_reference",
                "display_url": display_path,
                "original_url": image_info.get("original_url"),
                "reference_review_v1": ref_evidence,
                "candidate_count": len(scored),
            }
        last_reason = f"reference_{reason}"

    status = "needs_review" if "requires" in last_reason or "unknown" in last_reason else "not_found"
    if last_reason.startswith("source_fetch_failed") or "download_failed" in last_reason:
        status = "fetch_failed"
    item["image_v1"] = unavailable_image_metadata(status, source_page_url or source_url, last_reason)
    return {
        "doc_id": normalize_text(item.get("doc_id")),
        "equipment_id": equipment_id,
        "name": normalize_text(item.get("name")),
        "source_url": source_url,
        "status": status,
        "reason": last_reason,
        "candidate_count": len(scored),
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--out-snapshot", default="")
    parser.add_argument("--public-root", default="frontend/dist")
    parser.add_argument("--images-root", default="frontend/dist/data/equipment-images")
    parser.add_argument("--reference-map", default="")
    parser.add_argument("--report", default="tools/equipment_image_collection_report.json")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--doc-id", action="append", default=[])
    parser.add_argument("--host", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--skip-existing-terminal", action="store_true")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--shard-count", type=int, default=64)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--min-score", type=int, default=5)
    parser.add_argument("--min-image-bytes", type=int, default=6000)
    parser.add_argument("--min-width", type=int, default=120)
    parser.add_argument("--min-height", type=int, default=90)
    parser.add_argument("--max-source-bytes", type=int, default=4_000_000)
    parser.add_argument("--max-image-bytes", type=int, default=8_000_000)
    parser.add_argument("--allow-insecure-tls", action="store_true")
    return parser.parse_args(argv)


def insecure_tls_context() -> ssl.SSLContext:
    context = ssl._create_unverified_context()
    try:
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return context


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    socket.setdefaulttimeout(max(1.0, float(args.timeout)))
    root = Path.cwd()
    args.snapshot = str((root / args.snapshot).resolve())
    args.out_snapshot = str((root / (args.out_snapshot or args.snapshot)).resolve())
    args.public_root = str((root / args.public_root).resolve())
    args.images_root = str((root / args.images_root).resolve())
    args.ssl_context = insecure_tls_context() if args.allow_insecure_tls else None
    report_path = (root / args.report).resolve()
    refs = load_reference_map((root / args.reference_map).resolve() if args.reference_map else None)

    payload = load_snapshot(Path(args.snapshot))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    selected = select_items(
        items,
        offset=max(0, int(args.offset)),
        limit=args.limit,
        doc_ids={normalize_text(v) for v in args.doc_id if normalize_text(v)},
        hosts={normalize_text(v).lower() for v in args.host if normalize_text(v)},
    )

    results: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {}

    def build_report(complete: bool) -> Dict[str, Any]:
        return {
            "generated_at": utc_now(),
            "snapshot": args.snapshot,
            "out_snapshot": args.out_snapshot,
            "selected_count": len(selected),
            "completed_count": len(results),
            "complete": complete,
            "summary": dict(summary),
            "items": results,
        }

    def write_outputs(complete: bool) -> None:
        if not args.dry_run:
            write_snapshot(Path(args.out_snapshot), payload)
        write_json(report_path, build_report(complete))

    def record_result(number: int, result: Dict[str, Any]) -> None:
        results.append(result)
        status = normalize_text(result.get("status")) or "unknown"
        summary[status] = summary.get(status, 0) + 1
        print(
            json.dumps(
                {
                    "progress": f"{number}/{len(selected)}",
                    "doc_id": result.get("doc_id"),
                    "status": status,
                    "source_kind": result.get("source_kind"),
                    "reason": result.get("reason"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        checkpoint_every = max(0, int(args.checkpoint_every))
        if checkpoint_every and len(results) % checkpoint_every == 0:
            write_outputs(False)

    workers = max(1, int(args.workers))
    if workers == 1 or len(selected) <= 1:
        for number, (index, item) in enumerate(selected, start=1):
            result = process_item(item=item, index=index, args=args, refs=refs)
            record_result(number, result)
            if args.delay and number < len(selected):
                time.sleep(max(0.0, float(args.delay)))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(process_item, item=item, index=index, args=args, refs=refs): (index, item)
                for index, item in selected
            }
            for number, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
                record_result(number, future.result())
                if args.delay and number < len(selected):
                    time.sleep(max(0.0, float(args.delay)))

    write_outputs(True)
    print(json.dumps({"selected": len(selected), "summary": summary, "report": str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
