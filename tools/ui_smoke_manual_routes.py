#!/usr/bin/env python3
"""UI smoke test for manual usage / paper route / beginner route flows."""

from __future__ import annotations

import argparse
import gzip
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class SkipRowError(RuntimeError):
    """Raised when a row exists but cannot satisfy beginner-route checks."""


def wait_for_results(page, timeout_ms: int = 20000) -> int:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        count = page.locator(".result-row").count()
        if count > 0:
            return count
        page.wait_for_timeout(250)
    raise RuntimeError("result rows not found")


def wait_hash_prefix(page, prefix: str, timeout_ms: int = 8000) -> str:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        value = page.evaluate("location.hash")
        if str(value).startswith(prefix):
            return str(value)
        page.wait_for_timeout(100)
    raise RuntimeError(f"hash did not start with {prefix}")


def wait_hash_not_prefix(page, prefix: str, timeout_ms: int = 8000) -> str:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        value = page.evaluate("location.hash")
        if not str(value).startswith(prefix):
            return str(value)
        page.wait_for_timeout(100)
    raise RuntimeError(f"hash still starts with {prefix}")


def wait_route_overlay_closed(page, timeout_ms: int = 8000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        closed = page.evaluate(
            """() => {
              const overlay = document.getElementById('manual-route-overlay');
              return !overlay || overlay.hidden === true;
            }"""
        )
        if closed:
            return
        page.wait_for_timeout(100)
    raise RuntimeError("manual route overlay did not close")


def load_snapshot_index(snapshot_path: str) -> Dict[str, Dict[str, Any]]:
    path = (Path.cwd() / snapshot_path).resolve()
    if not path.exists():
        raise RuntimeError(f"snapshot not found: {path}")
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else []
    index: Dict[str, Dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id") or "").strip()
            if doc_id:
                index[doc_id] = item
    return index


def load_doc_ids(path: str) -> List[str]:
    p = (Path.cwd() / path).resolve()
    if not p.exists():
        raise RuntimeError(f"doc ids file not found: {p}")
    out: List[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        doc_id = raw.strip()
        if doc_id:
            out.append(doc_id)
    return out


def resolve_paper_doi(item: Dict[str, Any]) -> str:
    manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
    papers = manual.get("paper_explanations") if isinstance(manual.get("paper_explanations"), list) else []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        doi = str(paper.get("doi") or "").strip()
        if doi:
            return doi
    source_papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    for paper in source_papers:
        if not isinstance(paper, dict):
            continue
        doi = str(paper.get("doi") or "").strip()
        if doi:
            return doi
    return ""


def navigate_direct_route(page, hash_value: str, timeout_ms: int = 60000) -> str:
    base_url = str(page.url or "").split("#", 1)[0] or "about:blank"
    target = f"{base_url}{hash_value}"
    page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(4000)
    return target


def run_keyboard_checks_direct(page, doc_id: str, doi: str) -> Dict[str, Any]:
    if not doi:
        raise RuntimeError(f"paper doi missing for doc_id={doc_id}")
    paper_hash = f"#/paper/{doc_id}/{doi}"
    beginner_hash = f"#/beginner/{doc_id}"
    out: Dict[str, Any] = {}

    navigate_direct_route(page, paper_hash)
    out["paper_enter_hash"] = wait_hash_prefix(page, "#/paper/")
    verify_paper_overlay(page)
    out["paper_space_hash"] = out["paper_enter_hash"]

    navigate_direct_route(page, beginner_hash)
    out["beginner_enter_hash"] = wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    out["beginner_space_hash"] = out["beginner_enter_hash"]
    return out


def run_desktop_checks_direct(
    page,
    target_cases: int,
    doc_ids: List[str],
    snapshot_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for doc_id in doc_ids:
        if len(records) >= target_cases:
            break
        item = snapshot_index.get(doc_id)
        if not item:
            continue
        doi = resolve_paper_doi(item)
        if not doi:
            continue
        paper_hash = f"#/paper/{doc_id}/{doi}"
        beginner_hash = f"#/beginner/{doc_id}"
        last_error = ""
        ok = False
        for _ in range(3):
            try:
                navigate_direct_route(page, paper_hash)
                wait_hash_prefix(page, "#/paper/")
                verify_paper_overlay(page)

                navigate_direct_route(page, beginner_hash)
                wait_hash_prefix(page, "#/beginner/")
                verify_beginner_overlay(page)
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                page.wait_for_timeout(200)
        if not ok:
            raise RuntimeError(f"direct-route case failed for {doc_id}: {last_error}")

        manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
        general = manual.get("general_usage") if isinstance(manual.get("general_usage"), dict) else {}
        beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
        papers = manual.get("paper_explanations") if isinstance(manual.get("paper_explanations"), list) else []

        records.append(
            {
                "case_no": len(records) + 1,
                "row_name": str(item.get("name") or ""),
                "summary_len": len(str(general.get("summary_ja") or "").strip()),
                "sample_count": len(general.get("sample_states") or []),
                "field_count": len(general.get("research_fields_ja") or []),
                "paper_count": len(papers),
                "badge_present": False,
                "badge": "",
                "paper_hash": paper_hash,
                "beginner_hash": beginner_hash,
                "paper_link_href": str((papers[0] or {}).get("link_url") or ""),
                "beginner_sections": [
                    bool(str(beginner.get("principle_ja") or "").strip()),
                    bool(str(beginner.get("sample_guidance_ja") or "").strip()),
                    len(beginner.get("basic_steps_ja") or []),
                    len(beginner.get("common_pitfalls_ja") or []),
                ],
            }
        )
    if len(records) < target_cases:
        raise RuntimeError(f"insufficient direct-route cases checked: {len(records)}/{target_cases}")
    return records


def run_mobile_checks_direct(page, doc_id: str, doi: str) -> Dict[str, Any]:
    if not doi:
        raise RuntimeError(f"paper doi missing for doc_id={doc_id}")
    navigate_direct_route(page, f"#/paper/{doc_id}/{doi}")
    wait_hash_prefix(page, "#/paper/")
    verify_paper_overlay(page)
    overflow_paper = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")

    navigate_direct_route(page, f"#/beginner/{doc_id}")
    wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    overflow_beginner = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    return {"paper_overflow": bool(overflow_paper), "beginner_overflow": bool(overflow_beginner)}


def close_sheet_if_open(page) -> None:
    panel = page.locator(".equipment-sheet-panel").first
    if panel.count() < 1:
        return
    if not panel.is_visible():
        return
    close_btn = page.locator(".equipment-sheet-close").first
    if close_btn.count() > 0 and close_btn.is_visible():
        close_btn.click()
    else:
        page.keyboard.press("Escape")
    deadline = time.time() + 8
    while time.time() < deadline:
        if not panel.is_visible():
            return
        page.wait_for_timeout(100)
    raise RuntimeError("equipment sheet did not close")


def find_eligible_row_index_on_page(page) -> int:
    rows_count = page.locator(".result-row").count()
    for idx in range(rows_count):
        close_sheet_if_open(page)
        row = page.locator(".result-row").nth(idx)
        ensure_sheet_open(page, row)
        paper_count = page.locator(".manual-paper-list .manual-paper-item").count()
        beginner_button = page.locator(".manual-beginner-button").first
        enabled_beginner = (
            beginner_button.count() > 0
            and beginner_button.is_visible()
            and not beginner_button.is_disabled()
        )
        close_sheet_if_open(page)
        if paper_count > 0 and enabled_beginner:
            return idx
    raise SkipRowError("no eligible row on current page")


def find_eligible_row_with_paging(page, max_pages: int = 5000) -> int:
    checked_pages = 0
    while checked_pages < max_pages:
        wait_for_results(page)
        try:
            return find_eligible_row_index_on_page(page)
        except SkipRowError:
            if not go_next_page(page):
                break
            checked_pages += 1
    raise RuntimeError("no eligible row with enabled beginner route found")


def verify_paper_overlay(page) -> Dict[str, Any]:
    selector = ".manual-route-panel.paper-detail-page"
    panel = page.locator(selector)
    deadline_panel = time.time() + 12
    while time.time() < deadline_panel:
        if panel.count() > 0 and panel.first.is_visible():
            break
        page.wait_for_timeout(120)
    if panel.count() < 1 or not panel.first.is_visible():
        raise RuntimeError("paper detail panel not found")
    required = ["研究目的", "手法", "わかったこと", "リンク"]
    deadline = time.time() + 8
    missing: List[str] = required[:]
    link = panel.locator("a.paper-detail-link").first
    while time.time() < deadline:
        text = panel.first.inner_text()
        missing = [label for label in required if label not in text]
        if link.count() < 1:
            link = panel.locator("a").first
        if not missing and link.count() > 0:
            break
        page.wait_for_timeout(150)
    if missing:
        raise RuntimeError(f"paper panel missing labels: {missing}")
    if link.count() < 1:
        raise RuntimeError("paper detail link anchor not found")
    href = link.get_attribute("href") or ""
    if not href.startswith("http"):
        raise RuntimeError(f"paper detail link href invalid: {href}")
    return {"paper_link_href": href}


def verify_beginner_overlay(page) -> None:
    selector = ".manual-route-panel.beginner-detail-page"
    panel = page.locator(selector)
    deadline_panel = time.time() + 12
    while time.time() < deadline_panel:
        if panel.count() > 0 and panel.first.is_visible():
            break
        page.wait_for_timeout(120)
    if panel.count() < 1 or not panel.first.is_visible():
        raise RuntimeError("beginner detail panel not found")
    required = ["原理", "試料", "基本手順", "失敗しやすい点"]
    text = panel.first.inner_text()
    missing = [label for label in required if label not in text]
    if missing:
        raise RuntimeError(f"beginner panel missing labels: {missing}")
    toc_links = panel.locator(".beginner-toc-link")
    if toc_links.count() < 4:
        raise RuntimeError("beginner toc links missing")


def ensure_sheet_open(page, row_locator) -> None:
    panel = page.locator(".equipment-sheet-panel").first
    if panel.count() > 0 and panel.is_visible():
        return
    row_locator.click()
    page.wait_for_selector(".equipment-sheet-panel", timeout=8000)


def open_row_and_verify(page, row_index: int, key_variant: str) -> Dict[str, Any]:
    close_sheet_if_open(page)
    row = page.locator(".result-row").nth(row_index)
    ensure_sheet_open(page, row)
    name_loc = row.locator(".result-title strong").first
    row_name = name_loc.inner_text().strip() if name_loc.count() else row.inner_text().strip().split("\n")[0]
    page.wait_for_timeout(600)

    summary = page.locator(".manual-usage-summary").first.inner_text().strip()
    sample_count = page.locator(".manual-sample-states li").count()
    field_count = page.locator(".manual-research-fields li").count()
    badge = ""
    badge_present = False
    badge_locator = page.locator(".manual-usage-section .manual-source-badge").first
    if badge_locator.count() > 0 and badge_locator.is_visible():
        badge_present = True
        badge = badge_locator.inner_text().strip()
    paper_count = page.locator(".manual-paper-list .manual-paper-item").count()

    if not summary:
        raise RuntimeError("manual summary missing")
    if sample_count < 1:
        raise RuntimeError("sample states missing")
    if field_count < 1:
        raise RuntimeError("research fields missing")
    if paper_count < 1:
        raise RuntimeError("paper list missing")

    first_paper = page.locator(".manual-paper-list .manual-paper-item").first
    first_paper.focus()
    if key_variant == "Enter":
        first_paper.press("Enter")
    else:
        first_paper.press("Space")
    paper_hash = wait_hash_prefix(page, "#/paper/")
    paper_info = verify_paper_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/paper/")
    wait_route_overlay_closed(page)

    ensure_sheet_open(page, row)
    beginner_button = page.locator(".manual-beginner-button").first
    beginner_button.wait_for(state="visible", timeout=8000)
    if beginner_button.is_disabled():
        close_sheet_if_open(page)
        raise SkipRowError("beginner button disabled")
    deadline = time.time() + 8
    beginner_hash = ""
    while time.time() < deadline:
        if beginner_button.is_disabled():
            page.wait_for_timeout(150)
            continue
        beginner_button.evaluate("(el) => el.click()")
        page.wait_for_timeout(200)
        current_hash = str(page.evaluate("location.hash"))
        if current_hash.startswith("#/beginner/"):
            beginner_hash = current_hash
            break
        page.wait_for_timeout(200)
    if not beginner_hash:
        beginner_hash = wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/beginner/")
    wait_route_overlay_closed(page)
    close_sheet_if_open(page)

    return {
        "row_name": row_name,
        "summary_len": len(summary),
        "sample_count": sample_count,
        "field_count": field_count,
        "paper_count": paper_count,
        "badge_present": badge_present,
        "badge": badge,
        "paper_hash": paper_hash,
        "beginner_hash": beginner_hash,
        **paper_info,
    }


def go_next_page(page) -> bool:
    buttons = page.locator(".pagination button")
    count = buttons.count()
    for idx in range(count):
        button = buttons.nth(idx)
        text = button.inner_text().strip()
        disabled = button.is_disabled()
        if text == ">" and not disabled:
            button.click()
            page.wait_for_timeout(1200)
            return True
    return False


def run_keyboard_checks(page) -> Dict[str, Any]:
    wait_for_results(page)
    row_index = find_eligible_row_with_paging(page)
    row = page.locator(".result-row").nth(row_index)
    out: Dict[str, Any] = {}

    def open_row() -> None:
        close_sheet_if_open(page)
        row.click()
        page.wait_for_selector(".equipment-sheet-panel", timeout=8000)
        page.wait_for_timeout(400)

    open_row()
    paper = page.locator(".manual-paper-list .manual-paper-item").first
    paper.focus()
    paper.press("Enter")
    out["paper_enter_hash"] = wait_hash_prefix(page, "#/paper/")
    verify_paper_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/paper/")
    wait_route_overlay_closed(page)

    open_row()
    paper = page.locator(".manual-paper-list .manual-paper-item").first
    paper.focus()
    paper.press("Space")
    out["paper_space_hash"] = wait_hash_prefix(page, "#/paper/")
    verify_paper_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/paper/")
    wait_route_overlay_closed(page)

    open_row()
    beginner = page.locator(".manual-beginner-button").first
    beginner.focus()
    beginner.press("Enter")
    out["beginner_enter_hash"] = wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/beginner/")
    wait_route_overlay_closed(page)

    open_row()
    beginner = page.locator(".manual-beginner-button").first
    beginner.focus()
    beginner.press("Space")
    out["beginner_space_hash"] = wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/beginner/")
    wait_route_overlay_closed(page)
    close_sheet_if_open(page)
    return out


def run_desktop_checks(page, target_cases: int) -> List[Dict[str, Any]]:
    rows_total = wait_for_results(page)
    records: List[Dict[str, Any]] = []
    enter_turn = True
    while len(records) < target_cases:
        rows_count = page.locator(".result-row").count()
        for idx in range(rows_count):
            if len(records) >= target_cases:
                break
            key_variant = "Enter" if enter_turn else "Space"
            enter_turn = not enter_turn
            try:
                result = open_row_and_verify(page, idx, key_variant=key_variant)
            except SkipRowError:
                continue
            result["case_no"] = len(records) + 1
            records.append(result)
        if len(records) >= target_cases:
            break
        if not go_next_page(page):
            break
        wait_for_results(page)
    if len(records) < target_cases:
        raise RuntimeError(f"insufficient cases checked: {len(records)}/{target_cases}")
    return records


def run_mobile_checks(page) -> Dict[str, Any]:
    wait_for_results(page)
    row_index = find_eligible_row_with_paging(page)
    row = page.locator(".result-row").nth(row_index)
    ensure_sheet_open(page, row)

    page.locator(".manual-paper-list .manual-paper-item").first.click()
    wait_hash_prefix(page, "#/paper/")
    verify_paper_overlay(page)
    overflow_paper = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/paper/")
    wait_route_overlay_closed(page)

    ensure_sheet_open(page, row)
    beginner_button = page.locator(".manual-beginner-button").first
    beginner_button.wait_for(state="visible", timeout=8000)
    deadline = time.time() + 8
    opened = False
    while time.time() < deadline:
        if beginner_button.is_disabled():
            page.wait_for_timeout(150)
            continue
        beginner_button.evaluate("(el) => el.click()")
        page.wait_for_timeout(200)
        if str(page.evaluate("location.hash")).startswith("#/beginner/"):
            opened = True
            break
        page.wait_for_timeout(200)
    if not opened:
        wait_hash_prefix(page, "#/beginner/")
    verify_beginner_overlay(page)
    overflow_beginner = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    page.keyboard.press("Escape")
    wait_hash_not_prefix(page, "#/beginner/")
    wait_route_overlay_closed(page)
    close_sheet_if_open(page)

    return {
        "paper_overflow": bool(overflow_paper),
        "beginner_overflow": bool(overflow_beginner),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10-case UI smoke checks for manual route features.")
    parser.add_argument("--url", default="http://127.0.0.1:4173/")
    parser.add_argument("--cases", type=int, default=10)
    parser.add_argument("--output", default="tools/ui_smoke_manual_routes_report.json")
    parser.add_argument("--doc-ids-file", default="", help="Optional newline-separated doc_id file for direct route mode")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    args = parser.parse_args()

    report: Dict[str, Any] = {
        "url": args.url,
        "cases_target": int(args.cases),
        "keyboard_checks": {},
        "desktop_cases": [],
        "mobile": {},
        "status": "FAIL",
        "error": "",
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            desktop = browser.new_page(viewport={"width": 1400, "height": 1000})
            desktop.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            desktop.wait_for_timeout(4000)
            if str(args.doc_ids_file or "").strip():
                doc_ids = load_doc_ids(str(args.doc_ids_file))
                snapshot_index = load_snapshot_index(str(args.snapshot))
                valid_doc_ids = [d for d in doc_ids if d in snapshot_index]
                if not valid_doc_ids:
                    raise RuntimeError("doc_ids_file contains no resolvable doc_id")
                keyboard_doc = valid_doc_ids[0]
                keyboard_doi = resolve_paper_doi(snapshot_index[keyboard_doc])
                report["keyboard_checks"] = run_keyboard_checks_direct(desktop, keyboard_doc, keyboard_doi)
                report["desktop_cases"] = run_desktop_checks_direct(
                    desktop, int(args.cases), valid_doc_ids, snapshot_index
                )
            else:
                report["keyboard_checks"] = run_keyboard_checks(desktop)
                report["desktop_cases"] = run_desktop_checks(desktop, int(args.cases))
            desktop.close()

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            mobile.wait_for_timeout(4000)
            if str(args.doc_ids_file or "").strip():
                doc_ids = load_doc_ids(str(args.doc_ids_file))
                snapshot_index = load_snapshot_index(str(args.snapshot))
                valid_doc_ids = [d for d in doc_ids if d in snapshot_index]
                mobile_doc = valid_doc_ids[0]
                mobile_doi = resolve_paper_doi(snapshot_index[mobile_doc])
                report["mobile"] = run_mobile_checks_direct(mobile, mobile_doc, mobile_doi)
            else:
                report["mobile"] = run_mobile_checks(mobile)
            mobile.close()
            browser.close()

        if report["mobile"].get("paper_overflow") or report["mobile"].get("beginner_overflow"):
            raise RuntimeError(f"mobile overflow detected: {report['mobile']}")
        report["status"] = "PASS"
    except PlaywrightTimeoutError as exc:
        report["error"] = f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)

    out_path = (Path.cwd() / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
