"""Expand individual store offers via all high-quality channels.

Channels:
1) VERIFIED_PINS (hand-verified baseline)
2) data/brand_store_locators.json (curated official locator pins)
3) Live brand locators (AEON / YATA / MUJI)
4) Sino Land directories (奧海城 / 屯門市廣場 / 荃新天地 → S⁺)
5) SHKP directories (YOHO Strapi + 新城市廣場 map → The Point)
6) Swire Pacific Place directory (above hosts)
7) HK-wide flagship Store Locator reverse phone match (74 malls)
8) Link REIT / Hang Lung — prefer LinkHK JSON API (linkreit_api), HTML + cache fallback
9) Payment/wallet promos joined onto verified pins (PayMe / AlipayHK / WeChat Pay)
10) Social media structured post parser (週年慶／市集／小店)
11) Food-court / casual-dining stall scanner
12) District community aggregator (sources.json + feeds)
13) Strata / OpenRice — prefer internal JSON API (openrice_api), HTML + cache fallback
14) Multi-group developer APIs (SHKP / Swire / Sino) → upcoming density boost
15) Recurring pattern prediction engine (weekend / Wed credit / member day / festival early-bird)
16) Merchant direct feed (JSON/CSV under data/merchant_submissions/)

Network I/O uses native asyncio + shared httpx.AsyncClient (TCP keep-alive pool),
gated by asyncio.Semaphore(15) globally and stricter domain semaphores for
openrice.com / linkreit.com / linkhk.com. Channel jobs run via asyncio.gather.

Daily review gates (every rematerialize / sync):
- six-field authenticity via store_authenticity.py (no placeholders)
- lifecycle window: only in-progress or starting within 3 days; expired rows purged
- offer_tagging vertical_category + tags applied on write
- merchant offer consolidation: same mall+store+floor+shop upcoming → primary + sub_offers
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from store_authenticity import (  # noqa: E402
    VERIFICATION_PENDING,
    VERIFICATION_VERIFIED,
    presence_is_verified,
)

from enrich_flagship_phones import enrich_flagship_phones  # noqa: E402
from fix_store_locations import VERIFIED_PINS  # noqa: E402
from match_store_locators import load_registry_malls, match_locator_pins  # noqa: E402
from strata_mall_openrice_scraper import scrape_strata_openrice_offers  # noqa: E402
from store_channels.brand_locators_live import scrape_live_brand_locators  # noqa: E402
from store_channels.community_aggregator import scrape_community_offers  # noqa: E402
from store_channels.food_court_scanner import scrape_food_court_offers  # noqa: E402
from store_channels.http_util import (  # noqa: E402
    CONNECT_TIMEOUT_S,
    DOMAIN_CONCURRENCY,
    GLOBAL_CONCURRENCY,
    MAX_RETRIES,
    READ_TIMEOUT_S,
    shared_http,
)
from store_channels.link_reit_channel import scrape_link_hanglung_directories  # noqa: E402
from store_channels.payment_join import scrape_payment_joined_offers  # noqa: E402
from store_channels.shkp_directory import scrape_all_shkp_directories  # noqa: E402
from store_channels.sino_directory import scrape_all_sino_directories  # noqa: E402
from store_channels.social_media_parser import scrape_social_media_offers  # noqa: E402
from store_channels.swire_directory import scrape_all_swire_directories  # noqa: E402
from scrapers.multi_group_api import scrape_multi_group_upcoming_offers  # noqa: E402

CHAIN_PATH = ROOT / "data" / "chain_store_offers.json"
CACHE_PATH = ROOT / "data" / "cache" / "directory_verified_pins.json"
PAYMENT_CACHE = ROOT / "data" / "cache" / "payment_joined_store_offers.json"
INDEPENDENT_CACHE = ROOT / "data" / "cache" / "independent_store_offers.json"
SOURCES_PATH = ROOT / "data" / "sources.json"
BENCHMARK_PATH = ROOT / "data" / "cache" / "expand_benchmark.json"

# Measured ThreadPoolExecutor baseline (pre-asyncio refactor), wall-clock seconds.
BASELINE_THREADPOOL_WALL_S = 172.8

INDEPENDENT_SOURCE_NAMES = frozenset(
    {
        "social_media_parser",
        "food_court_scanner",
        "community_aggregator",
        "payment_join:payme",
        "payment_join",
        "enrich_flagship_phones",
        "strata_mall_openrice",
        "link_reit_channel",
        "upcoming_coverage",
        "recurring_pattern_engine",
        "merchant_direct_feed",
        "community_calendar",
        "small_shop_scraper",
        "shkp_api",
        "swire_api",
        "sino_api",
        "multi_group_api",
    }
)


def _pin_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("chain_id") or "").strip(),
        str(row.get("mall_name") or "").strip(),
        str(row.get("shop_number") or "").strip(),
    )


def merge_verified_pins(groups: list[list[dict]]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str, str], dict[str, str]] = {}
    for group in groups:
        for raw in group:
            pin = {
                "chain_id": str(raw.get("chain_id") or "").strip(),
                "mall_name": str(raw.get("mall_name") or "").strip(),
                "district": str(raw.get("district") or "").strip(),
                "floor": str(raw.get("floor") or "").strip(),
                "shop_number": str(raw.get("shop_number") or "").strip(),
                "phone": str(raw.get("phone") or "").strip(),
                "store_name": str(raw.get("store_name") or "").strip(),
                "verification_status": VERIFICATION_VERIFIED,
            }
            source = str(raw.get("source") or "").strip()
            if source:
                pin["source"] = source
            source_url = str(raw.get("source_url") or "").strip()
            if source_url:
                pin["source_url"] = source_url
            if not presence_is_verified(pin):
                continue
            merged[_pin_key(pin)] = pin
    rows = list(merged.values())
    rows.sort(key=lambda r: (r["chain_id"], r["district"], r["mall_name"], r["shop_number"]))
    return rows


def apply_presence(verified_pins: list[dict[str, str]]) -> tuple[int, int]:
    payload = json.loads(CHAIN_PATH.read_text(encoding="utf-8"))
    presence_in = payload.get("presence", [])
    verified_keys = {(p["chain_id"], p["mall_name"]) for p in verified_pins}

    pending: list[dict] = []
    seen_pending: set[tuple[str, str, str]] = set()
    for row in presence_in:
        chain_id = str(row.get("chain_id", "")).strip()
        mall = str(row.get("mall_name", "")).strip()
        shop = str(row.get("shop_number", "")).strip()
        if not chain_id or not mall:
            continue
        if (chain_id, mall) in verified_keys:
            continue
        key = (chain_id, mall, shop)
        if key in seen_pending:
            continue
        seen_pending.add(key)
        item = {
            "chain_id": chain_id,
            "mall_name": mall,
            "district": str(row.get("district", "")).strip(),
            "floor": str(row.get("floor") or "").strip(),
            "shop_number": shop,
            "verification_status": VERIFICATION_PENDING,
        }
        phone = str(row.get("phone") or "").strip()
        if phone:
            item["phone"] = phone
        store_name = str(row.get("store_name") or "").strip()
        if store_name:
            item["store_name"] = store_name
        pending.append(item)

    cleaned = verified_pins + pending
    cleaned.sort(
        key=lambda r: (
            0 if r.get("verification_status") == VERIFICATION_VERIFIED else 1,
            r.get("chain_id", ""),
            r.get("district", ""),
            r.get("mall_name", ""),
            r.get("shop_number", ""),
        )
    )
    verified_n = sum(1 for r in cleaned if presence_is_verified(r))
    pending_n = len(cleaned) - verified_n
    payload["presence"] = cleaned
    payload["_comment"] = (
        "連鎖商店／集團會員常態禮遇對照。"
        "僅 verification_status=verified 且樓層／鋪號／電話齊全者會注入 discounts／前端；"
        "其餘列標記為 pending（待核實）並被系統過濾。"
        "verified 來源：VERIFIED_PINS + brand locators + Sino/SHKP/Swire/"
        "Link-HangLung directories + enrich_flagship_phones。"
    )
    payload["_authenticity_policy"] = (
        "store offers require store_name + floor + shop_number + phone + "
        "offer content + validity dates; placeholders are forbidden"
    )
    CHAIN_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return verified_n, pending_n


def _merchant_store_key(offer: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(offer.get("mall_name") or "").strip(),
        str(offer.get("store_name") or "").strip(),
        str(offer.get("floor") or "").strip(),
        str(offer.get("shop_number") or "").strip(),
    )


def _offer_time_slot(offer: dict[str, Any]) -> str:
    start = str(offer.get("start_date") or "").strip()
    end = str(offer.get("expiry_date") or offer.get("end_date") or "").strip()
    if start and end and end != start:
        return f"{start} 至 {end}"
    if start:
        return f"{start} 起"
    return "時段待確認"


def _sub_offer_payload(offer: dict[str, Any]) -> dict[str, str]:
    title = str(offer.get("title") or offer.get("offer_title") or "").strip()
    detail = str(
        offer.get("details") or offer.get("detail") or offer.get("discount_info") or ""
    ).strip()
    return {
        "time_slot": _offer_time_slot(offer),
        "title": title,
        "detail": detail,
        "start_date": str(offer.get("start_date") or "").strip(),
        "expiry_date": str(
            offer.get("expiry_date") or offer.get("end_date") or ""
        ).strip(),
        "source_name": str(offer.get("source_name") or "").strip(),
    }


def consolidate_merchant_offers(
    offers: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Merge same-store active / upcoming offers into primary + ``sub_offers``.

    Groups by (mall_name, store_name, floor, shop_number) **within each** lifecycle
    bucket (active and upcoming separately). Keeps the earliest ``start_date`` as
    primary; remaining rows become ``sub_offers`` with time_slot / title / detail.
    Quota fills are included — one physical shop → one primary card per status.
    Never invents store fields — only rearranges authentic payloads.
    """
    from offer_tagging import STATUS_ACTIVE, STATUS_UPCOMING, classify_lifecycle_status

    today = today or date.today()
    passthrough: list[dict[str, Any]] = []
    buckets: dict[str, list[dict[str, Any]]] = {
        STATUS_ACTIVE: [],
        STATUS_UPCOMING: [],
    }

    for raw in offers:
        if not isinstance(raw, dict):
            continue
        offer = dict(raw)
        offer_type = str(offer.get("offer_type") or offer.get("type") or "").strip()
        store_name = str(offer.get("store_name") or "").strip()
        floor = str(offer.get("floor") or "").strip()
        shop = str(offer.get("shop_number") or "").strip()
        status = classify_lifecycle_status(offer, today=today)
        is_store_bucket = (
            offer_type == "store"
            and bool(store_name and floor and shop)
            and status in buckets
        )
        if is_store_bucket:
            buckets[status].append(offer)
        else:
            offer["sub_offers"] = []
            passthrough.append(offer)

    consolidated: list[dict[str, Any]] = []
    merged_groups = 0
    folded = 0
    bucket_stats: dict[str, int] = {}

    for status, rows_in in buckets.items():
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for offer in rows_in:
            groups[_merchant_store_key(offer)].append(offer)
        bucket_stats[status] = len(rows_in)
        for _key, rows in groups.items():
            rows.sort(
                key=lambda r: (
                    str(r.get("start_date") or ""),
                    str(r.get("title") or r.get("offer_title") or ""),
                    str(r.get("source_name") or ""),
                )
            )
            primary = dict(rows[0])
            # Flatten nested sub_offers from already-consolidated rows.
            sub_offers: list[dict[str, str]] = []
            for extra in rows[1:]:
                sub_offers.append(_sub_offer_payload(extra))
                for nested in extra.get("sub_offers") or []:
                    if isinstance(nested, dict):
                        sub_offers.append(
                            {
                                "time_slot": str(nested.get("time_slot") or "").strip(),
                                "title": str(nested.get("title") or "").strip(),
                                "detail": str(
                                    nested.get("detail") or nested.get("details") or ""
                                ).strip(),
                                "start_date": str(nested.get("start_date") or "").strip(),
                                "expiry_date": str(
                                    nested.get("expiry_date") or nested.get("end_date") or ""
                                ).strip(),
                                "source_name": str(nested.get("source_name") or "").strip(),
                            }
                        )
            for nested in primary.pop("sub_offers", None) or []:
                if isinstance(nested, dict):
                    sub_offers.insert(
                        0,
                        {
                            "time_slot": str(nested.get("time_slot") or "").strip(),
                            "title": str(nested.get("title") or "").strip(),
                            "detail": str(
                                nested.get("detail") or nested.get("details") or ""
                            ).strip(),
                            "start_date": str(nested.get("start_date") or "").strip(),
                            "expiry_date": str(
                                nested.get("expiry_date") or nested.get("end_date") or ""
                            ).strip(),
                            "source_name": str(nested.get("source_name") or "").strip(),
                        },
                    )
            # De-dupe identical sub slots.
            seen_sub: set[tuple[str, str, str]] = set()
            unique_subs: list[dict[str, str]] = []
            for sub in sub_offers:
                sig = (
                    str(sub.get("time_slot") or ""),
                    str(sub.get("title") or ""),
                    str(sub.get("detail") or ""),
                )
                if sig in seen_sub or not any(sig):
                    continue
                seen_sub.add(sig)
                unique_subs.append(sub)
            primary["sub_offers"] = unique_subs
            primary["consolidated_offer_count"] = 1 + len(unique_subs)
            primary["status"] = status
            primary["lifecycle_status"] = status
            if unique_subs:
                merged_groups += 1
                folded += len(unique_subs)
            consolidated.append(primary)

    out = passthrough + consolidated
    print(
        f"[consolidate] active_store={bucket_stats.get(STATUS_ACTIVE, 0)} "
        f"upcoming_store={bucket_stats.get(STATUS_UPCOMING, 0)} "
        f"primary_cards={len(consolidated)} merged_groups={merged_groups} "
        f"folded_into_sub_offers={folded} total_rows={len(out)}"
    )
    return out


def _patch_discounts_sub_offers(
    discounts_path: Path,
    consolidated_raw: list[dict[str, Any]],
) -> None:
    """Re-attach ``sub_offers`` after Offer round-trip (dataclass drops extras)."""
    if not discounts_path.exists():
        return
    payload = json.loads(discounts_path.read_text(encoding="utf-8"))
    index: dict[tuple[str, ...], dict[str, Any]] = {}
    soft_index: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw in consolidated_raw:
        if str(raw.get("offer_type") or "") != "store":
            continue
        mall_store = _merchant_store_key(raw)
        start = str(raw.get("start_date") or "").strip()
        title = str(raw.get("title") or raw.get("offer_title") or "").strip()
        key = (
            *mall_store,
            start,
            title,
            str(raw.get("pattern_id") or "").strip(),
            str(raw.get("merchant_type") or "").strip(),
        )
        meta = {
            "sub_offers": list(raw.get("sub_offers") or []),
            "consolidated_offer_count": int(
                raw.get("consolidated_offer_count") or (1 + len(raw.get("sub_offers") or []))
            ),
            "merchant_type": str(raw.get("merchant_type") or ""),
            "quota_fill": bool(raw.get("quota_fill")),
            "pattern_id": str(raw.get("pattern_id") or ""),
            "status": str(raw.get("status") or raw.get("lifecycle_status") or ""),
        }
        index[key] = meta
        soft_index[(*mall_store, start, title)] = meta
        # Last-resort: same store + start (prefer keeping most recent meta).
        soft_index.setdefault((*mall_store, start), meta)

    def _apply(rows: list[Any]) -> None:
        for offer in rows:
            if not isinstance(offer, dict):
                continue
            if str(offer.get("offer_type") or "") != "store":
                offer.setdefault("sub_offers", [])
                continue
            mall_store = _merchant_store_key(offer)
            start = str(offer.get("start_date") or "").strip()
            title = str(offer.get("title") or offer.get("offer_title") or "").strip()
            key = (
                *mall_store,
                start,
                title,
                str(offer.get("pattern_id") or "").strip(),
                str(offer.get("merchant_type") or "").strip(),
            )
            meta = (
                index.get(key)
                or soft_index.get((*mall_store, start, title))
                or soft_index.get((*mall_store, start))
            )
            if meta:
                offer["sub_offers"] = meta["sub_offers"]
                offer["consolidated_offer_count"] = meta["consolidated_offer_count"]
                if meta.get("merchant_type"):
                    offer["merchant_type"] = meta["merchant_type"]
                if meta.get("quota_fill"):
                    offer["quota_fill"] = True
                if meta.get("pattern_id"):
                    offer["pattern_id"] = meta["pattern_id"]
                if meta.get("status"):
                    offer["status"] = meta["status"]
                    offer["lifecycle_status"] = meta["status"]
            else:
                offer.setdefault("sub_offers", [])
                offer.setdefault("merchant_type", offer.get("merchant_type") or "")

    offers = payload.get("offers")
    if isinstance(offers, list):
        _apply(offers)
    by_category = payload.get("by_category")
    if isinstance(by_category, dict):
        for bucket in by_category.values():
            if isinstance(bucket, dict) and isinstance(bucket.get("offers"), list):
                _apply(bucket["offers"])
            if isinstance(bucket, dict) and isinstance(bucket.get("by_district"), dict):
                for district_rows in bucket["by_district"].values():
                    if isinstance(district_rows, list):
                        _apply(district_rows)

    discounts_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_discounts_from_raw(
    discounts_path: Path,
    raw_offers: list[dict[str, Any]],
) -> None:
    """Persist rematerialized rows without dropping merchant_type / quota_fill / sub_offers."""
    from collections import defaultdict

    from scraper import CATEGORIES, enrich_offer_payload, load_json

    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    if discounts_path.exists():
        try:
            prev = load_json(discounts_path)
            if isinstance(prev, dict) and prev.get("scrape_time"):
                timestamp = str(prev["scrape_time"])
        except Exception:  # noqa: BLE001
            pass

    serialised = [enrich_offer_payload(dict(raw)) for raw in raw_offers]
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted(CATEGORIES):
        category_offers = [offer for offer in serialised if offer.get("category") == category]
        districts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for offer in category_offers:
            district = offer.get("district")
            if district:
                districts[str(district)].append(offer)
        by_category[category] = {"offers": category_offers, "by_district": dict(districts)}

    discounts_path.write_text(
        json.dumps(
            {"scrape_time": timestamp, "offers": serialised, "by_category": by_category},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def rematerialize(extra_store_offers: list[dict] | None = None) -> None:
    from dataclasses import asdict

    from scraper import (
        load_chain_store_offers,
        load_json,
        load_mall_overrides,
        mall_from_json,
        merge_offers,
        offer_from_json,
        write_outputs,
    )
    from scrapers.community_calendar_scraper import apply_community_calendar_offers
    from scrapers.merchant_direct_feed import apply_merchant_direct_feed
    from scrapers.merchant_quota import apply_merchant_quota_balance
    from scrapers.merchant_taxonomy import annotate_merchant_types
    from scrapers.recurring_pattern_engine import apply_recurring_pattern_offers
    from scrapers.small_shop_scraper import apply_small_shop_offers
    from scrapers.upcoming_coverage import ensure_upcoming_coverage
    from store_authenticity import LIFECYCLE_PREVIEW_DAYS, is_within_lifecycle_window

    discounts_path = ROOT / "discounts.json"
    malls_path = ROOT / "data" / "malls-registry.json"
    reference_time = datetime.now(timezone.utc).astimezone()
    today = reference_time.date()
    existing_raw = load_json(discounts_path).get("offers", [])
    existing = [o for raw in existing_raw if (o := offer_from_json(raw))]
    dropped_stale = len(existing_raw) - len(existing)
    drop_sources = {"chain_store_offers", *INDEPENDENT_SOURCE_NAMES}
    base = [
        o
        for o in existing
        if o.source_name not in drop_sources
        and not str(o.source_name or "").startswith("payment_join:")
        and str(o.source_name or "") not in INDEPENDENT_SOURCE_NAMES
    ]
    malls = [m for raw in load_json(malls_path).get("malls", []) if (m := mall_from_json(raw))]
    known = {(m.district, m.mall_name) for m in malls}
    overrides = load_mall_overrides(ROOT / "data" / "mall_overrides.json", known, reference_time)
    chains = load_chain_store_offers(CHAIN_PATH, known, reference_time)
    extras = []
    for raw in extra_store_offers or []:
        offer = offer_from_json(raw)
        if offer:
            extras.append(offer)
    offers = merge_offers(base, overrides + chains + extras, reference_time)

    # Fill 3-day upcoming gaps using authentic store seeds (74-mall coverage).
    registry_dicts = [{"mall_name": m.mall_name, "district": m.district} for m in malls]
    filled_raw = ensure_upcoming_coverage(
        [asdict(o) for o in offers],
        registry_dicts,
        today=today,
    )
    # Recurring calendar patterns (weekend / credit / member / festival early-bird).
    filled_raw = apply_recurring_pattern_offers(
        filled_raw,
        registry_dicts,
        today=today,
    )
    # Merchant self-serve JSON/CSV submissions (six-column gated).
    filled_raw = apply_merchant_direct_feed(filled_raw, today=today)
    # Community & calendar scrape (mall / AEON / Donki / cinema → verified stores).
    filled_raw = apply_community_calendar_offers(
        filled_raw,
        registry_dicts,
        today=today,
    )
    # Independent small-shop harvest (OpenRice / curated indie seeds).
    # Prefer cache populated by `python scripts/scrapers/small_shop_scraper.py`.
    filled_raw = apply_small_shop_offers(
        filled_raw,
        today=today,
        live_fetch=False,
        persist_cache=True,
    )
    # Tag → consolidate same-store cards → unique-shop 70:30 labels → re-consolidate.
    # Do not re-annotate after quota — relabeled merchant_type must stick.
    filled_raw = annotate_merchant_types(filled_raw)
    filled_raw = consolidate_merchant_offers(filled_raw, today=today)
    filled_raw = apply_merchant_quota_balance(
        filled_raw,
        registry_dicts,
        today=today,
    )
    pre_consolidate = len(filled_raw)
    filled_raw = consolidate_merchant_offers(filled_raw, today=today)
    validated_raw = [dict(raw) for raw in filled_raw if offer_from_json(raw)]
    offers = [o for raw in validated_raw if (o := offer_from_json(raw))]

    in_window = sum(
        1
        for o in offers
        if is_within_lifecycle_window(o.start_date, o.expiry_date, today=today)
    )
    # Write mall registry via Offer path; discounts keep full rematerialize metadata.
    write_outputs(discounts_path, malls_path, offers, malls)
    _write_discounts_from_raw(discounts_path, validated_raw)
    print(
        f"[lifecycle] today={today.isoformat()} preview_days={LIFECYCLE_PREVIEW_DAYS} "
        f"dropped_stale_on_load={dropped_stale} retained={len(offers)} "
        f"in_window={in_window} pre_consolidate={pre_consolidate}"
    )
    print(
        f"rematerialized offers={len(offers)} verified_chain={len(chains)} "
        f"payment_joined={len(extras)}"
    )


async def _run_named(
    name: str, coro_factory: Callable[[], Awaitable[Any]]
) -> tuple[str, Any, float, str | None]:
    started = time.perf_counter()
    try:
        result = await coro_factory()
        return name, result, time.perf_counter() - started, None
    except Exception as exc:  # noqa: BLE001
        return name, None, time.perf_counter() - started, str(exc)


async def _gather_named(
    jobs: dict[str, Callable[[], Awaitable[Any]]],
) -> dict[str, Any]:
    """Run independent async jobs concurrently; return name -> result (or None on failure)."""
    if not jobs:
        return {}
    print(f"[channel] asyncio.gather jobs={list(jobs)} global_sem={GLOBAL_CONCURRENCY}")
    print(
        f"[channel] http timeouts connect={CONNECT_TIMEOUT_S}s read={READ_TIMEOUT_S}s "
        f"retries={MAX_RETRIES} domain_limits={DOMAIN_CONCURRENCY}"
    )
    outcomes = await asyncio.gather(
        *[_run_named(name, factory) for name, factory in jobs.items()]
    )
    results: dict[str, Any] = {}
    for name, result, elapsed, err in outcomes:
        if err:
            print(f"[channel] {name} failed ({elapsed:.1f}s): {err}")
            results[name] = None
        else:
            print(f"[channel] {name} done ({elapsed:.1f}s)")
            results[name] = result
    return results


async def async_main() -> float:
    wall_start = time.perf_counter()
    registry = load_registry_malls()
    manual = [
        {**pin, "verification_status": VERIFICATION_VERIFIED, "source": "verified_pins"}
        for pin in VERIFIED_PINS
    ]
    locator = match_locator_pins()
    print(f"[channel] curated brand_locator verified={len(locator)}")

    async with shared_http():
        # Phase 1: independent pin/offer producers — concurrent asyncio.
        phase1 = await _gather_named(
            {
                "live": lambda: scrape_live_brand_locators(registry),
                "sino": scrape_all_sino_directories,
                "shkp": scrape_all_shkp_directories,
                "swire": scrape_all_swire_directories,
                "flagship": lambda: enrich_flagship_phones(live=True, write_locators=True),
                "link": lambda: scrape_link_hanglung_directories(registry, live=True),
            }
        )

        live = phase1.get("live") or []
        sino = phase1.get("sino") or []
        shkp = phase1.get("shkp") or []
        swire = phase1.get("swire") or []
        flagship_raw = phase1.get("flagship")
        if isinstance(flagship_raw, tuple) and len(flagship_raw) == 2:
            flagship_pins, flagship_offers = flagship_raw
        else:
            flagship_pins, flagship_offers = [], []
        link_raw = phase1.get("link")
        if isinstance(link_raw, tuple) and len(link_raw) == 2:
            link_pins, link_offers = link_raw
        else:
            link_pins, link_offers = [], []

        print(f"[channel] live brand_locator verified={len(live)}")
        print(f"[channel] sino directory verified={len(sino)}")
        print(f"[channel] shkp directory verified={len(shkp)}")
        print(f"[channel] swire directory verified={len(swire)}")
        print(
            f"[channel] flagship reverse-match pins={len(flagship_pins)} "
            f"offers={len(flagship_offers)}"
        )
        print(f"[channel] link/hanglung pins={len(link_pins)} offers={len(link_offers)}")

        verified = merge_verified_pins(
            [manual, locator, live, sino, shkp, swire, flagship_pins, link_pins]
        )
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"pins": verified}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        verified_n, pending_n = apply_presence(verified)
        print(f"presence verified={verified_n} pending={pending_n} unique_pins={len(verified)}")

        sources_payload = {}
        if SOURCES_PATH.exists():
            try:
                sources_payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[channel] sources.json read failed: {exc}")
                sources_payload = {}
        source_rows = (
            list(sources_payload.get("sources") or []) if isinstance(sources_payload, dict) else []
        )
        food_live_urls = [
            str(s.get("url") or "").strip()
            for s in source_rows
            if s.get("enabled")
            and str(s.get("channel") or "").strip() == "food_court_scanner"
            and s.get("live_fetch")
            and str(s.get("url") or "").strip()
        ]

        # Phase 2: independent offer channels (payment needs verified pins).
        phase2 = await _gather_named(
            {
                "payment": lambda: scrape_payment_joined_offers(verified, registry),
                "social": lambda: asyncio.to_thread(
                    scrape_social_media_offers, registry, sources=source_rows
                ),
                "food": lambda: scrape_food_court_offers(
                    registry, live_urls=food_live_urls or None
                ),
                "community": lambda: scrape_community_offers(registry),
                "strata": lambda: scrape_strata_openrice_offers(live=True),
            }
        )

        payment_offers = phase2.get("payment") or []
        social_offers = phase2.get("social") or []
        food_offers = phase2.get("food") or []
        community_offers = phase2.get("community") or []
        strata_offers = phase2.get("strata") or []

        PAYMENT_CACHE.write_text(
            json.dumps({"offers": payment_offers}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[channel] payment authentic offers={len(payment_offers)}")
        print(f"[channel] social_media authentic offers={len(social_offers)}")
        print(f"[channel] food_court authentic offers={len(food_offers)}")
        print(f"[channel] community authentic offers={len(community_offers)}")
        print(f"[channel] strata/openrice authentic offers={len(strata_offers)}")

        independent = (
            payment_offers
            + social_offers
            + food_offers
            + community_offers
            + flagship_offers
            + link_offers
            + strata_offers
        )

        # Phase 3: multi-group developer APIs → upcoming density (needs store seeds).
        try:
            multi_offers = await scrape_multi_group_upcoming_offers(
                existing_offers=independent
                + [
                    {
                        "offer_type": "store",
                        "mall_name": p.get("mall_name"),
                        "district": p.get("district"),
                        "store_name": p.get("store_name"),
                        "floor": p.get("floor"),
                        "shop_number": p.get("shop_number"),
                        "phone": p.get("phone"),
                        "source_url": p.get("source_url") or p.get("source") or "",
                    }
                    for p in verified
                    if p.get("mall_name") and p.get("phone")
                ]
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[channel] multi_group failed: {exc}")
            multi_offers = []
        print(f"[channel] multi_group upcoming offers={len(multi_offers)}")
        independent = independent + multi_offers

        dedup: dict[tuple[str, str, str, str], dict] = {}
        for row in independent:
            key = (
                str(row.get("mall_name") or ""),
                str(row.get("store_name") or ""),
                str(row.get("title") or ""),
                str(row.get("expiry_date") or ""),
            )
            dedup[key] = row
        independent = list(dedup.values())
        INDEPENDENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        INDEPENDENT_CACHE.write_text(
            json.dumps({"offers": independent}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[channel] independent store offers total={len(independent)}")
        rematerialize(independent)

    wall = time.perf_counter() - wall_start
    speedup = (BASELINE_THREADPOOL_WALL_S / wall) if wall > 0 else 0.0
    print(
        f"[channel] expand wall_clock={wall:.1f}s "
        f"(baseline_threadpool={BASELINE_THREADPOOL_WALL_S:.1f}s, "
        f"speedup={speedup:.2f}x)"
    )
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARK_PATH.write_text(
        json.dumps(
            {
                "baseline_threadpool_wall_s": BASELINE_THREADPOOL_WALL_S,
                "asyncio_httpx_wall_s": round(wall, 2),
                "speedup_x": round(speedup, 3),
                "measured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "runtime": {
                    "global_concurrency": GLOBAL_CONCURRENCY,
                    "domain_concurrency": DOMAIN_CONCURRENCY,
                    "connect_timeout_s": CONNECT_TIMEOUT_S,
                    "read_timeout_s": READ_TIMEOUT_S,
                    "max_retries": MAX_RETRIES,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return wall


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
