# -*- coding: utf-8 -*-
"""Shared helpers for emitting authenticity-gated independent store offers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from store_authenticity import authenticity_failures, is_authentic_store_payload


def hk_today() -> date:
    return datetime.now(timezone.utc).astimezone().date()


def rolling_window(*, days: int = 0) -> tuple[str, str]:
    """Return ISO start/expiry for evergreen rematerialize (same-day by default)."""
    today = hk_today()
    end = today + timedelta(days=max(0, days))
    return today.isoformat(), end.isoformat()


def build_store_offer(
    *,
    mall_name: str,
    district: str,
    store_name: str,
    floor: str,
    shop_number: str,
    phone: str,
    title: str,
    details: str,
    source_url: str,
    source_name: str,
    start_date: str | None = None,
    expiry_date: str | None = None,
    is_evergreen: bool = False,
    category: str = "商場優惠",
) -> dict[str, Any] | None:
    """Build a store-offer dict; return None when six-field / lifecycle gates fail."""
    if is_evergreen or not start_date or not expiry_date:
        start_date, expiry_date = rolling_window(days=0)
    created = f"{start_date}T00:00:00+08:00"
    offer: dict[str, Any] = {
        "title": str(title or "").strip(),
        "category": category,
        "offer_type": "store",
        "is_daily_special": False,
        "is_evergreen": bool(is_evergreen),
        "created_date": start_date,
        "created_at": created,
        "start_date": start_date,
        "expiry_date": expiry_date,
        "discount_info": str(details or "").strip()[:120],
        "details": str(details or "").strip(),
        "source_url": str(source_url or "").strip(),
        "image_url": None,
        "mall_name": str(mall_name or "").strip(),
        "district": str(district or "").strip(),
        "store_name": str(store_name or "").strip(),
        "floor": str(floor or "").strip(),
        "shop_number": str(shop_number or "").strip(),
        "phone": str(phone or "").strip(),
        "source_name": source_name,
    }
    if not is_authentic_store_payload(offer):
        return None
    return offer


def filter_authentic(offers: list[dict[str, Any]], *, label: str) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for offer in offers:
        if is_authentic_store_payload(offer):
            kept.append(offer)
        else:
            fails = authenticity_failures(offer)
            print(
                f"[{label}] reject {offer.get('store_name')}@{offer.get('mall_name')}: {fails}"
            )
    return kept
