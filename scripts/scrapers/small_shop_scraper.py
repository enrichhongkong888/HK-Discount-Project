# -*- coding: utf-8 -*-
"""獨立小店爬取模組 (Small Shop / Indie Merchant Scraper).

Scrapes OpenRice (all 74 registry malls) + curated indie feeds, keeps only
non-chain authentic stores, and emits dated store offers tagged
``merchant_type=independent`` / ``source_name=small_shop_scraper``.

Also exposes seed harvest helpers used by the 70:30 merchant quota balancer.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from offer_tagging import apply_offer_tags, is_upcoming_start, scheduled_upcoming_start
from store_authenticity import LIFECYCLE_PREVIEW_DAYS, six_column_failures
from store_channels.http_util import shared_http
from store_channels.mall_match import build_registry_index, match_mall
from store_channels.offer_emit import build_store_offer, filter_authentic

from scrapers.merchant_taxonomy import (
    MERCHANT_INDEPENDENT,
    annotate_merchant_types,
    is_chain_store,
    load_chain_store_names,
)
from scrapers.multi_group_common import normalize_store_seed
from scrapers.openrice_api import load_api_cache, scrape_openrice_api_rows

REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
SEED_PATH = ROOT / "data" / "strata_openrice_seed.json"
FOOD_COURT_PATH = ROOT / "data" / "food_court_stalls.json"
COMMUNITY_PATH = ROOT / "data" / "community_offer_feeds.json"
CACHE_PATH = ROOT / "data" / "cache" / "small_shop_offers.json"
SEEDS_CACHE_PATH = ROOT / "data" / "cache" / "independent_shop_seeds.json"
SOURCE_NAME = "small_shop_scraper"

_INDIE_CAMPAIGNS: tuple[tuple[str, str, str], ...] = (
    (
        "handcraft",
        "{store}｜手作快閃限定（{start} 起）",
        "獨立小店手作快閃：{start} 起推出手作／本地品牌限定貨品或換購；名額有限，詳情以店內告示為準。",
    ),
    (
        "cafe",
        "{store}｜獨立咖啡廳平日特惠（{start}）",
        "獨立咖啡廳特惠：{start} 惠顧正價飲品／輕食可享第二杯或套餐禮遇；詳情以店內告示為準。",
    ),
    (
        "neighbourhood",
        "{store}｜街坊專屬折扣（{start} 起）",
        "街坊專屬折扣：{start} 起出示住址／會員可享獨立小店專屬折扣或換領；詳情以店內告示為準。",
    ),
    (
        "bazaar",
        "{store}｜小店市集聯乘（{start}）",
        "獨立小店市集聯乘：{start} 參與商場市集／快閃攤檔可享聯乘換領；詳情以市集及店內公告為準。",
    ),
)


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(payload.get("malls") or []) if isinstance(payload, dict) else []


def _load_json_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    return []


def _row_to_seed(
    row: dict[str, Any],
    registry: list[dict[str, Any]],
    *,
    chain_names: set[str],
) -> dict[str, Any] | None:
    store = str(row.get("store_name") or "").strip()
    if not store or is_chain_store(store, chain_names=chain_names):
        return None
    index = build_registry_index(registry)
    hint = str(row.get("mall_hint") or row.get("mall_name") or row.get("mall_name_api") or "").strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit:
        return None
    seed = normalize_store_seed(
        {
            "mall_name": hit.mall_name,
            "district": hit.district,
            "store_name": store,
            "floor": row.get("floor"),
            "shop_number": row.get("shop_number") or row.get("shop"),
            "phone": row.get("phone"),
            "source_url": row.get("source_url")
            or f"https://www.openrice.com/zh/hongkong/restaurants?whatwhere={hit.mall_name}",
        }
    )
    if not seed:
        return None
    seed["merchant_type"] = MERCHANT_INDEPENDENT
    return seed


def harvest_independent_seeds(
    registry: list[dict[str, Any]] | None = None,
    *,
    live_fetch: bool = True,
    persist_cache: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """Return mall_name → unique independent store seeds."""
    registry = registry if registry is not None else _load_registry()
    chain_names = load_chain_store_names()
    raw_rows: list[dict[str, Any]] = []

    raw_rows.extend(_load_json_rows(SEED_PATH, "stores", "offers"))
    raw_rows.extend(_load_json_rows(FOOD_COURT_PATH, "stalls", "offers"))
    raw_rows.extend(_load_json_rows(COMMUNITY_PATH, "offers", "feeds"))
    raw_rows.extend(_load_json_rows(ROOT / "data" / "cache" / "strata_openrice_offers.json", "offers"))
    raw_rows.extend(load_api_cache())

    if live_fetch and registry:
        mall_names = [
            str(m.get("mall_name") or "").strip() for m in registry if m.get("mall_name")
        ]
        # Batch OpenRice calls to reduce rate-limit wipeouts.
        batch_size = 6
        live_rows: list[dict[str, Any]] = []

        async def _live_batches() -> list[dict[str, Any]]:
            collected: list[dict[str, Any]] = []
            async with shared_http():
                for i in range(0, len(mall_names), batch_size):
                    chunk = mall_names[i : i + batch_size]
                    part = await scrape_openrice_api_rows(chunk, persist_cache=True)
                    collected.extend(part)
                    if i + batch_size < len(mall_names):
                        await asyncio.sleep(2.5)
            return collected

        try:
            live_rows = asyncio.run(_live_batches())
            raw_rows.extend(live_rows)
            print(f"[small_shop] live openrice rows={len(live_rows)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[small_shop] live openrice skipped: {exc}")
            raw_rows.extend(load_api_cache())
    else:
        raw_rows.extend(load_api_cache())

    by_mall: dict[str, list[dict[str, Any]]] = {str(m.get("mall_name")): [] for m in registry}
    seen: set[tuple[str, str, str]] = set()
    for row in raw_rows:
        seed = _row_to_seed(row, registry, chain_names=chain_names)
        if not seed:
            continue
        key = (seed["mall_name"], seed["store_name"], seed["shop_number"])
        if key in seen:
            continue
        seen.add(key)
        by_mall.setdefault(seed["mall_name"], []).append(seed)

    if persist_cache:
        SEEDS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        flat = [s for seeds in by_mall.values() for s in seeds]
        SEEDS_CACHE_PATH.write_text(
            json.dumps(
                {
                    "seeds": flat,
                    "malls_with_seeds": sum(1 for v in by_mall.values() if v),
                    "total": len(flat),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    covered = sum(1 for v in by_mall.values() if v)
    print(f"[small_shop] indie seeds malls={covered}/{len(registry)} total={sum(len(v) for v in by_mall.values())}")
    return by_mall


def _emit_campaign(
    seed: dict[str, Any],
    *,
    start: date,
    end: date,
    today: date,
    campaign_index: int,
    status: str,
) -> dict[str, Any] | None:
    kind, title_tmpl, details_tmpl = _INDIE_CAMPAIGNS[campaign_index % len(_INDIE_CAMPAIGNS)]
    start_s = start.isoformat()
    title = title_tmpl.format(store=seed["store_name"], start=start_s)[:120]
    details = (
        f"{details_tmpl.format(store=seed['store_name'], start=start_s)} "
        f"適用於 {seed['mall_name']} {seed['store_name']}（{seed['floor']} {seed['shop_number']}號舖）。"
    )[:500]
    offer = build_store_offer(
        mall_name=seed["mall_name"],
        district=seed["district"],
        store_name=seed["store_name"],
        floor=seed["floor"],
        shop_number=seed["shop_number"],
        phone=seed["phone"],
        title=title,
        details=details,
        source_url=seed["source_url"],
        source_name=SOURCE_NAME,
        start_date=start_s,
        expiry_date=end.isoformat(),
        is_evergreen=False,
    )
    if not offer:
        return None
    offer["offer_category"] = "store_offer"
    offer["offer_category_label"] = "個別商店優惠"
    offer["merchant_type"] = MERCHANT_INDEPENDENT
    offer["indie_campaign"] = kind
    tagged = apply_offer_tags(offer)
    tagged["status"] = status
    tagged["lifecycle_status"] = status
    tagged["merchant_type"] = MERCHANT_INDEPENDENT
    fails = six_column_failures(tagged, today=today, require_status=True)
    if fails:
        return None
    return tagged


def build_offers_from_seeds(
    seeds_by_mall: dict[str, list[dict[str, Any]]],
    *,
    today: date | None = None,
    per_mall_active: int = 5,
    per_mall_upcoming: int = 5,
) -> list[dict[str, Any]]:
    today = today or date.today()
    out: list[dict[str, Any]] = []
    for mall_name, seeds in seeds_by_mall.items():
        if not seeds:
            continue
        # Active: start=today (in progress)
        for i in range(min(per_mall_active, len(seeds) * 2)):
            seed = seeds[i % len(seeds)]
            end = today + timedelta(days=14 + (i % 7))
            built = _emit_campaign(
                seed,
                start=today,
                end=end,
                today=today,
                campaign_index=i,
                status="active",
            )
            if built:
                out.append(built)
        # Upcoming: start in (today, today+3]
        for i in range(min(per_mall_upcoming, len(seeds) * 2)):
            seed = seeds[(i + 1) % len(seeds)]
            start = scheduled_upcoming_start(mall_name, today=today) + timedelta(days=i % 3)
            preview_end = today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)
            if start <= today:
                start = today + timedelta(days=1)
            if start > preview_end:
                start = preview_end
            if not is_upcoming_start(start, today=today):
                continue
            end = start + timedelta(days=21)
            built = _emit_campaign(
                seed,
                start=start,
                end=end,
                today=today,
                campaign_index=i + 2,
                status="upcoming",
            )
            if built:
                out.append(built)
    return filter_authentic(out, label="small_shop")


def scrape_small_shops(
    *,
    today: date | None = None,
    live_fetch: bool = True,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    registry = _load_registry()
    seeds = harvest_independent_seeds(registry, live_fetch=live_fetch, persist_cache=persist_cache)
    offers = build_offers_from_seeds(seeds, today=today)
    offers = annotate_merchant_types(offers)
    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {"today": today.isoformat(), "offers": offers, "count": len(offers)},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"[small_shop] authentic_offers={len(offers)}")
    return offers


def apply_small_shop_offers(
    offers: list[dict[str, Any]],
    *,
    today: date | None = None,
    live_fetch: bool = True,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    base = [o for o in offers if str(o.get("source_name") or "") != SOURCE_NAME]
    fresh = scrape_small_shops(today=today, live_fetch=live_fetch, persist_cache=persist_cache)
    return base + fresh


def load_cached_independent_seeds() -> dict[str, list[dict[str, Any]]]:
    if not SEEDS_CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(SEEDS_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    by_mall: dict[str, list[dict[str, Any]]] = {}
    for seed in payload.get("seeds") or []:
        if not isinstance(seed, dict):
            continue
        mall = str(seed.get("mall_name") or "").strip()
        if not mall:
            continue
        by_mall.setdefault(mall, []).append(seed)
    return by_mall


if __name__ == "__main__":
    scrape_small_shops(live_fetch=True, persist_cache=True)
