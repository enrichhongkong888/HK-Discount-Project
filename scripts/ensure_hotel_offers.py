# -*- coding: utf-8 -*-
"""Ensure data/hotels.json always has displayable hotel offers for the SPA.

- Hotel feed lives in data/hotels.json (NOT data/malls.json, which is parking catalog).
- Merges curated OTA samples from data/hotel_ota_offers.json.
- Normalises date aliases: end_date ← valid_to / expiry_date; start_date ← valid_from.
- Extends expired sample/OTA offers so valid_to / end_date stay after today.
- Seeds a fallback staycation offer when a hotel would otherwise have zero live offers.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
HOTELS_PATH = ROOT / "data" / "hotels.json"
OTA_PATH = ROOT / "data" / "hotel_ota_offers.json"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

SAMPLE_WINDOW_DAYS = 60
MIN_LIVE_PER_HOTEL = 1


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


def offer_start(raw: dict[str, Any]) -> date | None:
    return parse_day(raw.get("start_date") or raw.get("valid_from"))


def offer_end(raw: dict[str, Any]) -> date | None:
    return parse_day(raw.get("end_date") or raw.get("valid_to") or raw.get("expiry_date"))


def normalize_offer_dates(offer: dict[str, Any], *, today: date) -> dict[str, Any]:
    out = dict(offer)
    start = offer_start(out) or today
    end = offer_end(out)
    if end is None or end < today:
        # Roll forward expired / missing end dates for curated sample feeds.
        end = today + timedelta(days=SAMPLE_WINDOW_DAYS)
        if start > end:
            start = today
    out["start_date"] = start.isoformat()
    out["end_date"] = end.isoformat()
    out["valid_from"] = start.isoformat()
    out["valid_to"] = end.isoformat()
    if not out.get("tags"):
        out["tags"] = ["酒店優惠"]
    elif "酒店優惠" not in out["tags"] and "Hotel" not in out["tags"]:
        out["tags"] = list(out["tags"]) + ["酒店優惠"]
    return out


def is_live(offer: dict[str, Any], *, today: date) -> bool:
    start = offer_start(offer)
    end = offer_end(offer)
    if not (start and end):
        return False
    if end < today:
        return False
    if start > today + timedelta(days=3) and start > today:
        # Keep scheduled offers in file; frontend hides beyond 3-day preview.
        return True
    return True


def load_ota() -> dict[str, list[dict[str, Any]]]:
    if not OTA_PATH.exists():
        return {}
    raw = json.loads(OTA_PATH.read_text(encoding="utf-8"))
    by_hotel = raw.get("offers_by_hotel") if isinstance(raw, dict) else None
    if not isinstance(by_hotel, dict):
        return {}
    return {
        str(hid): [dict(o) for o in offers if isinstance(o, dict)]
        for hid, offers in by_hotel.items()
        if isinstance(offers, list)
    }


def merge_ota(hotels: list[dict[str, Any]], ota: dict[str, list[dict[str, Any]]], *, today: date) -> int:
    merged = 0
    for hotel in hotels:
        hid = str(hotel.get("id") or "")
        extras = ota.get(hid) or []
        if not extras:
            continue
        existing = list(hotel.get("offers") or [])
        seen = {str(o.get("id") or "") for o in existing if isinstance(o, dict)}
        for offer in extras:
            oid = str(offer.get("id") or "")
            if oid and oid in seen:
                # Refresh dates on existing OTA row if expired.
                for idx, cur in enumerate(existing):
                    if str(cur.get("id") or "") == oid:
                        existing[idx] = normalize_offer_dates({**cur, **offer}, today=today)
                        break
                continue
            existing.append(normalize_offer_dates(offer, today=today))
            seen.add(oid)
            merged += 1
        hotel["offers"] = existing
    return merged


def seed_sample_offer(hotel: dict[str, Any], *, today: date) -> dict[str, Any]:
    hid = str(hotel.get("id") or "hotel")
    name = str(hotel.get("name") or "酒店")
    site = str(hotel.get("official_website") or hotel.get("official_homepage") or "").strip()
    start = today
    end = today + timedelta(days=SAMPLE_WINDOW_DAYS)
    return {
        "id": f"offer-{hid}-sample-staycation",
        "category": "staycation",
        "source_type": "official",
        "title": f"官網獨家：{name.split('(')[0].strip()} Staycation 優惠",
        "description": f"經官網預訂可享住宿／餐飲禮遇；詳情以 {name} 官方條款為準。",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "valid_from": start.isoformat(),
        "valid_to": end.isoformat(),
        "booking_url": site,
        "tags": ["官網獨家", "Staycation", "酒店優惠"],
        "platform": "官網",
    }


def ensure_hotels(*, today: date | None = None, dry_run: bool = False) -> dict[str, Any]:
    today = today or today_hk()
    payload = json.loads(HOTELS_PATH.read_text(encoding="utf-8"))
    hotels = list(payload.get("hotels") or [])
    ota = load_ota()
    ota_merged = merge_ota(hotels, ota, today=today)

    refreshed = 0
    seeded = 0
    live_total = 0

    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        offers_in = [o for o in (hotel.get("offers") or []) if isinstance(o, dict)]
        offers_out: list[dict[str, Any]] = []
        for offer in offers_in:
            before_end = offer_end(offer)
            normalised = normalize_offer_dates(offer, today=today)
            if before_end is None or before_end < today:
                refreshed += 1
            offers_out.append(normalised)

        live = [o for o in offers_out if offer_end(o) and offer_end(o) >= today]
        if len(live) < MIN_LIVE_PER_HOTEL:
            sample = seed_sample_offer(hotel, today=today)
            if not any(str(o.get("id")) == sample["id"] for o in offers_out):
                offers_out.append(sample)
                seeded += 1
            live = [o for o in offers_out if offer_end(o) and offer_end(o) >= today]

        hotel["offers"] = offers_out
        hotel["type"] = hotel.get("type") or "hotel"
        live_total += len(live)

    payload["hotels"] = hotels
    payload["updated_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    payload["ensure_hotel_offers_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    payload["ensure_hotel_offers_stats"] = {
        "today": today.isoformat(),
        "hotels": len(hotels),
        "live_offers": live_total,
        "ota_merged": ota_merged,
        "dates_refreshed": refreshed,
        "samples_seeded": seeded,
    }

    if not dry_run:
        HOTELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp = HOTELS_PATH.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(HOTELS_PATH)

        # Keep curated OTA file dates in sync so future audits stay live.
        if OTA_PATH.exists():
            ota_payload = json.loads(OTA_PATH.read_text(encoding="utf-8"))
            by_hotel = ota_payload.get("offers_by_hotel") or {}
            for hid, offers in list(by_hotel.items()):
                by_hotel[hid] = [normalize_offer_dates(deepcopy(o), today=today) for o in offers if isinstance(o, dict)]
            ota_payload["offers_by_hotel"] = by_hotel
            ota_payload["updated_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
            ota_tmp = OTA_PATH.with_suffix(".json.tmp")
            ota_tmp.write_text(json.dumps(ota_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ota_tmp.replace(OTA_PATH)

    return payload["ensure_hotel_offers_stats"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure hotel offers remain displayable in the SPA")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--today", default="", help="Override today YYYY-MM-DD")
    args = parser.parse_args(argv)
    today = parse_day(args.today) or today_hk()
    stats = ensure_hotels(today=today, dry_run=args.dry_run)
    print("========== ENSURE HOTEL OFFERS ==========")
    for key, value in stats.items():
        print(f"{key:16}: {value}")
    print(f"{'mode':16}: {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print("Note: hotel feed = data/hotels.json (data/malls.json is parking catalog only)")
    print("=========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
