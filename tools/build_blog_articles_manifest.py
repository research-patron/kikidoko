#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MANIFEST = Path("frontend/content/blog/articles.json")
DEFAULT_MARKDOWN_DIR = Path("frontend/content/blog/articles")
DEFAULT_OUTPUT_PATH = Path("frontend/dist/blog/articles.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build public blog article manifest from source metadata and markdown.")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--markdown-dir", default=str(DEFAULT_MARKDOWN_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def strip_markdown(text: str) -> str:
    cleaned = str(text or "").replace("\r\n", "\n")
    cleaned = re.sub(r"^#{1,6}\s+.+$", " ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[>*_`]", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n\n", cleaned)
    return cleaned


def extract_excerpt(markdown: str, title: str, max_chars: int = 120) -> str:
    title_norm = normalize_text(title)
    candidates: list[str] = []
    for block in strip_markdown(markdown).split("\n\n"):
        paragraph = normalize_text(block)
        if not paragraph:
            continue
        if title_norm and (paragraph == title_norm or paragraph.startswith(title_norm)):
            continue
        candidates.append(paragraph)

    excerpt = next((item for item in candidates if len(item) >= 24), candidates[0] if candidates else "")
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[: max_chars - 1].rstrip() + "…"


def build_payload(source_manifest: Path, markdown_dir: Path) -> dict[str, Any]:
    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    articles = payload.get("articles") or []
    if not isinstance(articles, list):
        raise ValueError("invalid_articles_payload")

    built_articles: list[dict[str, Any]] = []
    for article in articles:
        item = dict(article)
        article_id = normalize_text(item.get("id"))
        if not article_id:
            raise ValueError("article_missing_id")

        markdown_path = markdown_dir / f"{article_id}.md"
        if not markdown_path.exists():
            raise FileNotFoundError(f"missing_article_markdown:{markdown_path}")

        markdown = markdown_path.read_text(encoding="utf-8")
        excerpt = extract_excerpt(markdown, item.get("title", ""))
        if not normalize_text(item.get("meta_description")):
            item["meta_description"] = excerpt
        item["excerpt"] = excerpt
        built_articles.append(item)

    payload["articles"] = built_articles
    payload["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return payload


def main() -> int:
    args = parse_args()
    source_manifest = Path(args.source_manifest).resolve()
    markdown_dir = Path(args.markdown_dir).resolve()
    output_path = Path(args.output).resolve()

    payload = build_payload(source_manifest, markdown_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
