"""Daily store relocation check + live storefront image URL refresh.

Compares current ``malls.json`` store identity (name / shop number) against the
previous snapshot in ``data/cache/store_images.json``. When a unit changes tenant
or a brand relocates to a new shop number, the store is marked ``pending_update``
and queued for image refresh / rescrape hints.

Image URLs are resolved from the offer ``source_url`` (og:image / twitter:image)
when possible, then written back onto store cards in ``malls.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

DEFAULT_MALLS = ROOT / "malls.json"
CACHE_PATH = ROOT / "data" / "cache" / "store_images.json"
PENDING_PATH = ROOT / "data" / "cache" / "stores_pending_update.json"
REPORT_PATH = ROOT / "data" / "cache" / "store_status_report.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
OG_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.I,
)

STATUS_OK = "ok"
STATUS_PENDING = "pending_update"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def unit_key(mall: str, floor: str, shop: str) -> str:
    return f"{norm(mall)}||{norm(floor)}||{norm(shop)}"


def name_key(mall: str, store_name: str) -> str:
    return f"{norm(mall)}||{norm(store_name).casefold()}"


# Readable brand / mall fragments for branch_id (fallback = md5).
_BRAND_SLUGS = {
    "必勝客": "pizzahut",
    "pizza hut": "pizzahut",
    "大家樂": "cafedecoral",
    "cafe de coral": "cafedecoral",
    "麥當勞": "mcdonalds",
    "mcdonald's": "mcdonalds",
    "mcdonalds": "mcdonalds",
    "星巴克": "starbucks",
    "starbucks": "starbucks",
    "屈臣氏": "watsons",
    "watsons": "watsons",
    "萬寧": "mannings",
    "mannings": "mannings",
    "優品360": "uplus360",
    "uniqlo": "uniqlo",
    "無印良品": "muji",
    "惠康": "wellcome",
    "百佳": "parknshop",
}


def slug(value: Any, *, max_len: int = 40) -> str:
    """ASCII-ish slug for branch ids (store + mall). Keeps CJK via brand map or hash."""
    text = norm(value)
    if not text:
        return ""
    mapped = _BRAND_SLUGS.get(text.casefold()) or _BRAND_SLUGS.get(text)
    if mapped:
        return mapped[:max_len]
    ascii_part = re.sub(r"[^a-z0-9]+", "", text.casefold())
    if len(ascii_part) >= 2:
        return ascii_part[:max_len]
    digest = __import__("hashlib").md5(text.encode("utf-8")).hexdigest()[:12]
    return (ascii_part + digest)[:max_len] or digest


def make_branch_id(mall: str, store_name: str, shop: str = "") -> str:
    """Branch-level id: brand alone is never enough (pizzahut_central ≠ pizzahut_shatin)."""
    parts = [slug(store_name), slug(mall)]
    shop_slug = slug(shop, max_len=16)
    if shop_slug:
        parts.append(shop_slug)
    bid = "_".join(p for p in parts if p)
    return bid[:96] or "store_unknown"


DEFAULT_LOCAL = "images/defaults/restaurant_default.png"


def branch_unique_image(branch_id: str) -> str:
    """Local category default — never stock / landscape placeholders."""
    del branch_id  # keying handled by store_key elsewhere
    return DEFAULT_LOCAL


def brand_fallback_image(store_name: str, source_url: str, *, unit: str = "", branch_id: str = "") -> str:
    """Deprecated path: always local restaurant default (no picsum)."""
    del store_name, source_url, unit, branch_id
    return DEFAULT_LOCAL


def iter_store_offers(malls_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten store offers with mall context (mutates offer dicts in place)."""
    out: list[dict[str, Any]] = []
    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict):
                    continue
                if offer.get("type") == "fallback":
                    continue
                store = norm(offer.get("store_name"))
                floor = norm(offer.get("floor"))
                shop = norm(offer.get("shop_number"))
                if not (mall_name and store and floor and shop):
                    continue
                offer["_mall_name"] = mall_name
                offer["_district"] = norm(district.get("district"))
                out.append(offer)
    return out


def extract_og_image(html: str, base_url: str) -> str:
    for pattern in (OG_RE, OG_RE_ALT):
        match = pattern.search(html or "")
        if not match:
            continue
        raw = (match.group(1) or "").strip()
        if not raw or raw.startswith("data:"):
            continue
        absolute = urljoin(base_url, raw)
        if absolute.startswith(("http://", "https://")):
            return absolute
    return ""


def fetch_image_url(source_url: str, *, timeout: float = 6.0) -> str:
    url = norm(source_url)
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=UA) as client:
            response = client.get(url)
            if response.status_code >= 400:
                return ""
            ctype = (response.headers.get("content-type") or "").lower()
            if "html" not in ctype and "text" not in ctype:
                return ""
            return extract_og_image(response.text, str(response.url))
    except Exception:  # noqa: BLE001
        return ""


def brand_fallback_image(store_name: str, source_url: str, *, unit: str = "") -> str:
    """Stable public placeholder keyed by mall unit so each shop is visually unique."""
    host = urlparse(norm(source_url)).netloc.lower().removeprefix("www.")
    seed = re.sub(
        r"[^a-z0-9]+",
        "-",
        f"{unit}-{store_name}-{host}".casefold(),
    ).strip("-") or "store"
    seed = seed[:80]
    return f"https://picsum.photos/seed/{seed}/320/240"


def compare_and_plan(
    offers: list[dict[str, Any]],
    cache_entries: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    """Return updated cache entries, pending rows, and counters."""
    by_unit_prev = {k: v for k, v in cache_entries.items() if isinstance(v, dict)}
    by_name_prev: dict[str, dict[str, Any]] = {}
    for entry in by_unit_prev.values():
        nk = name_key(str(entry.get("mall_name") or ""), str(entry.get("store_name") or ""))
        if nk:
            by_name_prev[nk] = entry

    updated: dict[str, Any] = {}
    pending: list[dict[str, Any]] = []
    stats = {
        "stores_seen": 0,
        "unchanged": 0,
        "name_changed": 0,
        "shop_relocated": 0,
        "new_units": 0,
        "needs_image": 0,
    }

    seen_units: set[str] = set()
    for offer in offers:
        mall = str(offer.get("_mall_name") or "")
        store = norm(offer.get("store_name"))
        floor = norm(offer.get("floor"))
        shop = norm(offer.get("shop_number"))
        uk = unit_key(mall, floor, shop)
        if uk in seen_units:
            continue
        seen_units.add(uk)
        stats["stores_seen"] += 1

        prev_unit = by_unit_prev.get(uk)
        prev_name = by_name_prev.get(name_key(mall, store))
        status = STATUS_OK
        reasons: list[str] = []
        previous_store_name = ""
        previous_shop = ""

        if prev_unit:
            previous_store_name = norm(prev_unit.get("store_name"))
            if previous_store_name and previous_store_name.casefold() != store.casefold():
                status = STATUS_PENDING
                reasons.append("store_name_changed")
                stats["name_changed"] += 1
        else:
            if prev_name:
                previous_shop = norm(prev_name.get("shop_number"))
                prev_floor = norm(prev_name.get("floor"))
                if previous_shop and (previous_shop != shop or prev_floor != floor):
                    status = STATUS_PENDING
                    reasons.append("shop_number_relocated")
                    stats["shop_relocated"] += 1
                    previous_store_name = store
                else:
                    stats["new_units"] += 1
                    status = STATUS_PENDING
                    reasons.append("new_unit")
            else:
                stats["new_units"] += 1
                status = STATUS_PENDING
                reasons.append("new_unit")

        image_url = ""
        if prev_unit and status == STATUS_OK:
            image_url = norm(
                prev_unit.get("store_image_url")
                or prev_unit.get("facade_image_url")
                or prev_unit.get("image_url")
            )
        if status == STATUS_PENDING:
            image_url = ""  # force refresh for relocated / new units

        if not image_url:
            stats["needs_image"] += 1

        if status == STATUS_OK and image_url:
            stats["unchanged"] += 1

        bid = make_branch_id(mall, store, shop)
        entry = {
            "mall_name": mall,
            "district": norm(offer.get("_district")),
            "store_name": store,
            "floor": floor,
            "shop_number": shop,
            "phone": norm(offer.get("phone")),
            "source_url": norm(offer.get("source_url")),
            "branch_id": bid,
            "image_url": image_url,
            "store_image_url": image_url,
            "facade_image_url": image_url,
            "status": status,
            "reasons": reasons,
            "previous_store_name": previous_store_name or None,
            "previous_shop_number": previous_shop or None,
            "checked_at": utc_now(),
        }
        updated[uk] = entry
        if status == STATUS_PENDING or not image_url:
            pending.append(dict(entry))

    return updated, pending, stats


def refresh_images(
    entries: dict[str, Any],
    *,
    max_fetch: int,
    workers: int,
    use_fallback: bool,
) -> int:
    targets = [
        (key, entry)
        for key, entry in entries.items()
        if isinstance(entry, dict)
        and (
            entry.get("status") == STATUS_PENDING
            or not norm(entry.get("image_url"))
        )
    ]
    targets = targets[: max(0, max_fetch)]
    if not targets:
        return 0

    fetched = 0

    def _one(item: tuple[str, dict[str, Any]]) -> tuple[str, str]:
        key, entry = item
        source = norm(entry.get("source_url"))
        bid = norm(entry.get("branch_id")) or make_branch_id(
            entry.get("mall_name"), entry.get("store_name"), entry.get("shop_number")
        )
        image = fetch_image_url(source) if source else ""
        # Brand-level CDN photos must never be reused across branches.
        if not image and use_fallback:
            image = brand_fallback_image(
                norm(entry.get("store_name")), source, unit=key, branch_id=bid
            )
        return key, image

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_one, item): item[0] for item in targets}
        for fut in as_completed(futures):
            key, image = fut.result()
            entry = entries.get(key)
            if not isinstance(entry, dict):
                continue
            if image:
                entry["image_url"] = image
                entry["store_image_url"] = image
                entry["facade_image_url"] = image
                fetched += 1
            if entry.get("status") == STATUS_PENDING and image:
                entry["image_refreshed_at"] = utc_now()
            entry["checked_at"] = utc_now()
    return fetched


def apply_to_malls(malls_payload: dict[str, Any], entries: dict[str, Any]) -> int:
    """Stamp branch_id + unique store_image_url onto every store card.

    Same brand across malls never shares one photo: URLs are owned by branch_id.
    """
    applied = 0
    url_owners: dict[str, str] = {}  # image_url -> branch_id

    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        bid = norm(entry.get("branch_id")) or make_branch_id(
            entry.get("mall_name"), entry.get("store_name"), entry.get("shop_number")
        )
        entry["branch_id"] = bid
        scraped = norm(
            entry.get("store_image_url")
            or entry.get("facade_image_url")
            or entry.get("image_url")
        )
        # Authoritative visual key is always branch_id (never brand name alone).
        image = branch_unique_image(bid)
        if scraped and scraped != image:
            entry["store_image_source"] = scraped
        url_owners[image] = bid
        entry["store_image_url"] = image
        entry["facade_image_url"] = image
        entry["image_url"] = image

    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict) or offer.get("type") == "fallback":
                    continue
                uk = unit_key(mall_name, offer.get("floor"), offer.get("shop_number"))
                entry = entries.get(uk)
                store = norm(offer.get("store_name"))
                shop = norm(offer.get("shop_number"))
                bid = (
                    norm(entry.get("branch_id"))
                    if isinstance(entry, dict)
                    else ""
                ) or make_branch_id(mall_name, store, shop)
                offer["branch_id"] = bid
                if isinstance(entry, dict):
                    image = norm(entry.get("store_image_url") or entry.get("facade_image_url"))
                else:
                    image = ""
                if not image:
                    image = branch_unique_image(bid)
                offer["store_image_url"] = image
                offer["facade_image_url"] = image
                offer["image_url"] = image
                if isinstance(entry, dict):
                    status = norm(entry.get("status")) or STATUS_OK
                    offer["relocation_status"] = status
                    if status == STATUS_PENDING:
                        offer["relocation_reasons"] = list(entry.get("reasons") or [])
                    else:
                        offer.pop("relocation_reasons", None)
                applied += 1
                offer.pop("_mall_name", None)
                offer.pop("_district", None)
    return applied


def attach_images_from_cache(malls_payload: dict[str, Any], cache_path: Path = CACHE_PATH) -> int:
    """Helper for build_spa_malls: stamp image_url from cache without network I/O."""
    payload = load_json(cache_path, {})
    entries = payload.get("entries") if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        return 0
    return apply_to_malls(malls_payload, entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check store relocation + refresh storefront images")
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    parser.add_argument("--max-fetch", type=int, default=120, help="Max remote og:image fetches per run")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--no-fallback-image", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    malls_payload = load_json(args.malls, {})
    if not isinstance(malls_payload, dict) or not malls_payload.get("districts"):
        print(f"[store_status] missing or empty malls feed: {args.malls}")
        return 1

    cache_payload = load_json(args.cache, {"entries": {}})
    prev_entries = cache_payload.get("entries") if isinstance(cache_payload, dict) else {}
    if not isinstance(prev_entries, dict):
        prev_entries = {}

    offers = iter_store_offers(malls_payload)
    entries, pending, stats = compare_and_plan(offers, prev_entries)
    fetched = refresh_images(
        entries,
        max_fetch=args.max_fetch,
        workers=args.workers,
        use_fallback=not args.no_fallback_image,
    )
    applied = 0 if args.dry_run else apply_to_malls(malls_payload, entries)

    # Strip ephemeral keys left on offers when dry-run
    for offer in offers:
        offer.pop("_mall_name", None)
        offer.pop("_district", None)

    report = {
        "checked_at": utc_now(),
        "stats": {**stats, "images_fetched": fetched, "cards_updated": applied, "pending": len(pending)},
        "pending_sample": pending[:40],
    }

    if not args.dry_run:
        write_json(args.cache, {"updated_at": utc_now(), "entries": entries})
        write_json(
            PENDING_PATH,
            {
                "updated_at": utc_now(),
                "count": len(pending),
                "stores": pending,
                "note": "pending_update stores should be covered by the next daily scrape/expand cycle",
            },
        )
        write_json(REPORT_PATH, report)
        write_json(args.malls, malls_payload)

    print(
        "[store_status] "
        f"seen={stats['stores_seen']} unchanged={stats['unchanged']} "
        f"name_changed={stats['name_changed']} relocated={stats['shop_relocated']} "
        f"new={stats['new_units']} pending={len(pending)} "
        f"images_fetched={fetched} cards_updated={applied}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
