# -*- coding: utf-8 -*-
"""District community / indie-shop feed aggregator.

Reads:
- data/sources.json entries with channel=community_aggregator
- data/community_offer_feeds.json curated rows

Cross-matches mall_hint / address / keywords onto the 74-mall registry and
emits only offers that pass store_authenticity six-field + lifecycle gates.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from store_authenticity import is_precise_phone, is_precise_shop_number

from .http_util import afetch_text, normalize_phone
from .mall_match import build_registry_index, match_mall
from .offer_emit import build_store_offer, filter_authentic
from .social_media_parser import extract_fields_from_caption

ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = ROOT / "data" / "sources.json"
FEEDS_PATH = ROOT / "data" / "community_offer_feeds.json"
SOURCE_NAME = "community_aggregator"

_KEYWORD_RE = re.compile(
    r"(小店|市集|街坊|週年慶|美食廣場|獨立店|期間限定|快閃|手作|本地品牌)"
)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[community] fail load {path}: {exc}")
        return None


def load_community_sources(sources_path: Path | None = None) -> list[dict[str, Any]]:
    payload = _load_json(sources_path or SOURCES_PATH)
    if not isinstance(payload, dict):
        return []
    rows = []
    for src in payload.get("sources") or []:
        if not isinstance(src, dict):
            continue
        if str(src.get("channel") or "").strip() != "community_aggregator":
            continue
        rows.append(src)
    return rows


def _feed_rows(path: Path | None = None) -> list[dict[str, Any]]:
    payload = _load_json(path or FEEDS_PATH)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [r for r in (payload.get("offers") or payload.get("feeds") or []) if isinstance(r, dict)]
    return []


def _keywords_match(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return bool(_KEYWORD_RE.search(text))
    blob = text.casefold()
    return any(str(k).casefold() in blob for k in keywords if str(k).strip())


def row_to_offer(
    row: dict[str, Any],
    registry_malls: list[dict],
    *,
    default_source_url: str = "",
    keywords: list[str] | None = None,
) -> dict[str, Any] | None:
    if row.get("enabled") is False:
        return None
    blob = " ".join(
        str(row.get(k) or "")
        for k in (
            "mall_hint",
            "mall_name",
            "address",
            "title",
            "details",
            "caption",
            "store_name",
            "keywords",
        )
    )
    if keywords is not None and not _keywords_match(blob, keywords):
        return None

    extracted = extract_fields_from_caption(str(row.get("caption") or row.get("details") or ""))
    store_name = str(row.get("store_name") or extracted.get("store_name") or "").strip()
    floor = str(row.get("floor") or extracted.get("floor") or "").strip()
    shop = str(row.get("shop_number") or extracted.get("shop_number") or "").strip()
    phone = normalize_phone(str(row.get("phone") or extracted.get("phone") or ""))
    details = str(row.get("details") or row.get("offer_text") or row.get("caption") or "").strip()
    title = str(row.get("title") or "").strip() or f"街坊小店優惠：{store_name or '獨立店舖'}"
    source_url = str(row.get("source_url") or default_source_url or "").strip()
    start = str(row.get("start_date") or extracted.get("start_date") or "").strip() or None
    end = str(row.get("expiry_date") or extracted.get("expiry_date") or "").strip() or None

    if not source_url:
        return None
    if not (store_name and floor and is_precise_shop_number(shop) and is_precise_phone(phone)):
        return None
    if not details:
        return None

    index = build_registry_index(registry_malls)
    hint = str(row.get("mall_hint") or row.get("mall_name") or blob).strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit:
        print(f"[community] unmatched mall hint={hint!r} store={store_name}")
        return None

    return build_store_offer(
        mall_name=hit.mall_name,
        district=hit.district,
        store_name=store_name,
        floor=floor,
        shop_number=shop,
        phone=phone,
        title=title,
        details=details[:500],
        source_url=source_url,
        source_name=SOURCE_NAME,
        start_date=start,
        expiry_date=end,
        is_evergreen=bool(row.get("is_evergreen")),
    )


async def _fetch_source_snippets(src: dict[str, Any]) -> list[dict[str, Any]]:
    """Optional live fetch: only keeps snippets that already look complete."""
    url = str(src.get("url") or "").strip()
    if not url or not src.get("live_fetch"):
        return []
    try:
        html = await afetch_text(url, timeout=40)
    except Exception as exc:  # noqa: BLE001
        print(f"[community] live fetch fail {url}: {exc}")
        return []
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    rows: list[dict[str, Any]] = []
    for chunk in re.split(r"\n{2,}", text):
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if len(chunk) < 40 or len(chunk) > 600:
            continue
        if not _KEYWORD_RE.search(chunk):
            continue
        extracted = extract_fields_from_caption(chunk)
        if not (
            extracted.get("store_name")
            and extracted.get("floor")
            and extracted.get("shop_number")
            and extracted.get("phone")
        ):
            continue
        rows.append(
            {
                **extracted,
                "details": chunk,
                "caption": chunk,
                "source_url": url,
                "mall_hint": str(src.get("mall", {}).get("mall_name") or src.get("name") or chunk),
                "address": str(src.get("mall", {}).get("address") or ""),
            }
        )
    print(f"[community] live snippets from {url}: {len(rows)}")
    return rows


async def scrape_community_offers(
    registry_malls: list[dict],
    *,
    sources_path: Path | None = None,
    feeds_path: Path | None = None,
) -> list[dict[str, Any]]:
    sources = load_community_sources(sources_path)
    default_feeds_path = (feeds_path or FEEDS_PATH).resolve()
    feeds = _feed_rows(default_feeds_path)
    seen_feed_paths = {default_feeds_path}
    offers: list[dict[str, Any]] = []

    for row in feeds:
        offer = row_to_offer(row, registry_malls)
        if offer:
            offers.append(offer)

    live_sources = [src for src in sources if src.get("enabled")]
    live_snippets = await asyncio.gather(*[_fetch_source_snippets(src) for src in live_sources])

    for src, snippets in zip(live_sources, live_snippets):
        keywords = [str(k) for k in (src.get("match_keywords") or [])]
        default_url = str(src.get("url") or "").strip()
        for row in src.get("curated_offers") or []:
            if isinstance(row, dict):
                offer = row_to_offer(
                    row,
                    registry_malls,
                    default_source_url=default_url,
                    keywords=keywords or None,
                )
                if offer:
                    offers.append(offer)
        feed_rel = src.get("feed_path")
        if feed_rel:
            path = (ROOT / str(feed_rel)).resolve()
            if path not in seen_feed_paths:
                seen_feed_paths.add(path)
                for row in _feed_rows(path):
                    offer = row_to_offer(
                        row,
                        registry_malls,
                        default_source_url=default_url,
                        keywords=keywords or None,
                    )
                    if offer:
                        offers.append(offer)
        for row in snippets:
            offer = row_to_offer(
                row,
                registry_malls,
                default_source_url=default_url,
                keywords=keywords or None,
            )
            if offer:
                offers.append(offer)

    kept = filter_authentic(offers, label="community")
    print(
        f"[community] sources={len(sources)} feed_rows={len(feeds)} "
        f"authentic_offers={len(kept)}"
    )
    return kept
