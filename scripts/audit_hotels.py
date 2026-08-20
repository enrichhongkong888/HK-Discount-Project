# -*- coding: utf-8 -*-
"""Daily audit for hotels.json — drop expired offers; keep structure intact.

Rules:
  - Remove offers where end_date < today (Asia/Hong_Kong calendar date).
  - Hotels with zero remaining offers are kept in the file but will be hidden
    by the frontend until new live offers are added.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOTELS = ROOT / "data" / "hotels.json"
HK_TZ = ZoneInfo("Asia/Hong_Kong")


def today_hk() -> date:
    return datetime.now(HK_TZ).date()


def parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def audit_hotels(payload: dict[str, Any] | list[Any], *, today: date) -> tuple[dict[str, Any], int, int]:
    if isinstance(payload, list):
        hotels = payload
        wrapper: dict[str, Any] = {"hotels": hotels}
    elif isinstance(payload, dict):
        wrapper = dict(payload)
        hotels = list(wrapper.get("hotels") or [])
    else:
        raise ValueError("hotels payload must be object or array")

    removed = 0
    kept_offers = 0
    cleaned: list[dict[str, Any]] = []
    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        offers_in = hotel.get("offers") if isinstance(hotel.get("offers"), list) else []
        offers_out: list[dict[str, Any]] = []
        for offer in offers_in:
            if not isinstance(offer, dict):
                continue
            end = parse_day(offer.get("end_date"))
            if end is None:
                continue
            if end < today:
                removed += 1
                continue
            # Official-website-first: keep / backfill source + booking link
            site = str(hotel.get("official_website") or "").strip()
            offer = dict(offer)
            offer["source_type"] = str(offer.get("source_type") or "official")
            if not str(offer.get("booking_url") or "").strip() and site:
                offer["booking_url"] = site
            offers_out.append(offer)
            kept_offers += 1
        cleaned.append({**hotel, "offers": offers_out})

    wrapper["hotels"] = cleaned
    wrapper["updated_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    wrapper["last_audit_date"] = today.isoformat()
    return wrapper, removed, kept_offers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit hotels.json — remove expired offers")
    parser.add_argument("--hotels", type=Path, default=DEFAULT_HOTELS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.hotels.exists():
        print(f"[audit_hotels] missing {args.hotels}")
        return 1

    raw = json.loads(args.hotels.read_text(encoding="utf-8"))
    today = today_hk()
    cleaned, removed, kept = audit_hotels(raw, today=today)
    print(f"[audit_hotels] today={today.isoformat()} removed_expired={removed} offers_kept={kept} hotels={len(cleaned.get('hotels') or [])}")
    if not args.dry_run:
        args.hotels.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
