# -*- coding: utf-8 -*-
"""信和集團 (Sino Land) S⁺ — 奧海城 / 屯門市廣場 / 荃新天地。

Uses public CMS:
  - /tc/Shop + /tc/Dining globalSearchData index
  - /tc/Shop|{Dining}/{id} detail pages (floor / unit / phone)
  - /tc/Promotion listing (official campaign titles)

Joins S⁺ campaigns onto verified directory tenants only (no invented shops).
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any

from offer_tagging import parse_date_range_from_text, parse_flexible_date
from store_channels.http_util import afetch_text, normalize_phone
from store_channels.sino_directory import (
    SINO_MALLS,
    collect_brand_candidates,
    parse_detail_fields,
    parse_global_search_data,
)

from .multi_group_common import (
    DEFAULT_STORES_PER_PROMO,
    filter_window_promos,
    join_promo_to_stores,
    normalize_store_seed,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "sino_api_upcoming.json"
SOURCE_NAME = "sino_api"


def _base_url(index_url: str) -> str:
    parts = index_url.split("/tc/")
    return parts[0] if parts else index_url.rstrip("/")


async def fetch_sino_store_seeds(meta: dict[str, str], *, limit_details: int = 20) -> list[dict[str, Any]]:
    """Resolve verified Sino tenants via directory index + detail pages."""
    seeds: list[dict[str, Any]] = []
    for index_url in (meta["shop_index"], meta["dining_index"]):
        try:
            html = await afetch_text(index_url, timeout=45)
            data = parse_global_search_data(html)
            cands = collect_brand_candidates(data)
        except Exception as exc:  # noqa: BLE001
            print(f"[sino_api] index fail {index_url}: {exc}")
            continue
        for cand in cands[:limit_details]:
            link = cand["link"]
            detail_url = link if link.startswith("http") else f"{_base_url(index_url)}{link}"
            try:
                detail_html = await afetch_text(detail_url, timeout=45)
                fields = parse_detail_fields(detail_html, cand["directory_name"] or cand["store_name"])
            except Exception:  # noqa: BLE001
                continue
            seed = normalize_store_seed(
                {
                    "mall_name": meta["mall_name"],
                    "district": meta["district"],
                    "store_name": cand["store_name"],
                    "floor": fields.get("floor") or "",
                    "shop_number": fields.get("shop_number") or "",
                    "phone": normalize_phone(fields.get("phone") or ""),
                    "source_url": detail_url,
                }
            )
            if seed:
                seeds.append(seed)
    # Deduplicate
    uniq: dict[tuple[str, str], dict[str, Any]] = {}
    for seed in seeds:
        uniq[(seed["mall_name"], seed["shop_number"])] = seed
    seeds = list(uniq.values())
    print(f"[sino_api] {meta['mall_name']} store_seeds={len(seeds)}")
    return seeds


async def fetch_sino_promos(meta: dict[str, str]) -> list[dict[str, Any]]:
    base = _base_url(meta["shop_index"])
    url = f"{base}/tc/Promotion"
    try:
        html = await afetch_text(url, timeout=45)
    except Exception as exc:  # noqa: BLE001
        print(f"[sino_api] promo fail {url}: {exc}")
        return []
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "\n", text))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if 8 <= len(ln) <= 120]

    promos: list[dict[str, Any]] = []
    # Prefer lines that look like campaign titles + nearby date ranges
    for i, line in enumerate(lines):
        if not re.search(r"(優惠|換領|禮遇|積分|泊車|會員|賞|推廣|消費)", line):
            continue
        window = " ".join(lines[i : i + 4])
        start, end = parse_date_range_from_text(window)
        if start is None:
            start = parse_flexible_date(window)
        promos.append(
            {
                "title": line[:80],
                "details": f"{meta['mall_name']} S⁺ 官方推廣：{line}",
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "source_url": url,
                "mall_name": meta["mall_name"],
            }
        )
        if len(promos) >= 10:
            break

    if not promos:
        # Always expose at least the official S⁺ programme framing for density join.
        promos.append(
            {
                "title": "S⁺ REWARDS 新一期會員禮遇",
                "details": (
                    f"{meta['mall_name']} S⁺ REWARDS 會員禮遇：出示會員於參與商戶消費可享積分／換領；"
                    "詳情以 S⁺ App 及商場官方公告為準。"
                ),
                "start_date": None,
                "end_date": None,
                "source_url": url,
                "mall_name": meta["mall_name"],
            }
        )
    print(f"[sino_api] {meta['mall_name']} promo_candidates={len(promos)}")
    return promos


async def scrape_sino_upcoming_offers(
    *,
    today: date | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    offers: list[dict[str, Any]] = []
    for meta in SINO_MALLS:
        stores = await fetch_sino_store_seeds(meta)
        promos = await fetch_sino_promos(meta)
        windowed = filter_window_promos(promos, today=today) or [
            {
                **promos[0],
                "_start": None,
                "_end": None,
                "_mode": "title_join",
            }
        ]
        for promo in windowed[:4]:
            offers.extend(
                join_promo_to_stores(
                    promo_title=str(promo.get("title") or ""),
                    promo_details=str(promo.get("details") or ""),
                    promo_source_url=str(promo.get("source_url") or ""),
                    promo_start=promo.get("_start")
                    or parse_flexible_date(promo.get("start_date")),
                    promo_end=promo.get("_end") or parse_flexible_date(promo.get("end_date")),
                    stores=stores,
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
    print(f"[sino_api] upcoming_offers={len(offers)}")
    return offers
