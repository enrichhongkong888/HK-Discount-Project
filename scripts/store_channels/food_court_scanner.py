# -*- coding: utf-8 -*-
"""Food-court / casual dining stall scanner for the 74-mall registry.

Loads curated stall directories (floor + shop + phone required) and optional
mall food-court zone metadata, then emits evergreen or dated store offers that
pass store_authenticity six-field + lifecycle gates.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from store_authenticity import is_precise_phone, is_precise_shop_number

from .http_util import afetch_text, normalize_phone
from .mall_match import build_registry_index, match_mall
from .offer_emit import build_store_offer, filter_authentic

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STALLS_PATH = ROOT / "data" / "food_court_stalls.json"
SOURCE_NAME = "food_court_scanner"

DEFAULT_OFFER_DETAILS = (
    "美食廣場／餐飲樓層檔口常態優惠：惠顧正價食品可享商場會員或店內當期推廣折扣；"
    "實際折扣、滿額門檻與換購條款以店內告示及當日單據為準。"
)

_FOOD_ZONE_HINT = re.compile(
    r"(美食廣場|food\s*court|大食代|food\s*republic|美食坊|享膳|餐飲樓層|美食薈萃)",
    re.I,
)


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"stalls": [], "zones": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[food_court] fail load {path}: {exc}")
        return {"stalls": [], "zones": []}
    if isinstance(raw, list):
        return {"stalls": raw, "zones": []}
    if isinstance(raw, dict):
        return {
            "stalls": list(raw.get("stalls") or []),
            "zones": list(raw.get("zones") or []),
        }
    return {"stalls": [], "zones": []}


def _zone_floor(zones: list[dict], mall_name: str, district: str) -> str | None:
    for zone in zones:
        if str(zone.get("mall_name") or "").strip() != mall_name:
            continue
        if district and str(zone.get("district") or "").strip() not in {"", district}:
            continue
        floor = str(zone.get("floor") or "").strip()
        if floor:
            return floor
    return None


def stall_to_offer(
    stall: dict[str, Any],
    registry_malls: list[dict],
    *,
    zones: list[dict] | None = None,
) -> dict[str, Any] | None:
    if stall.get("enabled") is False:
        return None
    index = build_registry_index(registry_malls)
    hint = str(stall.get("mall_hint") or stall.get("mall_name") or "").strip()
    address = str(stall.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit:
        print(f"[food_court] unmatched mall hint={hint!r}")
        return None

    store_name = str(stall.get("store_name") or stall.get("stall_name") or "").strip()
    floor = str(stall.get("floor") or "").strip()
    if not floor and zones:
        floor = _zone_floor(zones, hit.mall_name, hit.district) or ""
    shop = str(stall.get("shop_number") or "").strip()
    phone = normalize_phone(str(stall.get("phone") or ""))
    if not store_name or not floor or not is_precise_shop_number(shop) or not is_precise_phone(phone):
        return None

    details = str(stall.get("details") or stall.get("offer_text") or "").strip()
    if not details:
        details = DEFAULT_OFFER_DETAILS
    title = str(stall.get("title") or "").strip() or f"{store_name}｜美食廣場常態優惠"
    source_url = str(stall.get("source_url") or "").strip()
    if not source_url:
        return None

    start = str(stall.get("start_date") or "").strip() or None
    end = str(stall.get("expiry_date") or "").strip() or None
    evergreen = bool(stall.get("is_evergreen", True if not start else False))

    return build_store_offer(
        mall_name=hit.mall_name,
        district=hit.district,
        store_name=store_name,
        floor=floor,
        shop_number=shop,
        phone=phone,
        title=title,
        details=details[:500],
        source_url=source_url,
        source_name=SOURCE_NAME,
        start_date=start,
        expiry_date=end,
        is_evergreen=evergreen,
    )


async def scrape_food_court_operator_pages(
    registry_malls: list[dict],
    urls: list[str],
) -> list[dict[str, Any]]:
    """Best-effort HTML scrape for Food Republic / food-court operator pages.

    Only emits offers when floor, shop unit and phone are all present in text.
    """
    index = build_registry_index(registry_malls)
    offers: list[dict[str, Any]] = []

    async def _fetch(url: str) -> tuple[str, str | None]:
        try:
            return url, await afetch_text(url, timeout=45)
        except Exception as exc:  # noqa: BLE001
            print(f"[food_court] fetch fail {url}: {exc}")
            return url, None

    pages = await asyncio.gather(*[_fetch(url) for url in urls])
    for url, html in pages:
        if not html:
            continue
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        chunks = re.split(r"\n{2,}", text)
        for chunk in chunks:
            chunk = re.sub(r"\s+", " ", chunk).strip()
            if len(chunk) < 30 or not _FOOD_ZONE_HINT.search(chunk):
                continue
            phone_m = re.search(r"(\d{4}\s*\d{4})", chunk)
            shop_m = re.search(
                r"([A-Za-z]?\d+[A-Za-z0-9\-]*)\s*號舖|Shop\s*([A-Za-z]?\d+[A-Za-z0-9\-]*)",
                chunk,
                re.I,
            )
            floor_m = re.search(
                r"(\d+\s*樓|L\d+|G/?F|地下|1/?F|UG|LG)",
                chunk,
                re.I,
            )
            if not (phone_m and shop_m and floor_m):
                continue
            hit = match_mall(index, mall_hint=chunk[:160], address=chunk[:240])
            if not hit:
                continue
            shop = (shop_m.group(1) or shop_m.group(2) or "").strip()
            offer = build_store_offer(
                mall_name=hit.mall_name,
                district=hit.district,
                store_name="大食代 Food Republic",
                floor=floor_m.group(1).strip(),
                shop_number=shop,
                phone=normalize_phone(phone_m.group(1)),
                title="大食代 Food Republic｜美食廣場常態優惠",
                details=DEFAULT_OFFER_DETAILS,
                source_url=url,
                source_name=SOURCE_NAME,
                is_evergreen=True,
            )
            if offer:
                offers.append(offer)
    return offers


async def scrape_food_court_offers(
    registry_malls: list[dict],
    *,
    stalls_path: Path | None = None,
    live_urls: list[str] | None = None,
) -> list[dict[str, Any]]:
    payload = _load_payload(stalls_path or DEFAULT_STALLS_PATH)
    stalls = [s for s in payload["stalls"] if isinstance(s, dict)]
    zones = [z for z in payload["zones"] if isinstance(z, dict)]
    offers: list[dict[str, Any]] = []
    for stall in stalls:
        offer = stall_to_offer(stall, registry_malls, zones=zones)
        if offer:
            offers.append(offer)

    if live_urls:
        offers.extend(await scrape_food_court_operator_pages(registry_malls, live_urls))

    kept = filter_authentic(offers, label="food_court")
    print(f"[food_court] stalls={len(stalls)} authentic_offers={len(kept)}")
    return kept
