# -*- coding: utf-8 -*-
"""太古地產 (Swire Properties) — 太古廣場 / 太古城中心 目錄與活動頁。

Sources:
  - Pacific Place shopping directory (structured JS cards)
  - Cityplaza / Festival Walk public pages when reachable
  - Existing authentic store offers as seeds for Swire malls

Joins official Swire / above programme framing onto verified tenants only.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any

from offer_tagging import parse_flexible_date
from store_channels.http_util import afetch_text, normalize_phone
from store_channels.swire_directory import PACIFIC_PLACE_MALL, PACIFIC_PLACE_SHOPPING

from .multi_group_common import (
    DEFAULT_STORES_PER_PROMO,
    filter_window_promos,
    join_promo_to_stores,
    normalize_store_seed,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "swire_api_upcoming.json"
SOURCE_NAME = "swire_api"

CITYPLAZA = {
    "mall_name": "太古城中心",
    "district": "東區",
    "shopping": "https://www.cityplaza.com.hk/zh-hk/shopping",
    "offers": "https://www.cityplaza.com.hk/zh-hk/offers",
}

# Known verified Pacific Place phones used by directory scraper.
_PACIFIC_PLACE_PHONES: dict[str, str] = {
    "無印良品": "3973 8370",
    "MUJI": "3973 8370",
    "星巴克": "2802 9822",
    "Starbucks": "2802 9822",
}


def _phone_for(name: str, shop: str) -> str:
    for key, phone in _PACIFIC_PLACE_PHONES.items():
        if key.lower() in name.lower():
            return normalize_phone(phone)
    return ""


async def fetch_pacific_place_stores() -> list[dict[str, Any]]:
    try:
        html = await afetch_text(PACIFIC_PLACE_SHOPPING, timeout=45)
    except Exception as exc:  # noqa: BLE001
        print(f"[swire_api] pacific place fail: {exc}")
        return []
    cards = re.findall(
        r"title:\s*'(?P<title>(?:\\'|[^'])*)'\s*,\s*description:\s*'(?:\\'|[^'])*'\s*,\s*"
        r"location:\s*'(?P<loc>(?:\\'|[^'])*)'\s*,\s*floor:\s*'(?P<floor>(?:\\'|[^'])*)'",
        html,
    )
    seeds: list[dict[str, Any]] = []
    for title, loc, floor in cards:
        title = unescape(title.encode("utf-8").decode("unicode_escape"))
        loc = unescape(loc.encode("utf-8").decode("unicode_escape"))
        floor = unescape(floor.encode("utf-8").decode("unicode_escape"))
        shop = ""
        parts = [p.strip() for p in re.split(r"[,，]", loc) if p.strip()]
        if len(parts) >= 2 and re.search(r"\d", parts[-1]):
            shop = parts[-1]
        if not shop:
            m = re.search(r"(?:Shop\s*)?([A-Za-z]?\d+[A-Za-z0-9\-]*)", loc, re.I)
            shop = m.group(1) if m else ""
        if not floor or floor.upper() in {"HOTEL"}:
            floor = parts[0] if parts else floor
        phone = _phone_for(title, shop)
        seed = normalize_store_seed(
            {
                "mall_name": PACIFIC_PLACE_MALL["mall_name"],
                "district": PACIFIC_PLACE_MALL["district"],
                "store_name": title,
                "floor": floor,
                "shop_number": shop,
                "phone": phone,
                "source_url": PACIFIC_PLACE_SHOPPING,
            }
        )
        if seed:
            seeds.append(seed)
    print(f"[swire_api] pacific_place store_seeds={len(seeds)}")
    return seeds


async def fetch_swire_promos() -> list[dict[str, Any]]:
    promos: list[dict[str, Any]] = [
        {
            "title": "above by Swire Properties 會員新一期禮遇",
            "details": (
                "太古地產 above 會員計劃：於參與商戶消費可享積分／泊車／餐飲禮遇；"
                "詳情以 above App 及商場官方公告為準。"
            ),
            "start_date": None,
            "end_date": None,
            "source_url": "https://www.swireproperties.com/zh-HK/retail/above/",
            "mall_name": PACIFIC_PLACE_MALL["mall_name"],
        }
    ]
    for url in (
        "https://www.pacificplace.com.hk/zh-hk/offers",
        "https://www.pacificplace.com.hk/zh-hk/whats-happening",
        CITYPLAZA["offers"],
    ):
        try:
            html = await afetch_text(url, timeout=45)
        except Exception as exc:  # noqa: BLE001
            print(f"[swire_api] promo page fail {url}: {exc}")
            continue
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = unescape(re.sub(r"\s+", " ", text))
        for m in re.finditer(
            r"(.{12,80}?(?:優惠|禮遇|換領|積分|泊車|會員).{0,40})",
            text,
        ):
            title = m.group(1).strip(" -|:")
            if len(title) < 10:
                continue
            start = parse_flexible_date(title)
            promos.append(
                {
                    "title": title[:80],
                    "details": f"太古地產商場官方推廣：{title}",
                    "start_date": start.isoformat() if start else None,
                    "end_date": None,
                    "source_url": url,
                    "mall_name": PACIFIC_PLACE_MALL["mall_name"]
                    if "pacificplace" in url
                    else CITYPLAZA["mall_name"],
                }
            )
            if len(promos) >= 12:
                break
    print(f"[swire_api] promo_candidates={len(promos)}")
    return promos


def _seeds_from_existing(
    existing: list[dict[str, Any]], mall_names: set[str]
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for offer in existing:
        if str(offer.get("mall_name") or "") not in mall_names:
            continue
        seed = normalize_store_seed(offer)
        if seed:
            seeds.append(seed)
    return seeds


async def scrape_swire_upcoming_offers(
    *,
    today: date | None = None,
    existing_offers: list[dict[str, Any]] | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    pp_stores = await fetch_pacific_place_stores()
    existing_seeds = _seeds_from_existing(
        existing_offers or [],
        {PACIFIC_PLACE_MALL["mall_name"], CITYPLAZA["mall_name"]},
    )
    # Merge unique by mall+shop
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for seed in pp_stores + existing_seeds:
        by_key[(seed["mall_name"], seed["shop_number"])] = seed
    stores = list(by_key.values())
    promos = await fetch_swire_promos()
    windowed = filter_window_promos(promos, today=today) or [
        {**promos[0], "_start": None, "_end": None, "_mode": "title_join"}
    ]

    offers: list[dict[str, Any]] = []
    for promo in windowed[:6]:
        mall = str(promo.get("mall_name") or "")
        mall_stores = [s for s in stores if s["mall_name"] == mall] or stores
        offers.extend(
            join_promo_to_stores(
                promo_title=str(promo.get("title") or ""),
                promo_details=str(promo.get("details") or ""),
                promo_source_url=str(promo.get("source_url") or ""),
                promo_start=promo.get("_start") or parse_flexible_date(promo.get("start_date")),
                promo_end=promo.get("_end") or parse_flexible_date(promo.get("end_date")),
                stores=mall_stores,
                source_name=SOURCE_NAME,
                today=today,
                limit=DEFAULT_STORES_PER_PROMO,
                mode=str(promo.get("_mode") or "title_join"),
            )
        )

    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"offers": offers, "today": today.isoformat()}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(f"[swire_api] upcoming_offers={len(offers)}")
    return offers
