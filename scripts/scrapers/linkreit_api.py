# -*- coding: utf-8 -*-
"""領展 (Link REIT) LinkHK internal JSON API.

Base: https://www.linkhk.com/linkweb/api/
  - GET shopCentre/{id}  → promotions, shop.shopList, dine.dineList
  - GET shop/{shopId}    → shopInfo (locationTc, telephone, names)
  - GET promotion/{id}   → promotion detail / date range

Maps registry malls to centre IDs and emits seed-compatible tenant rows
(floor / shop / phone / promo details) for link_reit_channel.
"""

from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from pathlib import Path
from typing import Any

import httpx

from store_channels.http_util import afetch_json, normalize_phone

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "linkreit_api_rows.json"

API_BASE = "https://www.linkhk.com/linkweb/api"
JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.linkhk.com/tc/",
    "Origin": "https://www.linkhk.com",
}
API_TIMEOUT = httpx.Timeout(connect=3.0, read=20.0, write=20.0, pool=3.0)

# Registry mall_name → LinkHK shopCentreId (verified via live probe).
LINK_CENTRE_IDS: dict[str, int] = {
    "樂富廣場": 7,
    "赤柱廣場": 28,
    "T Town": 135,
    "黃大仙中心": 164,
}

LINK_CENTRE_META: dict[str, dict[str, str]] = {
    "樂富廣場": {"district": "九龍城區"},
    "赤柱廣場": {"district": "南區"},
    "T Town": {"district": "元朗區"},
    "黃大仙中心": {"district": "黃大仙區"},
}

_SHOP_RE = re.compile(
    r"([A-Za-z]?\d+[A-Za-z0-9\-/]*)\s*號舖",
    re.I,
)
_FLOOR_RE = re.compile(
    r"((?:[A-Za-z]區)?(?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:/F|樓|層)|地下|地庫|平台)",
    re.I,
)
_DATE_RANGE_RE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"\s*至\s*"
    r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)

DEFAULT_DETAILS = (
    "領展商場商戶常態禮遇：惠顧正價貨品／餐飲可享商場會員或店內當期推廣折扣；"
    "實際條款以店內告示及 Link App 為準。"
)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[linkreit_api] fail load {path}: {exc}")
        return None


def save_api_cache(rows: list[dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"rows": rows, "source": "linkreit_api"}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def load_api_cache() -> list[dict[str, Any]]:
    payload = _load_json(CACHE_PATH)
    if isinstance(payload, dict):
        rows = payload.get("rows") or []
        return [r for r in rows if isinstance(r, dict)]
    return []


def _strip_tags(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_location_tc(location: str) -> tuple[str, str]:
    """Parse e.g. 黃大仙樂富廣場A區1樓1161-1162號舖 → (A區1樓, 1161-1162)."""
    loc = _strip_tags(location)
    shop = ""
    floor = ""
    shop_m = _SHOP_RE.search(loc)
    if shop_m:
        shop = shop_m.group(1).strip()
    # Prefer zone+floor segment before 號舖
    floor_m = _FLOOR_RE.search(loc)
    if floor_m:
        floor = floor_m.group(1).strip()
    # Enrich: keep 「A區1樓」 style if present
    zone_floor = re.search(r"([A-Za-z]區\s*\d+\s*樓)", loc)
    if zone_floor:
        floor = zone_floor.group(1).replace(" ", "")
    return floor, shop


def parse_promotion_dates(date_tc: str) -> tuple[str | None, str | None]:
    m = _DATE_RANGE_RE.search(_strip_tags(date_tc))
    if not m:
        return None, None
    y1, mo1, d1, y2, mo2, d2 = m.groups()
    start = f"{int(y1):04d}-{int(mo1):02d}-{int(d1):02d}"
    end_year = int(y2) if y2 else int(y1)
    end = f"{end_year:04d}-{int(mo2):02d}-{int(d2):02d}"
    return start, end


def _promo_bundle(promotions: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the first usable centre promotion for offer text/dates."""
    for promo in promotions:
        if not isinstance(promo, dict):
            continue
        title = _strip_tags(str(promo.get("promotionTitleTc") or promo.get("promotionTitleEn") or ""))
        date_tc = str(promo.get("promotionDateTc") or "")
        start, end = parse_promotion_dates(date_tc)
        promo_id = promo.get("id")
        if title:
            return {
                "title": title,
                "details": f"領展推廣：{title}。詳情以 Link App／商場告示為準。",
                "start_date": start,
                "expiry_date": end,
                "source_url": (
                    f"https://www.linkhk.com/tc/promotion/{promo_id}"
                    if promo_id
                    else "https://www.linkhk.com/tc/promotion/"
                ),
                "is_evergreen": not (start and end),
            }
    return {
        "title": "",
        "details": DEFAULT_DETAILS,
        "start_date": None,
        "expiry_date": None,
        "source_url": "https://www.linkhk.com/tc/promotion/",
        "is_evergreen": True,
    }


async def _get_json(path: str) -> dict[str, Any]:
    url = f"{API_BASE}/{path.lstrip('/')}"
    data = await afetch_json(url, timeout=API_TIMEOUT, headers=JSON_HEADERS)
    if not isinstance(data, dict):
        return {}
    if str(data.get("error") or "") not in ("0000", "0", ""):
        return {}
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


async def fetch_shop_centre(centre_id: int) -> dict[str, Any]:
    return await _get_json(f"shopCentre/{centre_id}")


async def fetch_shop(shop_id: int) -> dict[str, Any]:
    return await _get_json(f"shop/{shop_id}")


def _collect_shop_ids(centre: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for section_key, list_key in (
        ("dine", "dineList"),
        ("shop", "shopList"),
    ):
        section = centre.get(section_key) or {}
        if not isinstance(section, dict):
            continue
        for item in section.get(list_key) or []:
            if not isinstance(item, dict):
                continue
            sid = item.get("shopId")
            if sid is None:
                continue
            try:
                sid_i = int(sid)
            except (TypeError, ValueError):
                continue
            if sid_i in seen:
                continue
            seen.add(sid_i)
            ids.append(sid_i)
    # Market stalls (optional)
    market = centre.get("market") or {}
    if isinstance(market, dict):
        for item in market.get("market") or []:
            if not isinstance(item, dict):
                continue
            sid = item.get("shopId")
            try:
                sid_i = int(sid)
            except (TypeError, ValueError):
                continue
            if sid_i not in seen:
                seen.add(sid_i)
                ids.append(sid_i)
    return ids


def shop_info_to_row(
    shop_info: dict[str, Any],
    *,
    mall_name: str,
    district: str,
    promo: dict[str, Any],
) -> dict[str, Any] | None:
    store = _strip_tags(
        str(shop_info.get("shopNameTc") or shop_info.get("shopNameEn") or "")
    )
    location = str(shop_info.get("locationTc") or shop_info.get("locationEn") or "")
    floor, shop = parse_location_tc(location)
    phone = normalize_phone(str(shop_info.get("telephone") or ""))
    if not (store and floor and shop and phone):
        return None
    shop_id = shop_info.get("shopId")
    source_url = (
        f"https://www.linkhk.com/tc/shop/{shop_id}"
        if shop_id
        else str(promo.get("source_url") or "https://www.linkhk.com/tc/")
    )
    promo_title = str(promo.get("title") or "").strip()
    title = (
        f"{store}｜{promo_title}"
        if promo_title
        else f"{store}｜領展商場商戶優惠"
    )
    return {
        "mall_hint": mall_name,
        "mall_name": mall_name,
        "district": district,
        "store_name": store,
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "title": title[:120],
        "details": str(promo.get("details") or DEFAULT_DETAILS)[:500],
        "source_url": source_url,
        "is_evergreen": bool(promo.get("is_evergreen", True)),
        "start_date": promo.get("start_date"),
        "expiry_date": promo.get("expiry_date"),
        "address": location,
    }


async def scrape_centre_rows(mall_name: str, centre_id: int) -> list[dict[str, Any]]:
    meta = LINK_CENTRE_META.get(mall_name) or {}
    district = meta.get("district", "")
    try:
        centre = await fetch_shop_centre(centre_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[linkreit_api] centre fail {mall_name}#{centre_id}: {exc}")
        return []
    if not centre:
        print(f"[linkreit_api] empty centre {mall_name}#{centre_id}")
        return []

    promotions = [p for p in (centre.get("promotions") or []) if isinstance(p, dict)]
    promo = _promo_bundle(promotions)
    shop_ids = _collect_shop_ids(centre)
    print(f"[linkreit_api] {mall_name} shops={len(shop_ids)} promos={len(promotions)}")

    rows: list[dict[str, Any]] = []

    async def _one(sid: int) -> dict[str, Any] | None:
        try:
            detail = await fetch_shop(sid)
        except Exception as exc:  # noqa: BLE001
            print(f"[linkreit_api] shop fail {sid}: {exc}")
            return None
        info = detail.get("shopInfo") if isinstance(detail, dict) else None
        if not isinstance(info, dict):
            return None
        return shop_info_to_row(info, mall_name=mall_name, district=district, promo=promo)

    details = await asyncio.gather(*(_one(sid) for sid in shop_ids))
    for row in details:
        if row:
            rows.append(row)
    return rows


async def scrape_linkreit_api_rows(
    *,
    centres: dict[str, int] | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Scrape all mapped Link centres; [] on total failure (caller uses cache)."""
    mapping = centres or LINK_CENTRE_IDS
    groups = await asyncio.gather(
        *(scrape_centre_rows(name, cid) for name, cid in mapping.items())
    )
    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.extend(group)

    if not rows:
        print("[linkreit_api] no rows from live API")
        return []

    if persist_cache:
        save_api_cache(rows)
    print(f"[linkreit_api] live_rows={len(rows)}")
    return rows
