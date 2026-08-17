# -*- coding: utf-8 -*-
"""新鴻基地產 (SHKP) / The Point — YOHO Strapi + 新城市廣場活動頁。

APIs:
  - https://cms.yohomall.hk/api/events  (event_start / event_end / name / slug)
  - https://cms.yohomall.hk/api/shops   (display_name / phone / mall_shop_number)
  - New Town Plaza promotions HTML (date + title best-effort)

Joins official campaigns onto verified YOHO / NTP store presence only.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from offer_tagging import parse_flexible_date
from store_channels.http_util import afetch_json, afetch_text, normalize_phone

from .multi_group_common import (
    DEFAULT_STORES_PER_PROMO,
    filter_window_promos,
    join_promo_to_stores,
    normalize_store_seed,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "shkp_api_upcoming.json"
SOURCE_NAME = "shkp_api"

CMS_YOHO = "https://cms.yohomall.hk"
YOHO_MALL = {"mall_name": "YOHO MALL 形點", "district": "元朗區"}
NTP_MALL = {"mall_name": "新城市廣場", "district": "沙田區"}
NTP_PROMOS = "https://www.newtownplaza.com.hk/zh-hant/promotions"

API_TIMEOUT = httpx.Timeout(connect=3.0, read=20.0, write=20.0, pool=3.0)
JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.yohomall.hk/",
    "Origin": "https://www.yohomall.hk",
}


def _attrs(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    if isinstance(node.get("attributes"), dict):
        return node["attributes"]
    return node


def _yoho_floor_shop(attrs: dict[str, Any]) -> tuple[str, str]:
    rel = attrs.get("mall_shop_number") or {}
    data = rel.get("data") if isinstance(rel, dict) else None
    loc = _attrs(data) if data else {}
    floor = str(loc.get("floor") or attrs.get("floor") or "").strip()
    shop = str(loc.get("shop_number") or attrs.get("shop_number") or "").strip()
    mall_code = str(loc.get("mall") or "").strip()
    if mall_code:
        label = {
            "mall-1": "YOHO MALL I",
            "mall-2": "YOHO MALL II",
            "mall-mix": "YOHO MIX",
        }.get(mall_code, mall_code)
        floor = f"{label} {floor}".strip()
    return floor, shop


async def fetch_yoho_events(*, max_pages: int = 3) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        query = urlencode(
            {
                "pagination[page]": page,
                "pagination[pageSize]": 50,
                "sort": "event_start:desc",
            }
        )
        try:
            payload = await afetch_json(
                f"{CMS_YOHO}/api/events?{query}",
                timeout=API_TIMEOUT,
                headers=JSON_HEADERS,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[shkp_api] events fail page={page}: {exc}")
            break
        if not isinstance(payload, dict):
            break
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            attrs = _attrs(row)
            name = str(attrs.get("name") or "").strip()
            if not name:
                continue
            slug = str(attrs.get("slug") or row.get("id") or "").strip()
            events.append(
                {
                    "title": name,
                    "details": name,
                    "start_date": str(attrs.get("event_start") or "")[:10],
                    "end_date": str(attrs.get("event_end") or "")[:10],
                    "event_start": attrs.get("event_start"),
                    "event_end": attrs.get("event_end"),
                    "source_url": f"https://www.yohomall.hk/zh-hk/whats-on/{slug}"
                    if slug
                    else f"{CMS_YOHO}/api/events/{row.get('id')}",
                    "mall_name": YOHO_MALL["mall_name"],
                }
            )
        meta = (payload.get("meta") or {}).get("pagination") or {}
        if page >= int(meta.get("pageCount") or page):
            break
    print(f"[shkp_api] yoho events={len(events)}")
    return events


async def fetch_yoho_store_seeds(*, max_pages: int = 8) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        query = urlencode(
            {
                "pagination[page]": page,
                "pagination[pageSize]": 100,
                "populate": "mall_shop_number",
            }
        )
        try:
            payload = await afetch_json(
                f"{CMS_YOHO}/api/shops?{query}",
                timeout=API_TIMEOUT,
                headers=JSON_HEADERS,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[shkp_api] shops fail page={page}: {exc}")
            break
        if not isinstance(payload, dict):
            break
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            attrs = _attrs(row)
            name = str(
                attrs.get("display_name")
                or attrs.get("name_zh")
                or attrs.get("name_tc")
                or attrs.get("name")
                or ""
            ).strip()
            floor, shop = _yoho_floor_shop(attrs)
            phone = normalize_phone(str(attrs.get("phone") or attrs.get("tel") or ""))
            seed = normalize_store_seed(
                {
                    "mall_name": YOHO_MALL["mall_name"],
                    "district": YOHO_MALL["district"],
                    "store_name": name,
                    "floor": floor,
                    "shop_number": shop,
                    "phone": phone,
                    "source_url": f"{CMS_YOHO}/api/shops/{row.get('id')}",
                }
            )
            if seed:
                seeds.append(seed)
        meta = (payload.get("meta") or {}).get("pagination") or {}
        if page >= int(meta.get("pageCount") or page):
            break
    print(f"[shkp_api] yoho store_seeds={len(seeds)}")
    return seeds


async def fetch_ntp_promos() -> list[dict[str, Any]]:
    try:
        html = await afetch_text(NTP_PROMOS, timeout=API_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        print(f"[shkp_api] ntp promos fail: {exc}")
        return []
    promos: list[dict[str, Any]] = []
    # Card-like blocks: title near ISO / Chinese dates
    for m in re.finditer(
        r"((?:20\d{2}-\d{2}-\d{2}).{0,80}?(?:20\d{2}-\d{2}-\d{2}))",
        html,
    ):
        span = m.group(1)
        dates = re.findall(r"20\d{2}-\d{2}-\d{2}", span)
        if len(dates) < 1:
            continue
        # Look backwards for a nearby heading-ish string
        start_idx = max(0, m.start() - 200)
        window = re.sub(r"<[^>]+>", " ", html[start_idx : m.end() + 20])
        window = re.sub(r"\s+", " ", window).strip()
        title = window[-80:] if len(window) > 80 else window
        title = title.strip(" -|:")[:80] or "新城市廣場最新推廣"
        promos.append(
            {
                "title": title,
                "details": f"新城市廣場官方推廣：{title}",
                "start_date": dates[0],
                "end_date": dates[1] if len(dates) > 1 else dates[0],
                "source_url": NTP_PROMOS,
                "mall_name": NTP_MALL["mall_name"],
            }
        )
    # Deduplicate by title
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for p in promos:
        key = p["title"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    print(f"[shkp_api] ntp promo_candidates={len(uniq)}")
    return uniq[:12]


def _ntp_seeds_from_offers(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for offer in existing:
        if str(offer.get("mall_name") or "") != NTP_MALL["mall_name"]:
            continue
        seed = normalize_store_seed(offer)
        if seed:
            seeds.append(seed)
    return seeds


async def scrape_shkp_upcoming_offers(
    *,
    today: date | None = None,
    existing_offers: list[dict[str, Any]] | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    yoho_stores = await fetch_yoho_store_seeds()
    events = await fetch_yoho_events()
    ntp_promos = await fetch_ntp_promos()
    ntp_stores = _ntp_seeds_from_offers(existing_offers or [])

    offers: list[dict[str, Any]] = []
    for promo in filter_window_promos(events, today=today)[:8]:
        offers.extend(
            join_promo_to_stores(
                promo_title=str(promo.get("title") or ""),
                promo_details=str(promo.get("details") or promo.get("title") or ""),
                promo_source_url=str(promo.get("source_url") or ""),
                promo_start=promo.get("_start") or parse_flexible_date(promo.get("start_date")),
                promo_end=promo.get("_end") or parse_flexible_date(promo.get("end_date")),
                stores=yoho_stores,
                source_name=SOURCE_NAME,
                today=today,
                limit=DEFAULT_STORES_PER_PROMO,
                mode=str(promo.get("_mode") or "active_join"),
            )
        )

    for promo in filter_window_promos(ntp_promos, today=today)[:6]:
        if not ntp_stores:
            break
        offers.extend(
            join_promo_to_stores(
                promo_title=str(promo.get("title") or "新城市廣場推廣"),
                promo_details=str(promo.get("details") or ""),
                promo_source_url=str(promo.get("source_url") or NTP_PROMOS),
                promo_start=promo.get("_start"),
                promo_end=promo.get("_end"),
                stores=ntp_stores,
                source_name=SOURCE_NAME,
                today=today,
                limit=DEFAULT_STORES_PER_PROMO,
                mode=str(promo.get("_mode") or "active_join"),
            )
        )

    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"offers": offers, "today": today.isoformat()}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(f"[shkp_api] upcoming_offers={len(offers)}")
    return offers
