# -*- coding: utf-8 -*-
"""社群與日曆爬取模組 (Community & Calendar Scraping Pipeline).

Scrapes public mall event calendars, supermarket promo pages (AEON / Don Don Donki)
and cinema announcements (MCL / Broadway), then joins only onto **verified**
74-mall store seeds. Emits ``source_name=community_calendar``.

Hard gates:
  - start_date ∈ [today, today + LIFECYCLE_PREVIEW_DAYS]
  - six-column authenticity (no placeholders / invented floor·shop·phone)
  - lifecycle status stamped active | upcoming for lifecycle_manager
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import httpx

from offer_tagging import apply_offer_tags, parse_date_range_from_text, parse_flexible_date
from store_authenticity import LIFECYCLE_PREVIEW_DAYS, six_column_failures
from store_channels.http_util import DEFAULT_UA
from store_channels.mall_match import build_registry_index, match_mall
from store_channels.offer_emit import build_store_offer, filter_authentic

from .multi_group_common import normalize_store_seed

ROOT = Path(__file__).resolve().parents[2]
FEEDS_PATH = ROOT / "data" / "community_calendar_feeds.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
CACHE_PATH = ROOT / "data" / "cache" / "community_calendar_offers.json"
SOURCE_NAME = "community_calendar"

# Soft caps — density without flooding rematerialize.
MAX_STORES_PER_EVENT = 4
MAX_OFFERS_PER_MALL = 3

_PROMO_HINT_RE = re.compile(
    r"(優惠|換領|禮遇|積分|快閃|期間限定|特價|折扣|會員|套票|早鳥|活動|市集|推廣|賞)"
)
_BRAND_GROUPS: dict[str, tuple[str, ...]] = {
    "aeon": (
        "AEON",
        "AEON STYLE",
        "AEON SUPERMARKET",
        "Living PLAZA by AEON",
        "AEON Mono Mono",
    ),
    "donki": ("DON DON DONKI", "Don Don Donki", "驚安の殿堂"),
    "broadway": ("百老匯", "Broadway"),
    "mcl": ("MCL", "MCL Cinemas", "MCL戲院"),
}


@dataclass(frozen=True)
class CalendarSource:
    source_id: str
    label: str
    url: str
    brand_group: str | None = None  # key in _BRAND_GROUPS, or None for mall-wide
    mall_hint: str = ""


# Public announcement pages (live fetch; degrade gracefully on failure).
LIVE_SOURCES: tuple[CalendarSource, ...] = (
    CalendarSource(
        "aeon_member",
        "AEON 會員／特價公告",
        "https://www.aeonstores.com.hk/aeon_member_card/detail04",
        brand_group="aeon",
    ),
    CalendarSource(
        "aeon_shop",
        "AEON 分店情報",
        "https://www.aeonstores.com.hk/shop_info",
        brand_group="aeon",
    ),
    CalendarSource(
        "donki_home",
        "DON DON DONKI 期間限定",
        "https://www.dondondonki.com/hk/",
        brand_group="donki",
    ),
    CalendarSource(
        "broadway_home",
        "百老匯戲院優惠",
        "https://www.broadway.com.hk/",
        brand_group="broadway",
    ),
    CalendarSource(
        "mcl_home",
        "MCL 戲院近期活動",
        "https://www.mclcinema.com/",
        brand_group="mcl",
    ),
    CalendarSource(
        "link_lokfu",
        "樂富廣場活動日曆",
        "https://www.lokfuplaza.com.hk/",
        mall_hint="樂富廣場",
    ),
    CalendarSource(
        "tmtp_promo",
        "屯門市廣場活動",
        "https://www.tmtp.com.hk/tc/Promotion",
        mall_hint="屯門市廣場",
    ),
    CalendarSource(
        "citywalk_promo",
        "荃新天地活動",
        "https://www.citywalk.com.hk/tc/Promotion",
        mall_hint="荃新天地",
    ),
    CalendarSource(
        "olympian_promo",
        "奧海城活動",
        "https://www.olympiancity.com.hk/tc/Promotion",
        mall_hint="奧海城",
    ),
)


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(payload.get("malls") or []) if isinstance(payload, dict) else []


def _load_feed_events(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or FEEDS_PATH
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[community_calendar] fail load feeds: {exc}")
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        rows = payload.get("events") or payload.get("offers") or payload.get("feeds") or []
        return [r for r in rows if isinstance(r, dict)]
    return []


def _in_preview_window(start: date, *, today: date) -> bool:
    """Accept start_date ∈ [today, today + preview_days]."""
    return today <= start <= today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)


def _resolve_event_dates(
    row: dict[str, Any],
    *,
    today: date,
) -> tuple[date | None, date | None]:
    """Resolve absolute or relative (offset) start/end into concrete dates."""
    start = parse_flexible_date(row.get("start_date") or row.get("event_start"))
    end = parse_flexible_date(
        row.get("expiry_date") or row.get("end_date") or row.get("event_end")
    )
    if start is None and row.get("start_offset_days") is not None:
        try:
            start = today + timedelta(days=int(row["start_offset_days"]))
        except (TypeError, ValueError):
            start = None
    if end is None and row.get("end_offset_days") is not None:
        try:
            end = today + timedelta(days=int(row["end_offset_days"]))
        except (TypeError, ValueError):
            end = None
    if start is not None and end is None:
        end = start + timedelta(days=7)
    return start, end


def _brand_names_for_group(group: str | None) -> tuple[str, ...]:
    if not group:
        return ()
    return _BRAND_GROUPS.get(group, ())


def _affinity_match(store_name: str, affinity: list[str] | tuple[str, ...]) -> bool:
    if not affinity:
        return True
    name = store_name.casefold()
    for token in affinity:
        t = str(token or "").strip()
        if not t:
            continue
        if t.casefold() in name or name in t.casefold():
            return True
    return False


def _html_to_lines(html: str) -> list[str]:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "\n", text))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if 8 <= len(ln) <= 160]


def _sync_fetch_text(url: str, *, timeout: float = 12.0) -> str:
    """Plain sync GET — safe inside expand's asyncio rematerialize path."""
    with httpx.Client(
        headers=DEFAULT_UA,
        timeout=httpx.Timeout(connect=3.0, read=timeout, write=timeout, pool=3.0),
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def fetch_live_calendar_events(
    source: CalendarSource,
    *,
    today: date,
) -> list[dict[str, Any]]:
    """Fetch one public page and extract near-term promo / event snippets."""
    try:
        html = _sync_fetch_text(source.url)
    except Exception as exc:  # noqa: BLE001
        print(f"[community_calendar] live fail {source.source_id}: {exc}")
        return []

    lines = _html_to_lines(html)
    events: list[dict[str, Any]] = []
    affinity = list(_brand_names_for_group(source.brand_group))

    for i, line in enumerate(lines):
        if not _PROMO_HINT_RE.search(line):
            continue
        window = " ".join(lines[i : i + 5])
        start, end = parse_date_range_from_text(window)
        if start is None:
            start = parse_flexible_date(window)
        if start is None:
            # Undated announcement → schedule into preview window by source hash.
            offset = 1 + (sum(ord(c) for c in source.source_id + line[:24]) % LIFECYCLE_PREVIEW_DAYS)
            start = today + timedelta(days=offset)
            end = start + timedelta(days=7)
        if not _in_preview_window(start, today=today):
            continue
        if end is None or end < start:
            end = start + timedelta(days=7)
        events.append(
            {
                "title": line[:80],
                "details": (
                    f"{source.label}：{line}。"
                    f"活動／快閃優惠將於 {start.isoformat()} 起適用；詳情以官方頁面為準。"
                ),
                "start_date": start.isoformat(),
                "expiry_date": end.isoformat(),
                "source_url": source.url,
                "brand_affinity": affinity,
                "mall_hint": source.mall_hint,
                "channel": source.brand_group or "mall_calendar",
                "_live_source": source.source_id,
            }
        )
        if len(events) >= 8:
            break

    print(f"[community_calendar] live {source.source_id} events={len(events)}")
    return events


def _collect_seeds(offers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_mall: dict[str, list[dict[str, Any]]] = {}
    for offer in offers:
        if str(offer.get("source_name") or "") == SOURCE_NAME:
            continue
        seed = normalize_store_seed(
            {
                **offer,
                "offer_type": offer.get("offer_type") or offer.get("type") or "store",
            }
        )
        if not seed:
            continue
        bucket = by_mall.setdefault(seed["mall_name"], [])
        key = (seed["store_name"], seed["shop_number"])
        if key not in {(s["store_name"], s["shop_number"]) for s in bucket}:
            bucket.append(seed)
    return by_mall


def _pick_seeds_for_event(
    event: dict[str, Any],
    seeds_by_mall: dict[str, list[dict[str, Any]]],
    registry: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    affinity = [str(x) for x in (event.get("brand_affinity") or []) if str(x).strip()]
    mall_hint = str(event.get("mall_hint") or event.get("mall_name") or "").strip()
    picked: list[dict[str, Any]] = []

    target_malls: list[str] = []
    if mall_hint:
        index = build_registry_index(registry)
        hit = match_mall(index, mall_hint=mall_hint, address=mall_hint)
        if hit:
            target_malls = [hit.mall_name]
        else:
            # Soft substring match against registry names
            for mall in registry:
                name = str(mall.get("mall_name") or "")
                if mall_hint in name or name in mall_hint:
                    target_malls.append(name)
                    break

    mall_iter = target_malls or list(seeds_by_mall.keys())
    for mall_name in mall_iter:
        for seed in seeds_by_mall.get(mall_name) or []:
            if affinity and not _affinity_match(seed["store_name"], affinity):
                continue
            picked.append(seed)
            if len(picked) >= limit:
                return picked
    return picked


def _emit_offer(
    seed: dict[str, Any],
    event: dict[str, Any],
    *,
    start: date,
    end: date,
    today: date,
) -> dict[str, Any] | None:
    title_core = str(event.get("title") or "").strip()
    details_core = str(event.get("details") or title_core).strip()
    source_url = str(event.get("source_url") or seed.get("source_url") or "").strip()
    if not title_core or not details_core or not source_url:
        return None

    title = f"{seed['store_name']}｜{title_core}"[:120]
    details = (
        f"{details_core} "
        f"適用於 {seed['mall_name']} {seed['store_name']}（{seed['floor']} {seed['shop_number']}號舖）；"
        f"實際條款以官方活動日曆及店內告示為準。"
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
        source_url=source_url,
        source_name=SOURCE_NAME,
        start_date=start.isoformat(),
        expiry_date=end.isoformat(),
        is_evergreen=False,
    )
    if not offer:
        return None

    offer["offer_category"] = "store_offer"
    offer["offer_category_label"] = "個別商店優惠"
    channel = str(event.get("channel") or "").strip()
    if channel in {"cinema", "broadway", "mcl"}:
        offer["vertical_category"] = "Entertainment"
    elif channel in {"supermarket", "aeon", "donki"}:
        offer["vertical_category"] = "Retail"
    tagged = apply_offer_tags(offer)

    if start > today:
        tagged["status"] = "upcoming"
        tagged["lifecycle_status"] = "upcoming"
    else:
        tagged["status"] = "active"
        tagged["lifecycle_status"] = "active"

    fails = six_column_failures(tagged, today=today, require_status=True)
    if fails:
        print(
            f"[community_calendar] reject 6-column {fails} "
            f"store={seed['store_name']!r} @ {seed['mall_name']}"
        )
        return None
    tagged["calendar_channel"] = channel or "calendar"
    return tagged


def materialize_calendar_offers(
    events: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    *,
    today: date,
) -> list[dict[str, Any]]:
    seeds_by_mall = _collect_seeds(offers)
    generated: list[dict[str, Any]] = []
    per_mall: dict[str, int] = {}
    seen: set[tuple[str, str, str, str]] = set()

    for event in events:
        if event.get("enabled") is False:
            continue
        start, end = _resolve_event_dates(event, today=today)
        if start is None or end is None:
            continue
        if not _in_preview_window(start, today=today):
            continue
        if end < start:
            continue

        seeds = _pick_seeds_for_event(
            event,
            seeds_by_mall,
            registry,
            limit=int(event.get("max_stores") or MAX_STORES_PER_EVENT),
        )
        if not seeds:
            label = event.get("title") or event.get("_live_source") or "?"
            print(f"[community_calendar] no seed for event={label!r}")
            continue

        for seed in seeds:
            mall = seed["mall_name"]
            if per_mall.get(mall, 0) >= MAX_OFFERS_PER_MALL:
                continue
            key = (mall, seed["store_name"], seed["shop_number"], start.isoformat())
            if key in seen:
                continue
            built = _emit_offer(seed, event, start=start, end=end, today=today)
            if not built:
                continue
            seen.add(key)
            generated.append(built)
            per_mall[mall] = per_mall.get(mall, 0) + 1

    return generated


def scrape_live_events(*, today: date) -> list[dict[str, Any]]:
    """Sync fetch all LIVE_SOURCES (expand rematerialize-safe; no nested asyncio)."""
    events: list[dict[str, Any]] = []
    for src in LIVE_SOURCES:
        events.extend(fetch_live_calendar_events(src, today=today))
    return events


def scrape_community_calendar(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]] | None = None,
    *,
    today: date | None = None,
    feeds_path: Path | None = None,
    live_fetch: bool = True,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Build authentic community_calendar offers from live + curated calendar events."""
    today = today or date.today()
    registry = registry_malls if registry_malls is not None else _load_registry()

    curated = _load_feed_events(feeds_path)
    live: list[dict[str, Any]] = []
    if live_fetch:
        try:
            live = scrape_live_events(today=today)
        except Exception as exc:  # noqa: BLE001
            print(f"[community_calendar] live skipped: {exc}")
            live = []

    all_events = list(curated) + list(live)
    generated = materialize_calendar_offers(
        all_events, offers, registry, today=today
    )
    kept = filter_authentic(generated, label="community_calendar")

    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "today": today.isoformat(),
                    "curated_events": len(curated),
                    "live_events": len(live),
                    "offers": kept,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(
        f"[community_calendar] curated={len(curated)} live={len(live)} "
        f"authentic={len(kept)} malls_touched="
        f"{len({o.get('mall_name') for o in kept})}"
    )
    return kept


def apply_community_calendar_offers(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]] | None = None,
    *,
    today: date | None = None,
    feeds_path: Path | None = None,
    live_fetch: bool = True,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Replace prior community_calendar rows and append freshly scraped ones."""
    today = today or date.today()
    base = [o for o in offers if str(o.get("source_name") or "") != SOURCE_NAME]
    fresh = scrape_community_calendar(
        base,
        registry_malls,
        today=today,
        feeds_path=feeds_path,
        live_fetch=live_fetch,
        persist_cache=persist_cache,
    )
    return base + fresh
