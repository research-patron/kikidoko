#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path


DEFAULT_PUBLIC_ROOT = Path("frontend/dist")
BANNED_PUBLIC_PATTERNS = (
    ".DS_Store",
    "*conflicted*",
    "README.md",
    "publish-log.json",
    "*-plan.md",
    "seo-article-report-*.md",
    "kikidoko-patches*.css",
    "kikidoko-patches*.js",
    "blog/drafts/*",
    "blog/**/*.md",
)
BANNED_REPO_PATHS = (
    Path("frontend/firebase-debug.log"),
    Path("frontend/.DS_Store"),
    Path("frontend/dist/.DS_Store"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail closed when non-public or stale files remain in the Hosting tree.")
    parser.add_argument("--public-root", default=str(DEFAULT_PUBLIC_ROOT))
    return parser.parse_args()


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def main() -> int:
    args = parse_args()
    public_root = Path(args.public_root).resolve()
    failures: list[str] = []
    blog_manifest_variants: list[str] = []

    if not public_root.exists():
        raise SystemExit(f"public_tree_audit_failed:missing_public_root:{public_root}")

    for path in sorted(public_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(public_root).as_posix()
        if fnmatch.fnmatch(relative, "blog/articles*.json"):
            blog_manifest_variants.append(relative)
        if matches_any(relative, BANNED_PUBLIC_PATTERNS):
            failures.append(relative)

    for path in BANNED_REPO_PATHS:
        if path.resolve().exists():
            failures.append(str(path))

    blog_manifest = public_root / "blog" / "articles.json"
    if not blog_manifest.exists():
        failures.append("missing:blog/articles.json")
    if len(blog_manifest_variants) != 1 or blog_manifest_variants[0] != "blog/articles.json":
        failures.append("invalid_blog_manifest_variants:" + ",".join(blog_manifest_variants or ["<none>"]))

    if failures:
        raise SystemExit("public_tree_audit_failed:\n" + "\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
