# -*- coding: utf-8 -*-
"""Daily audit for hotels.json — drop expired offers; validate booking URLs.

Rules:
  - Remove offers where end_date < today (Asia/Hong_Kong calendar date).
  - Validate booking_url with HEAD then GET; on 404 / invalid, fall back to
    official_homepage or official_website so users never land on dead links.
  - Hotels with zero remaining offers stay in the file; frontend hides them.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOTELS = ROOT / "data" / "hotels.json"
DEFAULT_OTA = ROOT / "data" / "hotel_ota_offers.json"
HK_TZ = ZoneInfo("Asia/Hong_Kong")

# Soft OK: anti-bot / method-not-allowed — URL still exists for browsers.
SOFT_OK_STATUS = {401, 403, 405, 429}
BAD_STATUS = {404, 410, 451}


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


def site_origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/"


def hotel_fallback_url(hotel: dict[str, Any]) -> str:
    for key in ("official_homepage", "official_website"):
        value = str(hotel.get(key) or "").strip()
        if value:
            return value
    return ""


def check_url(client: Any, url: str) -> tuple[bool, int | None, str]:
    """Return (ok, status, note)."""
    text = str(url or "").strip()
    if not text or not text.startswith(("http://", "https://")):
        return False, None, "invalid_url"
    # Reject known overseas lookalikes when HK property should use .com.hk / group HK path
    lowered = text.lower()
    if "alvahotel.com" in lowered and "alva.com.hk" not in lowered:
        return False, 404, "overseas_lookalike"

    try:
        response = client.head(text)
        status = int(response.status_code)
        if status in BAD_STATUS:
            return False, status, "head_bad"
        if 200 <= status < 400 or status in SOFT_OK_STATUS:
            return True, status, "head_ok"
        # Some CDNs reject HEAD — fall through to GET
    except Exception:
        status = None

    try:
        response = client.get(text)
        status = int(response.status_code)
        if status in BAD_STATUS:
            return False, status, "get_bad"
        if 200 <= status < 400 or status in SOFT_OK_STATUS:
            return True, status, "get_ok"
        return False, status, "get_non_ok"
    except Exception as exc:
        return False, status, f"error:{type(exc).__name__}"


def load_ota_offers(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    by_hotel = raw.get("offers_by_hotel") if isinstance(raw, dict) else None
    if not isinstance(by_hotel, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for hotel_id, offers in by_hotel.items():
        if not isinstance(offers, list):
            continue
        cleaned = [dict(o) for o in offers if isinstance(o, dict) and o.get("id")]
        if cleaned:
            out[str(hotel_id)] = cleaned
    return out


def merge_ota_offers(hotels: list[dict[str, Any]], ota_by_hotel: dict[str, list[dict[str, Any]]]) -> int:
    """Replace curated OTA offers per hotel (by source_type=ota from file); keep official rows."""
    merged_count = 0
    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        hotel_id = str(hotel.get("id") or "")
        existing = hotel.get("offers") if isinstance(hotel.get("offers"), list) else []
        official_rows: list[dict[str, Any]] = []
        for offer in existing:
            if not isinstance(offer, dict):
                continue
            source = str(offer.get("source_type") or "official").lower()
            if source == "ota":
                continue
            row = dict(offer)
            row.setdefault("source_type", "official")
            row.setdefault("platform", "官網")
            official_rows.append(row)

        extras = ota_by_hotel.get(hotel_id) or []
        ota_rows: list[dict[str, Any]] = []
        for offer in extras:
            row = dict(offer)
            row["source_type"] = str(row.get("source_type") or "ota")
            if not row.get("platform"):
                row["platform"] = "Klook"
            ota_rows.append(row)
        hotel["offers"] = official_rows + ota_rows
        merged_count += len(ota_rows)
    return merged_count


def resolve_booking_url(
    client: Any | None,
    hotel: dict[str, Any],
    offer: dict[str, Any],
    *,
    cache: dict[str, tuple[bool, int | None, str]],
) -> tuple[str, str]:
    """Return (booking_url, action) where action is keep|fallback|filled."""
    site = hotel_fallback_url(hotel)
    current = str(offer.get("booking_url") or "").strip()
    source = str(offer.get("source_type") or "official").lower()
    is_ota = source == "ota" or bool(offer.get("is_affiliate"))

    if not current and site:
        return site, "filled"

    if client is None:
        return current or site, "keep_no_httpx"

    def cached_check(url: str) -> tuple[bool, int | None, str]:
        if url not in cache:
            cache[url] = check_url(client, url)
        return cache[url]

    ok, _status, _note = cached_check(current)
    if ok:
        return current, "keep"

    # OTA / affiliate links: keep the platform URL even when anti-bot blocks probes,
    # unless it is clearly a placeholder / invalid scheme.
    if is_ota and current.startswith(("http://", "https://")) and "YOUR_AFFILIATE_ID" not in current and "XXXXX" not in current:
        return current, "keep_ota"

    # Prefer official homepage / website, then domain origin
    candidates: list[str] = []
    for key in ("official_homepage", "official_website"):
        value = str(hotel.get(key) or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    origin = site_origin(site or current)
    if origin and origin not in candidates:
        candidates.append(origin)

    for candidate in candidates:
        if candidate == current:
            continue
        ok_c, _s, _n = cached_check(candidate)
        if ok_c:
            return candidate, "fallback"

    # Last resort: still point at hotel official site even if soft-fail
    return site or current, "fallback_unchecked"


def audit_hotels(
    payload: dict[str, Any] | list[Any],
    *,
    today: date,
    client: Any | None = None,
    ota_path: Path | None = DEFAULT_OTA,
) -> tuple[dict[str, Any], dict[str, int]]:
    if isinstance(payload, list):
        hotels = payload
        wrapper: dict[str, Any] = {"hotels": hotels}
    elif isinstance(payload, dict):
        wrapper = dict(payload)
        hotels = list(wrapper.get("hotels") or [])
    else:
        raise ValueError("hotels payload must be object or array")

    ota_by_hotel = load_ota_offers(ota_path) if ota_path else {}
    ota_merged = merge_ota_offers(hotels, ota_by_hotel)

    stats = {
        "removed_expired": 0,
        "offers_kept": 0,
        "url_keep": 0,
        "url_fallback": 0,
        "url_filled": 0,
        "ota_merged": ota_merged,
    }
    cache: dict[str, tuple[bool, int | None, str]] = {}
    cleaned: list[dict[str, Any]] = []

    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        hotel_out = dict(hotel)
        # Prefer homepage for hotel-level official_website when offers path was bad
        offers_in = hotel.get("offers") if isinstance(hotel.get("offers"), list) else []
        offers_out: list[dict[str, Any]] = []

        # Validate / normalize hotel.official_website itself
        site = str(hotel.get("official_website") or "").strip()
        home = str(hotel.get("official_homepage") or "").strip() or site_origin(site) or site
        if client is not None and site:
            ok_site, _st, _note = cache[site] if site in cache else check_url(client, site)
            cache.setdefault(site, (ok_site, _st, _note))
            if not ok_site:
                for candidate in (home, site_origin(site)):
                    if not candidate or candidate == site:
                        continue
                    ok_c, st_c, note_c = check_url(client, candidate)
                    cache[candidate] = (ok_c, st_c, note_c)
                    if ok_c:
                        hotel_out["official_website"] = candidate
                        hotel_out["official_homepage"] = home or candidate
                        break
                else:
                    hotel_out["official_homepage"] = home or site
            else:
                hotel_out["official_homepage"] = home or site_origin(site) or site
        elif home:
            hotel_out["official_homepage"] = home

        for offer in offers_in:
            if not isinstance(offer, dict):
                continue
            end = parse_day(offer.get("end_date") or offer.get("valid_to") or offer.get("expiry_date"))
            start = parse_day(offer.get("start_date") or offer.get("valid_from"))
            if end is None:
                continue
            if end < today:
                stats["removed_expired"] += 1
                continue

            offer_out = dict(offer)
            if start:
                offer_out["start_date"] = start.isoformat()
                offer_out["valid_from"] = start.isoformat()
            offer_out["end_date"] = end.isoformat()
            offer_out["valid_to"] = end.isoformat()
            offer_out["source_type"] = str(offer_out.get("source_type") or "official")
            booking, action = resolve_booking_url(client, hotel_out, offer_out, cache=cache)
            offer_out["booking_url"] = booking
            # Preserve OTA metadata
            if str(offer_out.get("source_type") or "").lower() == "ota":
                if offer_out.get("platform"):
                    offer_out["platform"] = str(offer_out["platform"])
                if "is_affiliate" in offer_out:
                    offer_out["is_affiliate"] = bool(offer_out["is_affiliate"])
                if isinstance(offer_out.get("bank_tags"), list):
                    offer_out["bank_tags"] = [str(t) for t in offer_out["bank_tags"] if str(t).strip()]
            if action in {"keep", "keep_no_httpx", "keep_ota"}:
                stats["url_keep"] += 1
            elif action == "filled":
                stats["url_filled"] += 1
            else:
                stats["url_fallback"] += 1
            offers_out.append(offer_out)
            stats["offers_kept"] += 1

        cleaned.append({**hotel_out, "offers": offers_out})

    wrapper["hotels"] = cleaned
    wrapper["updated_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    wrapper["last_audit_date"] = today.isoformat()
    return wrapper, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit hotels.json — expire + URL validate")
    parser.add_argument("--hotels", type=Path, default=DEFAULT_HOTELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-url-check", action="store_true", help="Only prune expired offers")
    args = parser.parse_args(argv)

    if not args.hotels.exists():
        print(f"[audit_hotels] missing {args.hotels}")
        return 1

    raw = json.loads(args.hotels.read_text(encoding="utf-8"))
    today = today_hk()

    client = None
    if not args.skip_url_check:
        if httpx is None:
            print("[audit_hotels] httpx missing — URL check skipped")
        else:
            client = httpx.Client(
                follow_redirects=True,
                timeout=20.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
            )

    try:
        cleaned, stats = audit_hotels(raw, today=today, client=client)
    finally:
        if client is not None:
            client.close()

    print(
        "[audit_hotels] "
        f"today={today.isoformat()} "
        f"removed_expired={stats['removed_expired']} "
        f"offers_kept={stats['offers_kept']} "
        f"url_keep={stats['url_keep']} "
        f"url_fallback={stats['url_fallback']} "
        f"url_filled={stats['url_filled']} "
        f"ota_merged={stats.get('ota_merged', 0)} "
        f"hotels={len(cleaned.get('hotels') or [])}"
    )
    if not args.dry_run:
        args.hotels.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
