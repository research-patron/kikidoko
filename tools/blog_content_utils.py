#!/usr/bin/env python3
"""Shared markdown/content helpers for blog preflight and WP publish."""

from __future__ import annotations

import re
from html import escape
from typing import Any

MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")
MARKDOWN_STRONG_STAR_PATTERN = re.compile(r"\*\*(.+?)\*\*")
MARKDOWN_STRONG_UNDERSCORE_PATTERN = re.compile(r"__(.+?)__")
MARKDOWN_EM_STAR_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
MARKDOWN_EM_UNDERSCORE_PATTERN = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")

LEFTOVER_MARKDOWN_PATTERNS = [
    re.compile(r"\[[^\]]+\]\([^)]+\)"),
    re.compile(r"\*\*[^*\n]+\*\*"),
    re.compile(r"__[^_\n]+__"),
    re.compile(r"(?<!\*)\*[^\n*]+\*(?!\*)"),
    re.compile(r"`[^`\n]*`"),
]


def normalize_title_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("　", "")
    normalized = normalized.replace(":", "").replace("：", "")
    normalized = normalized.replace("?", "").replace("？", "")
    normalized = normalized.replace("!", "").replace("！", "")
    return normalized


def strip_leading_h1_if_title_match(markdown_text: str, title: str) -> dict[str, Any]:
    lines = markdown_text.splitlines()
    first_non_empty = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty = idx
            break

    if first_non_empty is None:
        return {
            "text": markdown_text,
            "leading_h1_detected": False,
            "body_title_duplication": False,
            "removed_h1_text": "",
        }

    first_line = lines[first_non_empty].strip()
    match = re.match(r"^#\s+(.+)$", first_line)
    if not match:
        return {
            "text": markdown_text,
            "leading_h1_detected": False,
            "body_title_duplication": False,
            "removed_h1_text": "",
        }

    h1_text = match.group(1).strip()
    body_title_duplication = normalize_title_text(h1_text) == normalize_title_text(title)
    remaining = lines[:first_non_empty] + lines[first_non_empty + 1 :]
    cleaned_text = "\n".join(remaining).lstrip("\n")
    return {
        "text": cleaned_text,
        "leading_h1_detected": True,
        "body_title_duplication": body_title_duplication,
        "removed_h1_text": h1_text,
    }


def extract_markdown_links(markdown_text: str) -> list[str]:
    return [m.group(2).strip() for m in MARKDOWN_LINK_PATTERN.finditer(markdown_text)]


def _store_placeholder(store: dict[str, str], content: str) -> str:
    key = f"@@MDTOKEN{len(store)}@@"
    store[key] = content
    return key


def render_inline_markdown(text: str) -> str:
    placeholders: dict[str, str] = {}
    working = text

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        href = match.group(2).strip()
        rendered_label = render_inline_markdown(label)
        html = f'<a href="{escape(href, quote=True)}">{rendered_label}</a>'
        return _store_placeholder(placeholders, html)

    def code_repl(match: re.Match[str]) -> str:
        code_text = match.group(1)
        html = f"<code>{escape(code_text)}</code>"
        return _store_placeholder(placeholders, html)

    working = MARKDOWN_LINK_PATTERN.sub(link_repl, working)
    working = MARKDOWN_CODE_SPAN_PATTERN.sub(code_repl, working)
    working = escape(working)

    working = MARKDOWN_STRONG_STAR_PATTERN.sub(r"<strong>\1</strong>", working)
    working = MARKDOWN_STRONG_UNDERSCORE_PATTERN.sub(r"<strong>\1</strong>", working)
    working = MARKDOWN_EM_STAR_PATTERN.sub(r"<em>\1</em>", working)
    working = MARKDOWN_EM_UNDERSCORE_PATTERN.sub(r"<em>\1</em>", working)

    for key, value in placeholders.items():
        working = working.replace(key, value)
    return working


def markdown_to_plain_text(markdown_text: str) -> str:
    text = markdown_text
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = MARKDOWN_LINK_PATTERN.sub(r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = MARKDOWN_CODE_SPAN_PATTERN.sub(r"\1", text)
    text = MARKDOWN_STRONG_STAR_PATTERN.sub(r"\1", text)
    text = MARKDOWN_STRONG_UNDERSCORE_PATTERN.sub(r"\1", text)
    text = MARKDOWN_EM_STAR_PATTERN.sub(r"\1", text)
    text = MARKDOWN_EM_UNDERSCORE_PATTERN.sub(r"\1", text)
    return text.strip()


def count_seo_chars(markdown_text: str) -> int:
    plain = markdown_to_plain_text(markdown_text)
    return len(re.sub(r"\s+", "", plain))


def _paragraph_block(content: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{content}</p>\n<!-- /wp:paragraph -->"


def _heading_block(level: int, content: str) -> str:
    if level <= 1:
        level = 2
    if level > 6:
        level = 6
    if level == 2:
        open_line = "<!-- wp:heading -->"
    else:
        open_line = f'<!-- wp:heading {{"level":{level}}} -->'
    return (
        f"{open_line}\n"
        f'<h{level} class="wp-block-heading">{content}</h{level}>\n'
        "<!-- /wp:heading -->"
    )


def _list_block(items: list[str], ordered: bool) -> str:
    tag = "ol" if ordered else "ul"
    open_block = '<!-- wp:list {"ordered":true} -->' if ordered else "<!-- wp:list -->"
    lines = [open_block, f'<{tag} class="wp-block-list">']
    for item in items:
        lines.append("<!-- wp:list-item -->")
        lines.append(f"<li>{item}</li>")
        lines.append("<!-- /wp:list-item -->")
    lines.append(f"</{tag}>")
    lines.append("<!-- /wp:list -->")
    return "\n".join(lines)


def markdown_to_blocks(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    list_ordered: bool | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        joined = " ".join(s.strip() for s in paragraph_buffer if s.strip())
        if joined:
            blocks.append(_paragraph_block(render_inline_markdown(joined)))
        paragraph_buffer = []

    def flush_list() -> None:
        nonlocal list_buffer, list_ordered
        if not list_buffer:
            return
        rendered_items = [render_inline_markdown(item) for item in list_buffer]
        blocks.append(_list_block(rendered_items, ordered=bool(list_ordered)))
        list_buffer = []
        list_ordered = None

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        ul_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        ol_match = re.match(r"^\d+\.\s+(.*)$", stripped)

        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            text = render_inline_markdown(heading_match.group(2).strip())
            blocks.append(_heading_block(level, text))
            continue

        if ul_match:
            flush_paragraph()
            if list_ordered is True:
                flush_list()
            list_ordered = False
            list_buffer.append(ul_match.group(1).strip())
            continue

        if ol_match:
            flush_paragraph()
            if list_ordered is False:
                flush_list()
            list_ordered = True
            list_buffer.append(ol_match.group(1).strip())
            continue

        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n\n".join(blocks).strip()


def detect_markdown_tokens(text: str) -> list[str]:
    leftovers: list[str] = []
    for pattern in LEFTOVER_MARKDOWN_PATTERNS:
        leftovers.extend(match.group(0) for match in pattern.finditer(text))
    if "`" in text:
        leftovers.append("`")

    unique: list[str] = []
    seen: set[str] = set()
    for token in leftovers:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique
