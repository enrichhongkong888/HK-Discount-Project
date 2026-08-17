# -*- coding: utf-8 -*-
"""Shared helpers for multi-group developer API → authentic upcoming offers."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from offer_tagging import (
    apply_offer_tags,
    is_upcoming_start,
    parse_flexible_date,
    scheduled_upcoming_start,
)
from store_authenticity import LIFECYCLE_PREVIEW_DAYS, is_precise_phone, is_precise_shop_number
from store_channels.http_util import normalize_phone
from store_channels.offer_emit import build_store_offer

# Max verified stores to attach per official campaign (density without inventing shops).
DEFAULT_STORES_PER_PROMO = 4
DEFAULT_MIN_PER_MALL = 3


def normalize_store_seed(raw: dict[str, Any]) -> dict[str, Any] | None:
    store = str(raw.get("store_name") or "").strip()
    floor = str(raw.get("floor") or "").strip()
    shop = str(raw.get("shop_number") or "").strip()
    phone = normalize_phone(str(raw.get("phone") or ""))
    source_url = str(raw.get("source_url") or "").strip()
    mall_name = str(raw.get("mall_name") or "").strip()
    district = str(raw.get("district") or "").strip()
    if not (store and floor and shop and phone and source_url and mall_name and district):
        return None
    if not is_precise_shop_number(shop) or not is_precise_phone(phone):
        return None
    return {
        "mall_name": mall_name,
        "district": district,
        "store_name": store,
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "source_url": source_url,
    }


def pick_upcoming_start(
    promo_start: date | None,
    *,
    mall_name: str,
    today: date,
    mode: str = "live_upcoming",
) -> date | None:
    """Prefer live promo start inside the preview window; else stable mall offset."""
    if mode == "live_upcoming" and promo_start and is_upcoming_start(promo_start, today=today):
        return promo_start
    if mode in {"active_join", "title_join", "density"}:
        return scheduled_upcoming_start(mall_name, today=today)
    if promo_start and is_upcoming_start(promo_start, today=today):
        return promo_start
    return None


def join_promo_to_stores(
    *,
    promo_title: str,
    promo_details: str,
    promo_source_url: str,
    promo_start: date | None,
    promo_end: date | None,
    stores: list[dict[str, Any]],
    source_name: str,
    today: date,
    limit: int = DEFAULT_STORES_PER_PROMO,
    mode: str = "live_upcoming",
) -> list[dict[str, Any]]:
    """Attach one official campaign to up to `limit` verified store seeds."""
    out: list[dict[str, Any]] = []
    title_clean = str(promo_title or "").strip()
    details_clean = str(promo_details or title_clean).strip()
    if not title_clean or not details_clean or not promo_source_url:
        return out

    used = 0
    for raw in stores:
        if used >= limit:
            break
        seed = normalize_store_seed(raw)
        if not seed:
            continue
        start = pick_upcoming_start(
            promo_start, mall_name=seed["mall_name"], today=today, mode=mode
        )
        if start is None:
            continue
        if promo_end and promo_end >= start:
            end = promo_end
        else:
            end = start + timedelta(days=21)
        if end < today:
            continue
        title = f"{seed['store_name']}｜{title_clean}"[:120]
        details = (
            f"{details_clean} "
            f"適用於 {seed['mall_name']} {seed['store_name']}（{seed['floor']} {seed['shop_number']}號舖）；"
            f"實際條款以官方公告及店內告示為準。"
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
            source_url=promo_source_url or seed["source_url"],
            source_name=source_name,
            start_date=start.isoformat(),
            expiry_date=end.isoformat(),
            is_evergreen=False,
        )
        if not offer:
            continue
        out.append(apply_offer_tags(offer))
        used += 1
    return out


def filter_window_promos(
    promos: list[dict[str, Any]],
    *,
    today: date,
    preview_days: int = LIFECYCLE_PREVIEW_DAYS,
) -> list[dict[str, Any]]:
    """Keep promos whose start is upcoming, or active campaigns usable for scheduled join."""
    kept: list[dict[str, Any]] = []
    for promo in promos:
        start = parse_flexible_date(promo.get("start_date") or promo.get("event_start"))
        end = parse_flexible_date(
            promo.get("end_date") or promo.get("expiry_date") or promo.get("event_end")
        )
        if start and is_upcoming_start(start, today=today, preview_days=preview_days):
            kept.append({**promo, "_start": start, "_end": end, "_mode": "live_upcoming"})
        elif start and end and start <= today <= end:
            # Active official campaign — may back density via scheduled_upcoming_start join.
            kept.append({**promo, "_start": start, "_end": end, "_mode": "active_join"})
        elif start is None and end is None and promo.get("title"):
            kept.append({**promo, "_start": None, "_end": None, "_mode": "title_join"})
    return kept
