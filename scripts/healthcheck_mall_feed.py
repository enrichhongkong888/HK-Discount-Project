# -*- coding: utf-8 -*-
"""Validate SPA mall feed JSON after OpenRice sync (dates, titles, conflicts, expiry)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
EXPECTED_MALLS = 74
OFFER_KINDS = (
    ("dining_offers", ("title", "offer_title", "restaurant_name")),
    ("store_offers", ("offer_title", "title", "store_name")),
    ("mall_offers", ("title", "offer_title")),
)


def _today_hk() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _offer_end(offer: dict[str, Any]) -> date | None:
    return _parse_date(offer.get("end_date") or offer.get("expiry_date") or offer.get("valid_to"))


def _offer_title(offer: dict[str, Any], fields: tuple[str, ...]) -> str:
    for key in fields:
        val = offer.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def load_feed(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    if not path.exists():
        return None, [f"missing file: {path.relative_to(ROOT)}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in CONFLICT_MARKERS:
        if marker in text:
            issues.append(f"conflict marker {marker!r} in {path.relative_to(ROOT)}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        issues.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return None, issues
    if not isinstance(payload, dict):
        issues.append(f"{path.relative_to(ROOT)} root must be object")
        return None, issues
    if not isinstance(payload.get("districts"), list):
        issues.append(f"{path.relative_to(ROOT)} missing districts[] (not SPA mall feed)")
        return None, issues
    return payload, issues


def validate_feed(payload: dict[str, Any], *, today: date, label: str) -> list[str]:
    issues: list[str] = []
    districts = payload.get("districts") or []
    mall_count = 0
    expired: list[str] = []
    null_titles: list[str] = []
    bad_dates: list[str] = []

    for district in districts:
        if not isinstance(district, dict):
            issues.append(f"{label}: non-object district entry")
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_count += 1
            mall_name = str(mall.get("mall_name") or "?")
            for kind, title_fields in OFFER_KINDS:
                for idx, offer in enumerate(mall.get(kind) or []):
                    if not isinstance(offer, dict):
                        issues.append(f"{label}: {mall_name} {kind}[{idx}] not object")
                        continue
                    title = _offer_title(offer, title_fields)
                    if not title:
                        null_titles.append(f"{mall_name} {kind}[{idx}]")
                    for field in ("start_date", "end_date", "valid_from", "valid_to", "expiry_date"):
                        val = offer.get(field)
                        if val is None or val == "":
                            continue
                        if _parse_date(val) is None:
                            bad_dates.append(f"{mall_name} {kind}[{idx}] {field}={val!r}")
                    end = _offer_end(offer)
                    if end and end < today:
                        expired.append(f"{mall_name} {kind}[{idx}] end={end.isoformat()} title={title[:40]}")

    if mall_count != EXPECTED_MALLS:
        issues.append(f"{label}: expected {EXPECTED_MALLS} malls, found {mall_count}")
    if expired:
        issues.append(f"{label}: {len(expired)} expired offer(s) remain")
        issues.extend(f"  - {row}" for row in expired[:15])
        if len(expired) > 15:
            issues.append(f"  ... and {len(expired) - 15} more")
    if null_titles:
        issues.append(f"{label}: {len(null_titles)} offer(s) with null/empty title")
        issues.extend(f"  - {row}" for row in null_titles[:10])
    if bad_dates:
        issues.append(f"{label}: {len(bad_dates)} invalid date field(s)")
        issues.extend(f"  - {row}" for row in bad_dates[:10])
    return issues


def check_sync_stats(path: Path, *, today: date) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"missing sync stats: {path.relative_to(ROOT)}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid sync stats JSON: {exc}"]
    stats = (payload or {}).get("stats") or {}
    prune = stats.get("prune") or {}
    if str(payload.get("today") or stats.get("today") or "")[:10] != today.isoformat():
        issues.append(f"sync stats today mismatch (expected {today.isoformat()})")
    if not isinstance(prune, dict):
        issues.append("sync stats missing prune object")
    else:
        for key in ("pruned_expired", "pruned_dead_url", "pruned_scheduled", "pruned_generic"):
            if key not in prune:
                issues.append(f"sync stats prune missing {key}")
    return issues


def check_cache_backup(main: Path, backup: Path) -> list[str]:
    issues: list[str] = []
    if not backup.exists():
        return [f"cache backup missing: {backup.relative_to(ROOT)}"]
    if main.exists() and backup.exists():
        if main.stat().st_size != backup.stat().st_size:
            issues.append(
                f"cache size mismatch: {main.relative_to(ROOT)} ({main.stat().st_size}) "
                f"vs {backup.relative_to(ROOT)} ({backup.stat().st_size})"
            )
        main_payload, _ = load_feed(main)
        backup_payload, _ = load_feed(backup)
        if main_payload and backup_payload:
            main_malls = sum(len(d.get("malls") or []) for d in main_payload.get("districts") or [])
            backup_malls = sum(len(d.get("malls") or []) for d in backup_payload.get("districts") or [])
            if main_malls != backup_malls:
                issues.append(f"cache mall count mismatch: main={main_malls} backup={backup_malls}")
    return issues


def check_frontend_self_healing(app_js: Path) -> list[str]:
    issues: list[str] = []
    if not app_js.exists():
        return [f"missing {app_js.relative_to(ROOT)}"]
    text = app_js.read_text(encoding="utf-8")
    if "./data/cache/malls.json" not in text:
        issues.append("app.js missing cache malls.json in feed sources")
    if "./malls.json" not in text:
        issues.append("app.js missing ./malls.json in feed sources")
    if "fetchMallFeed" not in text:
        issues.append("app.js missing fetchMallFeed()")
    if "DINING_IMAGE_FALLBACK" not in text:
        issues.append("app.js missing DINING_IMAGE_FALLBACK")
    if "imgOnErrorAttr" not in text:
        issues.append("app.js missing imgOnErrorAttr fallback helper")
    if not re.search(r"function\s+diningOfferImageUrl", text):
        issues.append("app.js missing diningOfferImageUrl()")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Health-check mall feed JSON and sync artifacts")
    parser.add_argument("--today", default="", help="Override today (YYYY-MM-DD)")
    parser.add_argument("--main", default="malls.json", help="Primary SPA feed path")
    parser.add_argument("--cache", default="data/cache/malls.json", help="Cache backup path")
    parser.add_argument("--stats", default="data/cache/daily_openrice_offers.json", help="Sync stats path")
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today[:10]) if args.today else _today_hk()
    main_path = ROOT / args.main
    cache_path = ROOT / args.cache
    stats_path = ROOT / args.stats
    parking_path = ROOT / "data" / "malls.json"

    all_issues: list[str] = []
    print("========== MALL FEED HEALTHCHECK ==========")
    print(f"Today           : {today.isoformat()}")
    print(f"Main feed       : {main_path.relative_to(ROOT)}")
    print(f"Cache backup    : {cache_path.relative_to(ROOT)}")
    print(f"Sync stats      : {stats_path.relative_to(ROOT)}")
    print("===========================================")

    all_issues.extend(check_frontend_self_healing(ROOT / "frontend" / "app.js"))
    all_issues.extend(check_sync_stats(stats_path, today=today))

    main_payload, load_issues = load_feed(main_path)
    all_issues.extend(load_issues)
    if main_payload:
        all_issues.extend(validate_feed(main_payload, today=today, label=str(main_path.relative_to(ROOT))))

    cache_payload, cache_load_issues = load_feed(cache_path)
    all_issues.extend(cache_load_issues)
    if cache_payload:
        all_issues.extend(validate_feed(cache_payload, today=today, label=str(cache_path.relative_to(ROOT))))

    all_issues.extend(check_cache_backup(main_path, cache_path))

    if parking_path.exists():
        parking_text = parking_path.read_text(encoding="utf-8", errors="replace")
        for marker in CONFLICT_MARKERS:
            if marker in parking_text:
                all_issues.append(f"conflict marker in data/malls.json (parking catalog)")
        try:
            json.loads(parking_text)
        except json.JSONDecodeError as exc:
            all_issues.append(f"invalid JSON in data/malls.json: {exc}")
    else:
        all_issues.append("data/malls.json parking catalog missing")

    if stats_path.exists():
        try:
            stats_payload = json.loads(stats_path.read_text(encoding="utf-8"))
            prune = ((stats_payload or {}).get("stats") or {}).get("prune") or {}
            print(f"Prune stats     : {json.dumps(prune, ensure_ascii=False)}")
        except json.JSONDecodeError:
            pass

    if all_issues:
        print("\n[FAIL] Issues found:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

    print("\n[PASS] All health checks passed.")
    if main_payload:
        malls = sum(len(d.get("malls") or []) for d in main_payload.get("districts") or [])
        dining = sum(
            len(m.get("dining_offers") or [])
            for d in main_payload.get("districts") or []
            for m in d.get("malls") or []
        )
        print(f"Summary         : {malls} malls, {dining} dining_offers, cache backup OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
