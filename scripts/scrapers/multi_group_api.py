# -*- coding: utf-8 -*-
"""Orchestrate SHKP / Swire / Sino multi-group upcoming offer scrapes."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from store_channels.offer_emit import filter_authentic

from .shkp_api import scrape_shkp_upcoming_offers
from .sino_api import scrape_sino_upcoming_offers
from .swire_api import scrape_swire_upcoming_offers

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "multi_group_upcoming_offers.json"
SOURCE_NAMES = frozenset({"shkp_api", "swire_api", "sino_api", "multi_group_api"})


async def scrape_multi_group_upcoming_offers(
    *,
    today: date | None = None,
    existing_offers: list[dict[str, Any]] | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    existing = existing_offers or []
    groups = await asyncio.gather(
        scrape_shkp_upcoming_offers(today=today, existing_offers=existing, persist_cache=True),
        scrape_swire_upcoming_offers(today=today, existing_offers=existing, persist_cache=True),
        scrape_sino_upcoming_offers(today=today, persist_cache=True),
        return_exceptions=True,
    )
    offers: list[dict[str, Any]] = []
    labels = ("shkp", "swire", "sino")
    for label, result in zip(labels, groups, strict=True):
        if isinstance(result, Exception):
            print(f"[multi_group] {label} failed: {result}")
            continue
        offers.extend(result or [])

    uniq: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for offer in offers:
        key = (
            str(offer.get("mall_name") or ""),
            str(offer.get("store_name") or ""),
            str(offer.get("shop_number") or ""),
            str(offer.get("start_date") or ""),
        )
        uniq[key] = offer
    kept = filter_authentic(list(uniq.values()), label="multi_group")
    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"offers": kept, "today": today.isoformat()}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(f"[multi_group] authentic_upcoming_offers={len(kept)}")
    return kept
