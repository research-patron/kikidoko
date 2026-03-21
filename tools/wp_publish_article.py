#!/usr/bin/env python3
"""Publish one blog article to WordPress via REST API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from blog_content_utils import (
    detect_markdown_tokens,
    markdown_to_blocks,
    markdown_to_plain_text,
    strip_leading_h1_if_title_match,
)
from seo_preflight_article import find_article, load_manifest, run_preflight

CATEGORY_DISPLAY_NAMES = {
    "guide": "基礎ガイド",
    "equipment": "機器別ガイド",
    "region": "地域別ガイド",
    "workflow": "実務フロー",
}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 30


class WPApiError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one article to WordPress.")
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--wp-base", required=True)
    parser.add_argument("--draft")
    parser.add_argument("--publish-log", default="frontend/public/blog/publish-log.json")
    parser.add_argument("--ensure-all-categories", action="store_true")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--report-out")
    return parser.parse_args()


def build_headers(user: str, app_password: str) -> dict[str, str]:
    token_raw = f"{user}:{app_password}".encode("utf-8")
    token = base64.b64encode(token_raw).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def http_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    retries: int = 3,
    insecure: bool = False,
) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    last_error: Exception | None = None
    last_url = url

    ssl_context = ssl._create_unverified_context() if insecure else None

    for attempt in range(retries + 1):
        req = Request(url=url, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT, context=ssl_context) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body) if body else {}
                return resp.status, parsed
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            parsed: Any
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"raw": body}

            if exc.code in RETRYABLE_STATUS and attempt < retries:
                time.sleep(2**attempt)
                continue
            if exc.code in {401, 403}:
                message = parsed.get("message") if isinstance(parsed, dict) else str(parsed)
                raise WPApiError(f"authorization error ({exc.code}): {message}") from exc
            raise WPApiError(f"http error {exc.code}: {parsed}") from exc
        except URLError as exc:
            last_error = exc
            last_url = url
            if attempt < retries:
                time.sleep(2**attempt)
                continue
            break

    raise WPApiError(f"network error: {last_error} (url={last_url})")


def api_get(
    api_base: str,
    endpoint: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    insecure: bool = False,
) -> Any:
    qs = f"?{urlencode(params, doseq=True)}" if params else ""
    status, payload = http_json(
        "GET",
        f"{api_base}{endpoint}{qs}",
        headers,
        insecure=insecure,
    )
    if status != 200:
        raise WPApiError(f"GET {endpoint} failed with status {status}")
    return payload


def api_post(
    api_base: str,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    insecure: bool = False,
) -> Any:
    status, data = http_json(
        "POST",
        f"{api_base}{endpoint}",
        headers,
        payload=payload,
        insecure=insecure,
    )
    if status not in {200, 201}:
        raise WPApiError(f"POST {endpoint} failed with status {status}: {data}")
    return data


def ensure_category(
    api_base: str,
    headers: dict[str, str],
    slug: str,
    name: str,
    insecure: bool = False,
) -> int:
    existing = api_get(
        api_base,
        "/categories",
        headers,
        params={"slug": slug, "per_page": 100},
        insecure=insecure,
    )
    if existing:
        return int(existing[0]["id"])
    created = api_post(
        api_base,
        "/categories",
        headers,
        payload={"slug": slug, "name": name},
        insecure=insecure,
    )
    return int(created["id"])


def ensure_categories(
    api_base: str,
    headers: dict[str, str],
    target_slug: str,
    ensure_all: bool,
    insecure: bool = False,
) -> dict[str, int]:
    ensured: dict[str, int] = {}
    items = CATEGORY_DISPLAY_NAMES.items() if ensure_all else [(target_slug, CATEGORY_DISPLAY_NAMES[target_slug])]
    for slug, name in items:
        ensured[slug] = ensure_category(
            api_base,
            headers,
            slug=slug,
            name=name,
            insecure=insecure,
        )
    return ensured


def find_existing_post(
    api_base: str,
    headers: dict[str, str],
    slug: str,
    insecure: bool = False,
) -> dict[str, Any] | None:
    posts = api_get(
        api_base,
        "/posts",
        headers,
        params={
            "slug": slug,
            "context": "edit",
            "per_page": 100,
            "status": "any",
        },
        insecure=insecure,
    )
    if not posts:
        return None
    return posts[0]


def build_excerpt(markdown_text: str, min_len: int = 120, max_len: int = 160) -> str:
    text = markdown_to_plain_text(markdown_text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    excerpt = text[:max_len].rstrip()
    if len(excerpt) < min_len:
        return text[:min_len].rstrip()
    return excerpt


def normalize_wp_site_base(wp_base: str) -> str:
    base = wp_base.strip().rstrip("/")
    if base.endswith("/blog"):
        base = base[: -len("/blog")]
    return base


def expected_permalink(site_base: str, article_url: str) -> str:
    path = article_url.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{site_base}{path.rstrip('/')}/"


def append_publish_log(path: Path, entry: dict[str, Any]) -> None:
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {"entries": []}
    else:
        current = {"entries": []}

    if not isinstance(current, dict):
        current = {"entries": []}
    if not isinstance(current.get("entries"), list):
        current["entries"] = []
    current["entries"].append(entry)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_published_content_raw(raw_content: str) -> dict[str, Any]:
    has_block_marker = "<!-- wp:" in raw_content
    has_h1 = bool(re.search(r"<h1\b", raw_content, flags=re.IGNORECASE))
    markdown_tokens_left = detect_markdown_tokens(raw_content)
    return {
        "has_block_marker": has_block_marker,
        "has_h1": has_h1,
        "markdown_tokens_left": markdown_tokens_left,
    }


def main() -> int:
    args = parse_args()

    wp_user = os.environ.get("WP_USER")
    wp_password = os.environ.get("WP_APP_PASSWORD")
    if not wp_user or not wp_password:
        print("missing required env vars: WP_USER and WP_APP_PASSWORD")
        return 2

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}")
        return 2

    manifest = load_manifest(manifest_path)
    try:
        article = find_article(manifest, args.article_id)
    except KeyError as exc:
        print(str(exc))
        return 2

    draft_path = Path(args.draft) if args.draft else Path(f"frontend/public/blog/drafts/{args.article_id}.md")
    if not draft_path.exists():
        print(f"draft not found: {draft_path}")
        return 2

    draft_text = draft_path.read_text(encoding="utf-8")
    h1_info = strip_leading_h1_if_title_match(draft_text, article["title"])
    sanitized_draft = h1_info["text"]
    seo_report = run_preflight(article, draft_text)
    if args.report_out:
        Path(args.report_out).write_text(
            json.dumps(seo_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if not seo_report["passed"]:
        print(json.dumps(seo_report, ensure_ascii=False, indent=2))
        print("aborting publish due to failed SEO preflight")
        return 1

    headers = build_headers(wp_user, wp_password)
    site_base = normalize_wp_site_base(args.wp_base)
    api_base = f"{site_base}/wp-json/wp/v2"
    ensure_all = bool(args.ensure_all_categories)

    try:
        category_ids = ensure_categories(
            api_base=api_base,
            headers=headers,
            target_slug=article["category"],
            ensure_all=ensure_all,
            insecure=args.insecure,
        )
        target_category_id = category_ids[article["category"]]

        existing = find_existing_post(
            api_base,
            headers,
            slug=article["slug"],
            insecure=args.insecure,
        )
        content_blocks = markdown_to_blocks(sanitized_draft)
        excerpt = build_excerpt(sanitized_draft)
        payload = {
            "status": "publish",
            "slug": article["slug"],
            "title": article["title"],
            "content": content_blocks,
            "categories": [target_category_id],
            "excerpt": excerpt,
        }

        if existing is None:
            saved = api_post(
                api_base,
                "/posts",
                headers,
                payload=payload,
                insecure=args.insecure,
            )
            action = "created"
        else:
            saved = api_post(
                api_base,
                f"/posts/{existing['id']}",
                headers,
                payload=payload,
                insecure=args.insecure,
            )
            action = "updated"

        post_id = int(saved["id"])
        verified = api_get(
            api_base,
            f"/posts/{post_id}",
            headers,
            params={"context": "edit"},
            insecure=args.insecure,
        )
        expected_link = expected_permalink(site_base, article["url"])
        actual_link = verified.get("link", "")
        status = verified.get("status", "")
        categories = verified.get("categories", [])
        raw_content = ""
        if isinstance(verified.get("content"), dict):
            raw_content = verified["content"].get("raw", "")
        content_checks = validate_published_content_raw(raw_content)

        verification_errors: list[str] = []
        if status != "publish":
            verification_errors.append(f"status is not publish: {status}")
        if article["slug"] != verified.get("slug"):
            verification_errors.append("slug mismatch after publish")
        if target_category_id not in categories:
            verification_errors.append("target category is not attached")
        if actual_link.rstrip("/") != expected_link.rstrip("/"):
            verification_errors.append(
                f"unexpected permalink: expected {expected_link}, got {actual_link}"
            )
        if not content_checks["has_block_marker"]:
            verification_errors.append("published content is not block-editor formatted.")
        if content_checks["has_h1"]:
            verification_errors.append("published content includes h1 in body.")
        if content_checks["markdown_tokens_left"]:
            verification_errors.append(
                f"published content includes unconverted markdown tokens: "
                f"{content_checks['markdown_tokens_left']}"
            )

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "article_id": article["id"],
            "post_id": post_id,
            "action": action,
            "status": status,
            "slug": verified.get("slug"),
            "link": actual_link,
            "category_id": target_category_id,
            "editor_format": "gutenberg",
            "content_checks": content_checks,
            "seo_preflight": {
                "passed": seo_report["passed"],
                "checks": seo_report["checks"],
                "warnings": seo_report["warnings"],
            },
            "verification_errors": verification_errors,
        }
        append_publish_log(Path(args.publish_log), log_entry)

        output = {
            "result": "ok" if not verification_errors else "warning",
            "article_id": article["id"],
            "action": action,
            "post_id": post_id,
            "link": actual_link,
            "expected_link": expected_link,
            "verification_errors": verification_errors,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

        return 0 if not verification_errors else 1
    except WPApiError as exc:
        print(f"publish error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
