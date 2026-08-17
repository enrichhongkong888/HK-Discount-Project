# -*- coding: utf-8 -*-
"""全港 74 商場：品牌 Store Locator 逆向電話／鋪號對照。

讀取多品牌官方分店清單（結構化 feed + 可選 live HTML），以商場名稱／地址
對照 data/malls-registry.json，產出通過六欄 presence 的 verified pins，
並可寫回 data/brand_store_locators.json 供每日 expand 使用。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified  # noqa: E402

from store_channels.brand_aliases import match_brand  # noqa: E402
from store_channels.http_util import afetch_text, normalize_phone, shared_http  # noqa: E402
from store_channels.mall_match import build_registry_index, match_mall  # noqa: E402
from store_channels.offer_emit import build_store_offer  # noqa: E402

FEEDS_PATH = ROOT / "data" / "brand_locator_feeds.json"
LOCATOR_PATH = ROOT / "data" / "brand_store_locators.json"
CACHE_PATH = ROOT / "data" / "cache" / "flagship_enriched_pins.json"
OFFERS_CACHE = ROOT / "data" / "cache" / "flagship_enriched_offers.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"

SOURCE_NAME = "enrich_flagship_phones"

# Public Watsons pharmacy / personal-care locator used as a HK-wide reverse map.
WATSONS_STORELIST = "https://www.equopausa.com.hk/storelist/"

DEFAULT_CHAIN_DETAILS: dict[str, str] = {
    "moneyback": "MoneyBack／屈臣氏會員常態禮遇：出示會員碼可賺分及換領當期優惠；詳情以 App 及店內告示為準。",
    "yuu": "yuu 獎賞計劃常態禮遇：出示 yuu 會員碼可賺分及換領當期優惠；詳情以 yuu App 為準。",
    "fortress_club": "豐澤會員常態禮遇：登記 Fortress Club 可享積分及當期店內推廣；詳情以 App 為準。",
    "starbucks_rewards": "Starbucks Rewards 常態禮遇：會員消費可累積星星換領獎賞；詳情以 App 為準。",
    "aeon_member": "AEON MEMBER 常態禮遇：出示會員卡／App 可享積分及當期折扣；詳情以官方公告為準。",
    "uniqlo_app": "UNIQLO App 會員常態禮遇：登記可享 App 專屬折扣與新品情報；詳情以 App 為準。",
}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[flagship] fail load {path}: {exc}")
        return None


def load_registry() -> list[dict]:
    payload = _load_json(REGISTRY_PATH) or {}
    return list(payload.get("malls") or []) if isinstance(payload, dict) else []


def _feed_rows() -> list[dict[str, Any]]:
    payload = _load_json(FEEDS_PATH)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [r for r in (payload.get("stores") or payload.get("pins") or []) if isinstance(r, dict)]
    return []


async def scrape_watsons_equopausa() -> list[dict[str, Any]]:
    """Parse HK-wide Watsons store table into locator rows."""
    try:
        html = await afetch_text(WATSONS_STORELIST, timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"[flagship] watsons fetch failed: {exc}")
        return []
    rows: list[dict[str, Any]] = []
    # Table rows: | 區域 | 店名 | 地址 | 電話 |
    for m in re.finditer(
        r"<tr[^>]*>\s*<td[^>]*>(?P<district>[^<]+)</td>\s*"
        r"<td[^>]*>(?P<name>[^<]+)</td>\s*"
        r"<td[^>]*>(?P<addr>[^<]+)</td>\s*"
        r"<td[^>]*>(?P<phone>[\d\s/-]+)</td>",
        html,
        flags=re.I,
    ):
        addr = re.sub(r"\s+", " ", m.group("addr")).strip()
        phone = normalize_phone(m.group("phone").split("/")[0])
        name = m.group("name").strip()
        floor = ""
        shop = ""
        fm = re.search(
            r"((?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:樓|層|/F)|地下|地庫|平台)",
            addr,
            re.I,
        )
        if fm:
            floor = fm.group(1).strip()
        sm = re.search(
            r"([A-Za-z]?\d+[A-Za-z0-9\-/,及至]*)\s*號舖",
            addr,
        )
        if sm:
            shop = sm.group(1).replace("及", ",").strip()
        if not shop:
            sm2 = re.search(r"(G\d+[A-Za-z]?|L\d+[A-Za-z0-9\-]*|[BM]\d+[A-Za-z]?)", addr, re.I)
            if sm2:
                shop = sm2.group(1)
        # Infer floor only from shop prefix when address omitted floor wording.
        if not floor and shop:
            if re.match(r"G", shop, re.I):
                floor = "地下"
            elif re.match(r"B", shop, re.I):
                floor = "地庫"
            elif re.match(r"UG", shop, re.I):
                floor = "UG"
            elif re.match(r"LG", shop, re.I):
                floor = "LG"
            else:
                lm = re.match(r"L(\d+)", shop, re.I)
                if lm:
                    floor = f"{lm.group(1)}樓"
        if not floor or not shop:
            continue
        rows.append(
            {
                "chain_id": "moneyback",
                "store_name": "屈臣氏",
                "mall_hint": name,
                "address": addr,
                "floor": floor,
                "shop_number": shop,
                "phone": phone,
                "source_url": WATSONS_STORELIST,
            }
        )
    print(f"[flagship] watsons equopausa rows={len(rows)}")
    return rows


def row_to_pin(row: dict[str, Any], registry: list[dict]) -> dict[str, str] | None:
    index = build_registry_index(registry)
    hint = str(row.get("mall_hint") or row.get("mall_name") or "").strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit:
        return None
    brand = match_brand(str(row.get("store_name") or ""))
    chain_id = str(row.get("chain_id") or (brand[0] if brand else "")).strip()
    store_name = str(row.get("store_name") or (brand[1] if brand else "")).strip()
    if not chain_id or not store_name:
        return None
    phone = normalize_phone(str(row.get("phone") or ""))
    floor = str(row.get("floor") or "").strip()
    shop = str(row.get("shop_number") or "").strip()
    if not floor or not shop:
        return None
    pin = {
        "chain_id": chain_id,
        "mall_name": hit.mall_name,
        "district": hit.district,
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "store_name": store_name,
        "verification_status": VERIFICATION_VERIFIED,
        "source": SOURCE_NAME,
        "source_url": str(row.get("source_url") or "").strip(),
    }
    if presence_is_verified(pin):
        return pin
    return None


def pins_to_offers(pins: list[dict[str, str]]) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    for pin in pins:
        chain_id = pin["chain_id"]
        details = DEFAULT_CHAIN_DETAILS.get(
            chain_id,
            f"{pin['store_name']} 常態會員／門市優惠：出示會員碼或 App 可享積分／折扣；詳情以官方公告為準。",
        )
        offer = build_store_offer(
            mall_name=pin["mall_name"],
            district=pin["district"],
            store_name=pin["store_name"],
            floor=pin["floor"],
            shop_number=pin["shop_number"],
            phone=pin["phone"],
            title=f"{pin['store_name']}｜{pin['mall_name']} 常態優惠",
            details=details,
            source_url=pin.get("source_url") or "https://www.watsons.com.hk/",
            source_name=SOURCE_NAME,
            is_evergreen=True,
        )
        if offer:
            offers.append(offer)
    return offers


def merge_into_brand_locators(pins: list[dict[str, str]]) -> int:
    payload = _load_json(LOCATOR_PATH)
    if not isinstance(payload, dict):
        payload = {"_comment": "Official brand locator pins.", "pins": []}
    existing = list(payload.get("pins") or [])
    seen = {
        (
            str(r.get("chain_id") or ""),
            str(r.get("mall_hint") or r.get("mall_name") or ""),
            str(r.get("shop_number") or ""),
        )
        for r in existing
        if isinstance(r, dict)
    }
    added = 0
    for pin in pins:
        key = (pin["chain_id"], pin["mall_name"], pin["shop_number"])
        if key in seen:
            continue
        seen.add(key)
        existing.append(
            {
                "chain_id": pin["chain_id"],
                "store_name": pin["store_name"],
                "mall_hint": pin["mall_name"],
                "district": pin["district"],
                "floor": pin["floor"],
                "shop_number": pin["shop_number"],
                "phone": pin["phone"],
                "source_url": pin.get("source_url") or "",
            }
        )
        added += 1
    payload["pins"] = existing
    LOCATOR_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


async def enrich_flagship_phones(
    *,
    live: bool = True,
    write_locators: bool = True,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    registry = load_registry()
    raw_rows = _feed_rows()
    if live:
        raw_rows.extend(await scrape_watsons_equopausa())
    pins: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    unmatched = 0
    for row in raw_rows:
        pin = row_to_pin(row, registry)
        if not pin:
            unmatched += 1
            continue
        key = (pin["chain_id"], pin["mall_name"], pin["shop_number"])
        if key in seen:
            continue
        seen.add(key)
        pins.append(pin)
    offers = pins_to_offers(pins)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"pins": pins}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OFFERS_CACHE.write_text(
        json.dumps({"offers": offers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    added = merge_into_brand_locators(pins) if write_locators else 0
    malls_hit = {p["mall_name"] for p in pins}
    print(
        f"[flagship] raw={len(raw_rows)} pins={len(pins)} offers={len(offers)} "
        f"malls_hit={len(malls_hit)} unmatched={unmatched} locators_added={added}"
    )
    return pins, offers


def main() -> int:
    import asyncio

    async def _run() -> None:
        async with shared_http():
            await enrich_flagship_phones(live=True, write_locators=True)

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
