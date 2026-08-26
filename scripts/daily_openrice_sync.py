# -*- coding: utf-8 -*-
"""Daily OpenRice dining-offer sync for all 74 SPA malls.

Scrapes OpenRice JSON API per mall, normalises to ``dining_offers`` schema,
prunes expired rows and dead OpenRice links, then writes root ``malls.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import httpx

from scrapers.openrice_api import (  # noqa: E402
    display_offer_title,
    extract_poi_image_url,
    is_generic_text,
    is_substantive_offer_title,
    load_api_cache,
    poi_to_row,
    save_api_cache,
    search_mall_pois,
)
from store_channels.http_util import shared_http  # noqa: E402

SPA_MALLS_PATH = ROOT / "malls.json"
CACHE_PATH = ROOT / "data" / "cache" / "daily_openrice_offers.json"
POI_DUMP_PATH = ROOT / "data" / "cache" / "_openrice_poi.json"
LIFECYCLE_PREVIEW_DAYS = 3
DEFAULT_OFFER_WINDOW_DAYS = 30
DEFAULT_DINING_IMAGE = (
    "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500"
)

OFFER_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("訂座折扣", r"訂座|訂位|訂枱|book\s*table|booking"),
    ("餐飲券", r"餐飲券|現金券|優惠券|coupon|voucher|禮券"),
    ("外賣折扣", r"外賣|自取|takeaway|take\s*away|deliver"),
    ("信用卡優惠", r"信用卡|visa|master|payme|alipay|支付|八達通"),
)

DISCOUNT_TAG_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*折|\d+\s*%\s*off|\$\s*\d+|HK\$\s*\d+|半價|買一送一|BOGO|"
    r"第二件\s*\d+\s*折|減\s*\$\s*\d+|回贈\s*\d+%)",
    re.I,
)

OPENRICE_URL_RE = re.compile(r"^https?://(?:www\.|s\.)?openrice\.com/", re.I)


def _today_hk() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _format_shop_no(floor: str, shop: str) -> str:
    floor = str(floor or "").strip()
    shop = str(shop or "").strip()
    if floor and shop and shop not in floor:
        return f"{floor} {shop}".strip()
    return floor or shop or ""


def classify_offer_type(text: str) -> str:
    blob = str(text or "")
    for label, pattern in OFFER_TYPE_RULES:
        if re.search(pattern, blob, re.I):
            return label
    return "訂座折扣"


def extract_discount_tag(text: str) -> str:
    match = DISCOUNT_TAG_RE.search(str(text or ""))
    if match:
        return re.sub(r"\s+", "", match.group(1))
    return ""


def lifecycle_status(start: date, end: date, *, today: date) -> str | None:
    if end < today:
        return None
    if start <= today <= end:
        return "active"
    delta = (start - today).days
    if 0 < delta <= LIFECYCLE_PREVIEW_DAYS:
        return "upcoming"
    if start > today:
        return None
    return "active"


def load_poi_image_index() -> dict[str, str]:
    """Map poiId / shortenUrl → facade image from cached OpenRice POI dump."""
    index: dict[str, str] = {}
    if not POI_DUMP_PATH.exists():
        return index
    try:
        payload = json.loads(POI_DUMP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return index
    rows = payload if isinstance(payload, list) else (payload.get("rows") or [])
    for poi in rows:
        if not isinstance(poi, dict):
            continue
        image = extract_poi_image_url(poi)
        if not image:
            continue
        poi_id = poi.get("poiId") or poi.get("poi_id")
        if poi_id is not None:
            index[str(poi_id)] = image
        shorten = str(poi.get("shortenUrl") or poi.get("source_url") or "").strip()
        if shorten:
            index[shorten] = image
            # Also index without query / trailing slash variants
            index[shorten.rstrip("/")] = image
    return index


def resolve_row_image(
    row: dict[str, Any],
    poi_images: dict[str, str] | None = None,
    *,
    prefer_poi: bool = True,
) -> str:
    """Resolve facade image; prefer POI door/env index over stale row.image (may be food)."""
    poi_images = poi_images or {}

    def _from_poi() -> str:
        poi_id = row.get("poi_id") or row.get("poiId")
        if poi_id is not None and poi_images.get(str(poi_id)):
            return poi_images[str(poi_id)]
        url = str(row.get("source_url") or row.get("openrice_url") or "").strip()
        if url and poi_images.get(url):
            return poi_images[url]
        if url and poi_images.get(url.rstrip("/")):
            return poi_images[url.rstrip("/")]
        return ""

    if prefer_poi:
        hit = _from_poi()
        if hit:
            return hit

    direct = str(
        row.get("image")
        or row.get("photo_url")
        or row.get("logo_url")
        or row.get("banner")
        or ""
    ).strip()
    # Never keep Unsplash / empty as "direct" when POI later available; still allow logos.
    if direct.startswith("http") and "unsplash.com" not in direct:
        # Reject obvious food CDN paths only when we have no POI — keep OR door CDN.
        return direct

    return _from_poi()


def row_to_dining_offer(
    row: dict[str, Any],
    *,
    today: date,
    poi_images: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    name = str(row.get("store_name") or "").strip()
    floor = str(row.get("floor") or "").strip()
    shop = str(row.get("shop_number") or "").strip()
    url = str(row.get("source_url") or row.get("openrice_url") or "").strip()
    if not (name and url and OPENRICE_URL_RE.match(url)):
        return None

    details = str(row.get("details") or "").strip()
    title = display_offer_title(row)
    # Drop placeholder / generic cards — keep only concrete promo titles.
    if not title or not is_substantive_offer_title(title):
        return None

    start = _parse_date(row.get("start_date"))
    end = _parse_date(row.get("expiry_date") or row.get("end_date"))
    if row.get("is_evergreen") or not (start and end):
        start = today
        end = today + timedelta(days=DEFAULT_OFFER_WINDOW_DAYS)

    status = lifecycle_status(start, end, today=today)
    if not status:
        return None

    offer_type = classify_offer_type(f"{title} {details}")
    discount_tag = extract_discount_tag(f"{title} {details}") or title[:24]
    shop_no = _format_shop_no(floor, shop)
    image = resolve_row_image(row, poi_images) or DEFAULT_DINING_IMAGE

    return {
        "restaurant_name": name,
        "shop_no": shop_no,
        "title": title[:160],
        "offer_type": offer_type,
        "discount_tag": discount_tag,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "openrice_url": url,
        "image": image,
        "status": status,
        "lifecycle_status": status,
        "source": "openrice_daily_sync",
        "synced_at": today.isoformat(),
        "poi_id": row.get("poi_id") or row.get("poiId"),
    }


async def url_is_alive(client: httpx.AsyncClient, url: str) -> bool:
    if not OPENRICE_URL_RE.match(url):
        return False
    try:
        response = await client.head(url, follow_redirects=True, timeout=8.0)
        if response.status_code >= 400:
            response = await client.get(url, follow_redirects=True, timeout=12.0)
        if response.status_code >= 400:
            return False
        body = (response.text or "")[:2000].lower()
        if "page not found" in body or "找不到" in body or "已下架" in body:
            return False
        return True
    except Exception:
        return False


def dedupe_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for offer in offers:
        key = "|".join(
            [
                str(offer.get("openrice_url") or "").strip().lower(),
                str(offer.get("restaurant_name") or "").strip().lower(),
                str(offer.get("title") or "").strip().lower(),
            ]
        )
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(offer)
    return out


def prune_offers(
    offers: list[dict[str, Any]],
    *,
    today: date,
    alive_urls: dict[str, bool] | None = None,
    poi_images: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "input": 0,
        "kept": 0,
        "pruned_expired": 0,
        "pruned_scheduled": 0,
        "pruned_dead_url": 0,
        "pruned_generic": 0,
    }
    kept: list[dict[str, Any]] = []
    for raw in offers:
        if not isinstance(raw, dict):
            continue
        stats["input"] += 1
        start = _parse_date(raw.get("start_date"))
        end = _parse_date(raw.get("end_date"))
        url = str(raw.get("openrice_url") or "").strip()
        title = str(raw.get("title") or raw.get("offer_title") or raw.get("discount_text") or "").strip()
        if not title or is_generic_text(title) or not is_substantive_offer_title(title):
            stats["pruned_generic"] += 1
            continue
        if not (start and end and url):
            stats["pruned_scheduled"] += 1
            continue
        if end < today:
            stats["pruned_expired"] += 1
            continue
        if alive_urls is not None and alive_urls.get(url) is False:
            stats["pruned_dead_url"] += 1
            continue
        status = lifecycle_status(start, end, today=today)
        if not status:
            stats["pruned_scheduled"] += 1
            continue
        offer = dict(raw)
        offer["title"] = title[:160]
        offer["start_date"] = start.isoformat()
        offer["end_date"] = end.isoformat()
        offer["status"] = status
        offer["lifecycle_status"] = status
        image = resolve_row_image(offer, poi_images)
        if image:
            offer["image"] = image
        elif not str(offer.get("image") or "").startswith("http"):
            offer["image"] = DEFAULT_DINING_IMAGE
        kept.append(offer)
        stats["kept"] += 1
    return kept, stats


def merge_poi_dump(pois: list[dict[str, Any]]) -> int:
    """Upsert OpenRice POIs (with doorPhoto) into local dump for image backfill."""
    if not pois:
        return 0
    existing: list[dict[str, Any]] = []
    if POI_DUMP_PATH.exists():
        try:
            payload = json.loads(POI_DUMP_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                existing = [p for p in payload if isinstance(p, dict)]
            elif isinstance(payload, dict):
                existing = [p for p in (payload.get("rows") or []) if isinstance(p, dict)]
        except (OSError, json.JSONDecodeError):
            existing = []
    by_id: dict[str, dict[str, Any]] = {}
    for poi in existing:
        pid = poi.get("poiId") or poi.get("poi_id")
        if pid is not None:
            by_id[str(pid)] = poi
    added = 0
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        pid = poi.get("poiId") or poi.get("poi_id")
        if pid is None:
            continue
        key = str(pid)
        if key not in by_id:
            added += 1
        by_id[key] = poi
    POI_DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(list(by_id.values()), ensure_ascii=False, indent=2) + "\n"
    tmp_path = POI_DUMP_PATH.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(payload_text, encoding="utf-8")
        tmp_path.replace(POI_DUMP_PATH)
    except OSError as exc:
        # Windows may lock the dump mid-sync; keep going with in-memory images.
        print(f"[openrice_sync] warn: poi dump write failed ({exc}); continuing without persist")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    return added


async def scrape_mall_rows(mall_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pois = await search_mall_pois(mall_name)
    rows: list[dict[str, Any]] = []
    for poi in pois:
        row = poi_to_row(poi, mall_hint=mall_name)
        if row:
            rows.append(row)
    return rows, pois


async def _html_fallback_rows(mall_name: str) -> list[dict[str, Any]]:
    try:
        from strata_mall_openrice_scraper import fetch_openrice_for_mall

        return await fetch_openrice_for_mall(mall_name)
    except Exception as exc:  # noqa: BLE001
        print(f"[openrice_sync] html fallback fail {mall_name}: {exc}")
        return []


def _cache_rows_for_mall(mall_name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in load_api_cache():
        hint = str(row.get("mall_hint") or row.get("mall_name") or "").strip()
        if hint == mall_name or (hint and hint in mall_name) or (mall_name and mall_name in hint):
            out.append(row)
    return out


async def scrape_all_malls(
    mall_names: list[str],
    *,
    delay_sec: float = 1.2,
    max_retries: int = 2,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in mall_names}
    live_total = 0
    collected_pois: list[dict[str, Any]] = []

    for idx, name in enumerate(mall_names):
        rows: list[dict[str, Any]] = []
        pois: list[dict[str, Any]] = []
        for attempt in range(max_retries):
            rows, pois = await scrape_mall_rows(name)
            if rows:
                break
            if attempt + 1 < max_retries:
                await asyncio.sleep(delay_sec * (attempt + 1))

        source = "api"
        if not rows:
            rows = await _html_fallback_rows(name)
            source = "html"
            pois = []
        if not rows:
            rows = _cache_rows_for_mall(name)
            source = "cache" if rows else "none"
            pois = []

        if pois:
            collected_pois.extend(pois)

        grouped[name] = rows
        if source in ("api", "html"):
            live_total += len(rows)
        print(f"[openrice_sync] {name}: rows={len(rows)} via={source} pois={len(pois)}")

        if idx + 1 < len(mall_names):
            await asyncio.sleep(delay_sec)

    flat = [row for rows in grouped.values() for row in rows]
    if flat:
        save_api_cache(flat, merge=True)
    if collected_pois:
        added = merge_poi_dump(collected_pois)
        print(f"[openrice_sync] poi dump upserted={len(collected_pois)} new={added}")
    return grouped, live_total


def load_mall_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for district in payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if isinstance(mall, dict):
                name = str(mall.get("mall_name") or "").strip()
                if name:
                    names.append(name)
    return names


async def validate_urls(urls: list[str]) -> dict[str, bool]:
    unique = sorted({u for u in urls if u})
    results: dict[str, bool] = {}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=12.0,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
            "Accept-Language": "zh-HK,zh;q=0.9",
        },
    ) as client:
        sem = asyncio.Semaphore(8)

        async def check(url: str) -> None:
            async with sem:
                results[url] = await url_is_alive(client, url)

        await asyncio.gather(*(check(url) for url in unique))
    return results


def rows_from_cache(mall_names: list[str]) -> dict[str, list[dict[str, Any]]]:
    grouped = {name: [] for name in mall_names}
    for row in load_api_cache():
        hint = str(row.get("mall_hint") or row.get("mall_name") or "").strip()
        for name in mall_names:
            if hint == name or (hint and hint in name) or (name and name in hint):
                grouped[name].append(row)
                break
    return grouped


async def sync_openrice(
    *,
    today: date,
    dry_run: bool = False,
    skip_scrape: bool = False,
    validate_links: bool = True,
) -> dict[str, Any]:
    payload = json.loads(SPA_MALLS_PATH.read_text(encoding="utf-8"))
    mall_names = load_mall_names(payload)
    stats: dict[str, Any] = {
        "today": today.isoformat(),
        "malls": len(mall_names),
        "scraped_rows": 0,
        "offers_written": 0,
        "malls_with_offers": 0,
        "prune": {
            "pruned_expired": 0,
            "pruned_dead_url": 0,
            "pruned_scheduled": 0,
            "pruned_generic": 0,
        },
    }

    grouped_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in mall_names}
    if not skip_scrape:
        async with shared_http():
            grouped_rows, live_total = await scrape_all_malls(mall_names)
        stats["scraped_rows"] = sum(len(v) for v in grouped_rows.values())
        stats["live_scraped_rows"] = live_total
        if live_total == 0 and stats["scraped_rows"] == 0:
            grouped_rows = rows_from_cache(mall_names)
            print("[openrice_sync] all sources empty → bulk API cache fallback")
        elif live_total == 0 and stats["scraped_rows"] > 0:
            print(f"[openrice_sync] live scrape blocked → per-mall cache used ({stats['scraped_rows']} rows)")

    # Rebuild after scrape so newly saved doorPhoto URLs are available for cache rows.
    poi_images = load_poi_image_index()
    stats["poi_images_indexed"] = len(poi_images)
    print(f"[openrice_sync] facade image index size={len(poi_images)}")

    candidate_offers: dict[str, list[dict[str, Any]]] = {}
    all_urls: list[str] = []
    for name in mall_names:
        offers = [
            offer
            for row in grouped_rows.get(name, [])
            if (offer := row_to_dining_offer(row, today=today, poi_images=poi_images))
        ]
        candidate_offers[name] = dedupe_offers(offers)
        all_urls.extend(str(o.get("openrice_url") or "") for o in offers)

    for district in payload.get("districts") or []:
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            existing = list(mall.get("dining_offers") or [])
            all_urls.extend(str(o.get("openrice_url") or "") for o in existing if isinstance(o, dict))

    alive_map: dict[str, bool] = {}
    if validate_links and all_urls:
        alive_map = await validate_urls(all_urls)

    for district in payload.get("districts") or []:
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            name = str(mall.get("mall_name") or "")
            existing = list(mall.get("dining_offers") or [])
            pruned_existing, prune_stats = prune_offers(
                existing, today=today, alive_urls=alive_map or None, poi_images=poi_images
            )
            for key in ("pruned_expired", "pruned_dead_url", "pruned_scheduled", "pruned_generic"):
                stats["prune"][key] += prune_stats.get(key, 0)

            fresh = [
                o for o in candidate_offers.get(name, [])
                if is_substantive_offer_title(str(o.get("title") or ""))
                and (not alive_map or alive_map.get(str(o.get("openrice_url") or ""), True))
            ]
            merged = dedupe_offers(pruned_existing + fresh)
            merged = [
                o for o in merged
                if lifecycle_status(_parse_date(o["start_date"]), _parse_date(o["end_date"]), today=today)
            ]
            # Always refresh facade from POI door/env index (never keep food leftovers).
            for offer in merged:
                facade = resolve_row_image(
                    {**offer, "image": "", "photo_url": "", "logo_url": "", "banner": ""},
                    poi_images,
                    prefer_poi=True,
                )
                offer["image"] = facade or DEFAULT_DINING_IMAGE
            mall["dining_offers"] = merged
            if merged:
                stats["malls_with_offers"] += 1
            stats["offers_written"] += len(merged)

    payload["openrice_sync_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    payload["openrice_sync_date"] = today.isoformat()

    if not dry_run:
        SPA_MALLS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"today": today.isoformat(), "stats": stats}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily OpenRice dining offer sync for malls.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-scrape", action="store_true", help="Prune/validate existing dining_offers only")
    parser.add_argument("--no-validate-urls", action="store_true")
    parser.add_argument("--today", default="", help="Override today (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    today = _parse_date(args.today) or _today_hk()
    stats = asyncio.run(
        sync_openrice(
            today=today,
            dry_run=args.dry_run,
            skip_scrape=args.skip_scrape,
            validate_links=not args.no_validate_urls,
        )
    )

    print("========== OPENRICE DAILY SYNC ==========")
    print(f"Today           : {stats['today']}")
    print(f"Malls           : {stats['malls']}")
    print(f"Scraped rows    : {stats['scraped_rows']}")
    print(f"Offers written  : {stats['offers_written']} ({stats['malls_with_offers']} malls)")
    print(f"Prune stats     : {stats['prune']}")
    print(f"Mode            : {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print("=========================================\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
