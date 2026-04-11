#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_DIR = Path("frontend/update-notes/entries")
DEFAULT_OUTPUT_PATH = Path("frontend/dist/update-info/index.json")


@dataclass
class NoteEntry:
    source_path: Path
    slug: str
    title: str
    published_at: str
    summary: str
    version_label: str
    status: str
    tags: list[str]
    body_markdown: str
    body_html: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build update info manifest from Markdown notes.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
      raise ValueError("frontmatter_missing")
    closing = text.find("\n---\n", 4)
    if closing < 0:
      raise ValueError("frontmatter_unclosed")
    frontmatter = text[4:closing]
    body = text[closing + 5 :]
    return frontmatter, body.strip()


def parse_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_frontmatter(frontmatter: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = frontmatter.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        if raw.lstrip().startswith("- "):
            raise ValueError("top_level_list_not_supported")
        if ":" not in raw:
            raise ValueError(f"invalid_frontmatter_line:{raw}")
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = parse_scalar(value)
            i += 1
            continue

        items: list[str] = []
        i += 1
        while i < len(lines):
            child = lines[i]
            if child.startswith("  - "):
                items.append(parse_scalar(child[4:]))
                i += 1
                continue
            if not child.strip():
                i += 1
                continue
            break
        data[key] = items
    return data


def inline_markdown(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{escape(m.group(1))}</code>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{escape(m.group(2), quote=True)}">{escape(m.group(1))}</a>',
        escaped,
    )
    return escaped


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("## "):
            html_parts.append(f"<h4>{inline_markdown(line[3:].strip())}</h4>")
            i += 1
            continue
        if line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline_markdown(lines[i][2:].strip())}</li>")
                i += 1
            html_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        paragraph: list[str] = []
        while i < len(lines):
            current = lines[i].rstrip()
            if not current.strip() or current.startswith("## ") or current.startswith("- "):
                break
            paragraph.append(current.strip())
            i += 1
        html_parts.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
    return "\n".join(html_parts)


def require_frontmatter(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing_required_field:{key}")
    return value.strip()


def parse_note(path: Path) -> NoteEntry:
    raw = path.read_text(encoding="utf-8")
    frontmatter_text, body = split_frontmatter(raw)
    frontmatter = parse_frontmatter(frontmatter_text)
    title = require_frontmatter(frontmatter, "title")
    published_at = require_frontmatter(frontmatter, "published_at")
    summary = require_frontmatter(frontmatter, "summary")
    version_label = require_frontmatter(frontmatter, "version_label")
    status = require_frontmatter(frontmatter, "status")
    datetime.fromisoformat(published_at)
    tags = frontmatter.get("tags") or []
    if not isinstance(tags, list):
        raise ValueError("invalid_tags")
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    return NoteEntry(
        source_path=path,
        slug=path.stem,
        title=title,
        published_at=published_at,
        summary=summary,
        version_label=version_label,
        status=status,
        tags=tags,
        body_markdown=body,
        body_html=markdown_to_html(body),
    )


def load_notes(source_dir: Path) -> list[NoteEntry]:
    entries: list[NoteEntry] = []
    for path in sorted(source_dir.rglob("*.md")):
        entries.append(parse_note(path))
    entries.sort(key=lambda entry: entry.published_at, reverse=True)
    return entries


def month_key(entry: NoteEntry) -> str:
    dt = datetime.fromisoformat(entry.published_at)
    return f"{dt.year:04d}-{dt.month:02d}"


def month_label(key: str) -> str:
    year, month = key.split("-", 1)
    return f"{year}年{int(month)}月"


def entry_payload(entry: NoteEntry) -> dict[str, Any]:
    return {
        "id": entry.slug,
        "title": entry.title,
        "published_at": entry.published_at,
        "summary": entry.summary,
        "version_label": entry.version_label,
        "status": entry.status,
        "tags": entry.tags,
        "body_html": entry.body_html,
    }


def build_manifest(entries: list[NoteEntry]) -> dict[str, Any]:
    latest = entry_payload(entries[0]) if entries else None
    month_groups: dict[str, list[NoteEntry]] = {}
    for entry in entries:
        key = month_key(entry)
        month_groups.setdefault(key, []).append(entry)

    month_keys = sorted(month_groups.keys(), reverse=True)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "latest": latest,
        "months": [
            {
                "key": key,
                "label": month_label(key),
                "entries": [entry_payload(entry) for entry in month_groups[key]],
            }
            for key in month_keys
        ],
    }


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    output_path = Path(args.output).resolve()

    entries = load_notes(source_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_manifest(entries)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
