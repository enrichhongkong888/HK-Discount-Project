"""Swire Properties mall directories (Pacific Place / above programme hosts)."""

from __future__ import annotations

import asyncio
import re
from html import unescape

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

from .brand_aliases import match_brand
from .http_util import afetch_text, normalize_phone, shared_http

PACIFIC_PLACE_SHOPPING = "https://www.pacificplace.com.hk/zh-hk/shopping"
PACIFIC_PLACE_MALL = {"mall_name": "太古廣場", "district": "中西區"}

_PACIFIC_PLACE_PHONES: dict[tuple[str, str], str] = {
    ("muji_app", "100"): "3973 8370",
    ("starbucks_rewards", "128-129"): "2802 9822",
    ("starbucks_rewards", "128"): "2802 9822",
    ("starbucks_rewards", "129"): "2802 9822",
}


def _pacific_place_phone(chain_id: str, shop: str, store_name: str) -> str:
    shop_key = re.sub(r"\s+", "", shop)
    for key, phone in _PACIFIC_PLACE_PHONES.items():
        if key[0] != chain_id:
            continue
        if key[1] == shop_key or key[1] in shop_key or shop_key in key[1]:
            return phone
    if chain_id == "muji_app":
        return "3973 8370"
    _ = store_name
    return ""


async def scrape_pacific_place_brand_pins() -> list[dict[str, str]]:
    html = await afetch_text(PACIFIC_PLACE_SHOPPING)
    cards = re.findall(
        r"title:\s*'(?P<title>(?:\\'|[^'])*)'\s*,\s*description:\s*'(?:\\'|[^'])*'\s*,\s*"
        r"location:\s*'(?P<loc>(?:\\'|[^'])*)'\s*,\s*floor:\s*'(?P<floor>(?:\\'|[^'])*)'",
        html,
    )
    pins: list[dict[str, str]] = []
    for title, loc, floor in cards:
        title = unescape(title.encode("utf-8").decode("unicode_escape"))
        loc = unescape(loc.encode("utf-8").decode("unicode_escape"))
        floor = unescape(floor.encode("utf-8").decode("unicode_escape"))
        matched = match_brand(title)
        if not matched:
            continue
        chain_id, store_name = matched
        shop = ""
        parts = [p.strip() for p in re.split(r"[,，]", loc) if p.strip()]
        if len(parts) >= 2:
            if re.search(r"\d", parts[-1]):
                shop = parts[-1]
            if not floor or floor.upper() in {"HOTEL"}:
                floor = parts[0]
        if not shop:
            m = re.search(r"(?:Shop\s*)?([A-Za-z]?\d+[A-Za-z0-9\-]*)", loc, re.I)
            shop = m.group(1) if m else ""
        if not shop or not re.search(r"\d", shop):
            continue
        if not floor or not re.search(r"[0-9A-Za-z]", floor):
            continue
        phone = _pacific_place_phone(chain_id, shop, store_name)
        if not phone:
            continue
        pin = {
            "chain_id": chain_id,
            "mall_name": PACIFIC_PLACE_MALL["mall_name"],
            "district": PACIFIC_PLACE_MALL["district"],
            "floor": floor,
            "shop_number": shop,
            "phone": normalize_phone(phone),
            "store_name": store_name,
            "verification_status": VERIFICATION_VERIFIED,
            "source": "swire_directory:pacific_place",
            "source_url": PACIFIC_PLACE_SHOPPING,
        }
        if presence_is_verified(pin):
            pins.append(pin)
    print(f"[pacific_place] verified brand pins={len(pins)}")
    return pins


async def scrape_all_swire_directories() -> list[dict[str, str]]:
    try:
        return await scrape_pacific_place_brand_pins()
    except Exception as exc:  # noqa: BLE001
        print(f"[swire] scrape failed: {exc}")
        return []


def scrape_all_swire_directories_sync() -> list[dict[str, str]]:
    async def _run() -> list[dict[str, str]]:
        async with shared_http():
            return await scrape_all_swire_directories()

    return asyncio.run(_run())
