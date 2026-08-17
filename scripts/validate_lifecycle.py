# -*- coding: utf-8 -*-
"""Validate offer lifecycle invariants + strict 6-column store structure.

Fails (exit 1) when any of:
- expired residue (today > end_date)
- placeholders
- missing/invalid 6-column fields on store offers / SPA store cards
- incomplete 74-mall store or upcoming coverage
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from offer_tagging import classify_lifecycle_status  # noqa: E402
from scrapers.merchant_quota import ratio_on_target  # noqa: E402
from scrapers.merchant_taxonomy import (  # noqa: E402
    MERCHANT_CHAIN,
    MERCHANT_INDEPENDENT,
    classify_merchant_type,
)
from store_authenticity import (  # noqa: E402
    LIFECYCLE_PREVIEW_DAYS,
    PLACEHOLDER_TEXTS,
    authenticity_failures,
    is_authentic_store_payload,
    is_within_lifecycle_window,
    lifecycle_failures,
    parse_offer_date,
    six_column_failures,
)

TARGET_INDEPENDENT_RATIO = 0.70
RATIO_TOLERANCE = 0.02


def _scan_placeholders(obj: dict, fields: tuple[str, ...]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for field in fields:
        value = str(obj.get(field) or "").strip()
        if value in PLACEHOLDER_TEXTS:
            hits.append((field, value))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證 discounts.json / malls.json 生命週期與六欄結構")
    parser.add_argument("--discounts", type=Path, default=Path("discounts.json"))
    parser.add_argument("--malls", type=Path, default=Path("malls.json"))
    args = parser.parse_args()

    today = date.today()
    now = datetime.now(timezone.utc).astimezone()
    payload = json.loads(args.discounts.read_text(encoding="utf-8"))
    offers = payload.get("offers", [])
    errors: list[str] = []
    evergreen = activeish = store_offers = 0
    placeholder_hits = 0
    expired_residue = 0
    six_col_failures = 0

    for offer in offers:
        title = offer.get("title", "?")
        start = parse_offer_date(offer.get("start_date"))
        end = parse_offer_date(offer.get("expiry_date") or offer.get("end_date"))
        is_evergreen = bool(offer.get("is_evergreen"))
        is_daily = bool(offer.get("is_daily_special"))
        offer_type = offer.get("offer_type", "mall")

        # Absolute ban on expired residue in discounts.json
        if end is not None and today > end:
            expired_residue += 1
            errors.append(f"expired residue in discounts: {title} end={end.isoformat()}")
            continue

        if offer_type == "store":
            store_offers += 1
            auth = authenticity_failures(offer, today=today)
            if auth:
                errors.append(
                    f"store offer authenticity/lifecycle failed {auth}: "
                    f"{title} @ {offer.get('mall_name')}"
                )
            six = six_column_failures(offer, today=today, require_status=True)
            if six:
                six_col_failures += 1
                errors.append(
                    f"store offer 6-column failed {six}: "
                    f"{title} @ {offer.get('mall_name')}"
                )
            for field, value in _scan_placeholders(
                offer,
                ("store_name", "floor", "shop_number", "phone", "details", "discount_info"),
            ):
                placeholder_hits += 1
                errors.append(
                    f"store offer placeholder in {field}={value!r}: "
                    f"{title} @ {offer.get('mall_name')}"
                )

            status = classify_lifecycle_status(offer, today=today)
            baked = str(offer.get("status") or offer.get("lifecycle_status") or "").strip()
            if baked and baked != status:
                errors.append(
                    f"status mismatch baked={baked!r} computed={status!r}: "
                    f"{title} @ {offer.get('mall_name')}"
                )

        # Lifecycle applies to every retained offer, including evergreen.
        life = lifecycle_failures(offer, today=today)
        if life:
            errors.append(f"lifecycle failed {life}: {title}")
            continue

        if is_evergreen:
            evergreen += 1

        if is_daily:
            try:
                created = datetime.fromisoformat(str(offer["created_at"]))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if now > created + timedelta(days=1):
                    errors.append(f"stale daily special retained: {title}")
            except (KeyError, ValueError):
                errors.append(f"daily special missing created_at: {title}")

        if start and end and is_within_lifecycle_window(
            start.isoformat(), end.isoformat(), today=today
        ):
            if start <= today <= end or today < start <= today + timedelta(
                days=LIFECYCLE_PREVIEW_DAYS
            ):
                activeish += 1

    malls_payload = json.loads(args.malls.read_text(encoding="utf-8")) if args.malls.exists() else {}
    mall_count = sum(len(d.get("malls", [])) for d in malls_payload.get("districts", []))
    fallback = 0
    malls_with_stores = 0
    spa_store_cards = 0
    for district in malls_payload.get("districts", []):
        for mall in district.get("malls", []):
            cards = mall.get("mall_offers", []) + mall.get("store_offers", [])
            store_cards = mall.get("store_offers", [])
            spa_store_cards += len(store_cards)
            if store_cards:
                malls_with_stores += 1
            if not any(card.get("type") != "fallback" for card in cards):
                fallback += 1
            for card in list(mall.get("mall_offers") or []) + store_cards:
                end = parse_offer_date(card.get("end_date") or card.get("expiry_date"))
                if card.get("type") != "fallback" and end is not None and today > end:
                    expired_residue += 1
                    errors.append(
                        f"expired residue in malls.json: {mall.get('mall_name')} / "
                        f"{card.get('offer_title') or card.get('store_name')} end={end.isoformat()}"
                    )

            for card in store_cards:
                if not is_authentic_store_payload(card, today=today):
                    errors.append(
                        f"SPA store card authenticity/lifecycle failed: {mall.get('mall_name')} / "
                        f"{card.get('offer_title') or card.get('store_name')}"
                    )
                six = six_column_failures(card, today=today, require_status=True)
                if six:
                    six_col_failures += 1
                    errors.append(
                        f"SPA store card 6-column failed {six}: {mall.get('mall_name')} / "
                        f"{card.get('offer_title') or card.get('store_name')}"
                    )
                for field, value in _scan_placeholders(
                    card, ("store_name", "floor", "shop_number", "phone", "details")
                ):
                    placeholder_hits += 1
                    errors.append(
                        f"SPA placeholder {field}={value!r}: {mall.get('mall_name')}"
                    )
                if not is_within_lifecycle_window(
                    card.get("start_date"),
                    card.get("end_date") or card.get("expiry_date"),
                    today=today,
                ):
                    errors.append(
                        f"SPA store card outside lifecycle window: {mall.get('mall_name')} / "
                        f"{card.get('offer_title') or card.get('store_name')}"
                    )

    print(
        f"offers={len(offers)} evergreen={evergreen} store_offers={store_offers} "
        f"active_or_preview≈{activeish} malls={mall_count} malls_with_stores={malls_with_stores} "
        f"spa_store_cards={spa_store_cards} fallback={fallback} placeholders={placeholder_hits} "
        f"expired_residue={expired_residue} six_column_failures={six_col_failures}"
    )

    # Upcoming (3-day) coverage gate: every mall must expose upcoming_offers > 0.
    malls_missing_upcoming: list[str] = []
    for district in malls_payload.get("districts", []):
        for mall in district.get("malls", []):
            upcoming = mall.get("upcoming_offers")
            if isinstance(upcoming, list):
                count = len(upcoming)
            else:
                count = 0
                for card in list(mall.get("mall_offers") or []) + list(
                    mall.get("store_offers") or []
                ):
                    if card.get("type") == "fallback":
                        continue
                    start = parse_offer_date(card.get("start_date"))
                    if (
                        start
                        and not card.get("is_evergreen")
                        and today < start <= today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)
                    ):
                        count += 1
            if count <= 0:
                malls_missing_upcoming.append(str(mall.get("mall_name") or "?"))
    if malls_missing_upcoming:
        errors.append(
            f"upcoming coverage incomplete: {mall_count - len(malls_missing_upcoming)}/{mall_count} "
            f"malls have upcoming_offers>0 (missing e.g. {malls_missing_upcoming[:5]})"
        )
    else:
        print(f"upcoming_coverage={mall_count}/{mall_count} (all malls upcoming_offers>0)")

    # Merchant mix gate: ~70% independent on unique SPA store cards (one per shop).
    malls_off_quota: list[str] = []
    duplicate_shop_hits: list[str] = []
    for district in malls_payload.get("districts", []):
        for mall in district.get("malls", []):
            indie = chain = 0
            seen_shops: set[tuple[str, str, str]] = set()
            for card in mall.get("store_offers") or []:
                if card.get("type") == "fallback":
                    continue
                status = str(card.get("status") or card.get("lifecycle_status") or "")
                if status not in {"active", "upcoming"}:
                    continue
                shop_key = (
                    str(card.get("store_name") or "").strip(),
                    str(card.get("floor") or "").strip(),
                    str(card.get("shop_number") or "").strip(),
                )
                if not all(shop_key):
                    continue
                if shop_key in seen_shops:
                    duplicate_shop_hits.append(
                        f"{mall.get('mall_name')}:{shop_key[0]}@{shop_key[1]}/{shop_key[2]}"
                    )
                    continue
                seen_shops.add(shop_key)
                mtype = str(card.get("merchant_type") or "").strip()
                if mtype not in {MERCHANT_INDEPENDENT, MERCHANT_CHAIN}:
                    mtype = classify_merchant_type(
                        str(card.get("store_name") or ""),
                        source_name=str(card.get("source_name") or ""),
                    )
                if mtype == MERCHANT_INDEPENDENT:
                    indie += 1
                elif mtype == MERCHANT_CHAIN:
                    chain += 1
            total = indie + chain
            if total <= 0:
                malls_off_quota.append(str(mall.get("mall_name") or "?"))
                continue
            if not ratio_on_target(indie, total, tolerance=RATIO_TOLERANCE):
                ratio = indie / total
                malls_off_quota.append(
                    f"{mall.get('mall_name')}({indie}/{total}={ratio:.0%})"
                )
    if duplicate_shop_hits:
        errors.append(
            f"duplicate store cards must be 0 (found {len(duplicate_shop_hits)}; "
            f"e.g. {duplicate_shop_hits[:5]})"
        )
    if malls_off_quota:
        errors.append(
            f"merchant quota off-target (want {TARGET_INDEPENDENT_RATIO:.0%} independent): "
            f"{mall_count - len(malls_off_quota)}/{mall_count} ok; "
            f"examples {malls_off_quota[:8]}"
        )
    else:
        print(
            f"merchant_quota={mall_count}/{mall_count} "
            f"(~{TARGET_INDEPENDENT_RATIO:.0%} independent / {1 - TARGET_INDEPENDENT_RATIO:.0%} chain, unique shops)"
        )

    if expired_residue:
        errors.append(f"expired residue must be 0 (found {expired_residue})")
    if placeholder_hits:
        errors.append(f"placeholders must be 0 (found {placeholder_hits})")
    if six_col_failures:
        errors.append(f"6-column failures must be 0 (found {six_col_failures})")
    if mall_count and malls_with_stores < mall_count:
        errors.append(
            f"store coverage incomplete: {malls_with_stores}/{mall_count} malls have store offers"
        )
    if errors:
        print(f"LIFECYCLE VALIDATION FAILED ({len(errors)} issues):", file=sys.stderr)
        for item in errors[:40]:
            print(f"  - {item}", file=sys.stderr)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more", file=sys.stderr)
        return 1

    print("lifecycle validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
