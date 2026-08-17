# -*- coding: utf-8 -*-
"""Lifecycle state machine: classify → transition → prune expired offers.

States
------
- upcoming: today < start_date <= today + LIFECYCLE_PREVIEW_DAYS
  (equivalently: today <= start_date <= today+3 once active is checked first)
- active:   start_date <= today <= end_date  (auto-promoted from upcoming)
- expired:  today > end_date → **hard-deleted** from discounts.json / malls.json
- scheduled (start beyond preview) → also pruned (not retained in sync feed)

Run at the front of daily_sync so every day starts from a clean, reclassified set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from offer_tagging import (  # noqa: E402
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_FALLBACK,
    STATUS_SCHEDULED,
    STATUS_UPCOMING,
    classify_lifecycle_status,
)
from store_authenticity import (  # noqa: E402
    LIFECYCLE_PREVIEW_DAYS,
    parse_offer_date,
)

DEFAULT_DISCOUNTS = ROOT / "discounts.json"
DEFAULT_MALLS = ROOT / "malls.json"
REPORT_PATH = ROOT / "data" / "cache" / "lifecycle_report.json"


def _end_date(offer: dict[str, Any]) -> date | None:
    return parse_offer_date(offer.get("expiry_date") or offer.get("end_date"))


def _start_date(offer: dict[str, Any]) -> date | None:
    return parse_offer_date(offer.get("start_date"))


def resolve_status(offer: dict[str, Any], *, today: date) -> str:
    """Canonical state-machine transition for one offer/card."""
    return classify_lifecycle_status(offer, today=today, preview_days=LIFECYCLE_PREVIEW_DAYS)


def should_retain(status: str) -> bool:
    """Only active + upcoming (+ SPA fallback placeholders) stay in the feed."""
    return status in {STATUS_ACTIVE, STATUS_UPCOMING, STATUS_FALLBACK}


def apply_status_fields(offer: dict[str, Any], status: str) -> dict[str, Any]:
    offer = dict(offer)
    offer["status"] = status
    offer["lifecycle_status"] = status
    return offer


def prune_and_classify_offers(
    offers: list[dict[str, Any]],
    *,
    today: date,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Reclassify discounts offers and hard-delete expired / out-of-window rows."""
    kept: list[dict[str, Any]] = []
    stats = {
        "input": len(offers),
        "active": 0,
        "upcoming": 0,
        "pruned_expired": 0,
        "pruned_scheduled": 0,
        "pruned_invalid": 0,
        "transitioned_to_active": 0,
        "transitioned_to_upcoming": 0,
        "retained": 0,
    }
    preview_end = today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)
    for raw in offers:
        if not isinstance(raw, dict):
            stats["pruned_invalid"] += 1
            continue
        previous = str(raw.get("status") or raw.get("lifecycle_status") or "").strip()
        start = _start_date(raw)
        end = _end_date(raw)

        # Hard prune: expired (today > end_date) — never retain residue.
        if end is not None and today > end:
            stats["pruned_expired"] += 1
            continue
        if start is None or end is None:
            stats["pruned_invalid"] += 1
            continue
        # Beyond preview window (start > today + 3).
        if start > preview_end:
            stats["pruned_scheduled"] += 1
            continue

        status = resolve_status(raw, today=today)
        if status == STATUS_EXPIRED:
            stats["pruned_expired"] += 1
            continue
        if status == STATUS_SCHEDULED or not should_retain(status):
            stats["pruned_scheduled"] += 1
            continue

        updated = apply_status_fields(raw, status)
        if status == STATUS_ACTIVE:
            stats["active"] += 1
            if previous == STATUS_UPCOMING:
                stats["transitioned_to_active"] += 1
        elif status == STATUS_UPCOMING:
            stats["upcoming"] += 1
            if previous and previous != STATUS_UPCOMING:
                stats["transitioned_to_upcoming"] += 1
        kept.append(updated)

    stats["retained"] = len(kept)
    return kept, stats


def prune_and_classify_malls(
    malls_payload: dict[str, Any],
    *,
    today: date,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Hard-delete expired SPA cards and refresh status / upcoming_offers buckets."""
    stats = {
        "mall_cards_in": 0,
        "store_cards_in": 0,
        "pruned_expired": 0,
        "pruned_scheduled": 0,
        "active": 0,
        "upcoming": 0,
        "retained_mall_cards": 0,
        "retained_store_cards": 0,
    }
    preview_end = today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)
    districts_out: list[dict[str, Any]] = []

    def _keep_card(card: dict[str, Any], *, is_store: bool) -> dict[str, Any] | None:
        if card.get("type") == "fallback":
            return apply_status_fields(card, STATUS_FALLBACK)
        start = _start_date(card)
        end = _end_date(card)
        if end is not None and today > end:
            stats["pruned_expired"] += 1
            return None
        if start is None or end is None:
            stats["pruned_scheduled"] += 1
            return None
        if start > preview_end:
            stats["pruned_scheduled"] += 1
            return None
        status = resolve_status(card, today=today)
        if status == STATUS_EXPIRED:
            stats["pruned_expired"] += 1
            return None
        if status == STATUS_SCHEDULED or not should_retain(status):
            stats["pruned_scheduled"] += 1
            return None
        updated = apply_status_fields(card, status)
        if status == STATUS_ACTIVE:
            stats["active"] += 1
        elif status == STATUS_UPCOMING:
            stats["upcoming"] += 1
        return updated

    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        malls_out: list[dict[str, Any]] = []
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall = dict(mall)
            mall_offers: list[dict[str, Any]] = []
            store_offers: list[dict[str, Any]] = []

            for card in mall.get("mall_offers") or []:
                if not isinstance(card, dict):
                    continue
                stats["mall_cards_in"] += 1
                kept = _keep_card(card, is_store=False)
                if kept is not None:
                    mall_offers.append(kept)

            for card in mall.get("store_offers") or []:
                if not isinstance(card, dict):
                    continue
                stats["store_cards_in"] += 1
                kept = _keep_card(card, is_store=True)
                if kept is not None:
                    store_offers.append(kept)

            upcoming_offers = [
                c
                for c in mall_offers + store_offers
                if c.get("type") != "fallback"
                and (c.get("status") or c.get("lifecycle_status")) == STATUS_UPCOMING
            ]
            active_offers = [
                c
                for c in mall_offers + store_offers
                if c.get("type") != "fallback"
                and (c.get("status") or c.get("lifecycle_status")) == STATUS_ACTIVE
            ]
            mall["mall_offers"] = mall_offers
            mall["store_offers"] = store_offers
            mall["upcoming_offers"] = upcoming_offers
            mall["upcoming_count"] = len(upcoming_offers)
            mall["upcoming_offer_total"] = sum(
                int(
                    c.get("consolidated_offer_count")
                    or (1 + len(c.get("sub_offers") or []))
                )
                for c in upcoming_offers
            )
            mall["active_count"] = len(active_offers)
            mall["active_offer_total"] = sum(
                int(
                    c.get("consolidated_offer_count")
                    or (1 + len(c.get("sub_offers") or []))
                )
                for c in active_offers
            )
            stats["retained_mall_cards"] += len(
                [c for c in mall_offers if c.get("type") != "fallback"]
            )
            stats["retained_store_cards"] += len(store_offers)
            malls_out.append(mall)
        districts_out.append({**district, "malls": malls_out})

    out = {
        **malls_payload,
        "districts": districts_out,
        "lifecycle_preview_days": LIFECYCLE_PREVIEW_DAYS,
        "lifecycle_managed_at": datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
        "lifecycle_today": today.isoformat(),
    }
    return out, stats


def maybe_purge_database() -> dict[str, int] | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        import psycopg
    except ImportError:
        print("[lifecycle] psycopg not installed; skip DB purge")
        return None
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM purge_expired_discounts()")
            daily_deleted, expired_deleted = cursor.fetchone()
        connection.commit()
    print(
        f"[lifecycle] database purged daily_specials={daily_deleted} "
        f"expired={expired_deleted}"
    )
    return {"daily_deleted": int(daily_deleted), "expired_deleted": int(expired_deleted)}


def run(
    *,
    discounts_path: Path,
    malls_path: Path,
    today: date | None = None,
    write: bool = True,
) -> dict[str, Any]:
    today = today or date.today()
    report: dict[str, Any] = {
        "today": today.isoformat(),
        "preview_days": LIFECYCLE_PREVIEW_DAYS,
        "discounts": {},
        "malls": {},
        "database": None,
    }

    if discounts_path.exists():
        payload = json.loads(discounts_path.read_text(encoding="utf-8"))
        offers = [o for o in (payload.get("offers") or []) if isinstance(o, dict)]
        kept, dstats = prune_and_classify_offers(offers, today=today)
        report["discounts"] = dstats
        if write:
            payload = {**payload, "offers": kept}
            payload["lifecycle_managed_at"] = (
                datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            )
            discounts_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(
            f"[lifecycle] discounts input={dstats['input']} retained={dstats['retained']} "
            f"active={dstats['active']} upcoming={dstats['upcoming']} "
            f"pruned_expired={dstats['pruned_expired']} "
            f"pruned_scheduled={dstats['pruned_scheduled']} "
            f"→_active={dstats['transitioned_to_active']}"
        )
    else:
        print(f"[lifecycle] skip missing {discounts_path}")

    if malls_path.exists():
        malls_payload = json.loads(malls_path.read_text(encoding="utf-8"))
        updated, mstats = prune_and_classify_malls(malls_payload, today=today)
        report["malls"] = mstats
        if write:
            malls_path.write_text(
                json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(
            f"[lifecycle] malls pruned_expired={mstats['pruned_expired']} "
            f"pruned_scheduled={mstats['pruned_scheduled']} "
            f"active={mstats['active']} upcoming={mstats['upcoming']} "
            f"store_cards={mstats['retained_store_cards']}"
        )
    else:
        print(f"[lifecycle] skip missing {malls_path}")

    report["database"] = maybe_purge_database()

    if write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[lifecycle] report → {REPORT_PATH}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="生命週期狀態機：轉態 + 過期硬刪")
    parser.add_argument("--discounts", type=Path, default=DEFAULT_DISCOUNTS)
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument(
        "--today",
        type=str,
        default="",
        help="Override today as YYYY-MM-DD (tests)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Classify/prune stats only")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else date.today()
    run(
        discounts_path=args.discounts,
        malls_path=args.malls,
        today=today,
        write=not args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
