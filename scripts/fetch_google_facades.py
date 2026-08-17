# -*- coding: utf-8 -*-
"""Fetch real storefront photos via Google Places API (legacy Text Search + Photos).

Pipeline layer (after ``crawl_mall_directories.py``)::

  1. Mall / OpenRice / YOHO / Link directory photos   (most accurate)
  2. Google Places facade photos                       (this script)
  3. Local chain brand placards                        (``chain_brand_images``)
  4. Category defaults                                 (restaurant / retail / store)

Candidates are offers whose current image is still a chain brand card, a category
default, or missing. Directory / already-Google photos are left untouched.

Requires ``GOOGLE_MAPS_API_KEY`` in the environment or project ``.env``.
If the key is missing, the script exits 0 and leaves brand / default images as-is.

Example (single mall)::

  # .env
  GOOGLE_MAPS_API_KEY=AIza...

  python scripts/fetch_google_facades.py --mall 太古城中心 --limit 20
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chain_brand_images import (  # noqa: E402
    apply_brand_to_store,
    default_image_for_vertical,
    ensure_all_brand_images,
    ensure_category_defaults,
    resolve_chain_brand,
)

DEFAULT_MALLS = ROOT / "malls.json"
STORE_IMG_DIR = ROOT / "frontend" / "images" / "stores"
CACHE_PATH = ROOT / "data" / "cache" / "google_facades_cache.json"
ENV_PATH = ROOT / ".env"

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
PHOTO_URL = "https://maps.googleapis.com/maps/api/place/photo"

# Keep directory / prior Google hits; refresh brand cards + defaults only.
PROTECTED_SOURCES = frozenset(
    {
        "directory_crawl",
        "openrice",
        "yoho_cms",
        "linkreit",
        "yoho",
        "link",
        "swire_directory",
        "google_places",
    }
)

# Frontend card is 180×125 ≈ 1.44; encode slightly larger for retina.
OUT_WIDTH = 720
OUT_HEIGHT = 500
JPEG_QUALITY = 82
MIN_LANDSCAPE_RATIO = 1.05  # width / height
MAXWIDTH_DOWNLOAD = 1200


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any = None) -> Any:
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


def get_api_key() -> str:
    load_dotenv(ENV_PATH, override=False)
    import os

    return norm(os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY"))


def image_url_of(offer: dict[str, Any]) -> str:
    return norm(
        offer.get("store_image_url")
        or offer.get("facade_image_url")
        or offer.get("image_url")
    )


def needs_google_facade(offer: dict[str, Any], *, force: bool = False) -> bool:
    if offer.get("type") == "fallback":
        return False
    if not norm(offer.get("store_name")):
        return False
    source = norm(offer.get("image_source"))
    if not force and source in PROTECTED_SOURCES:
        return False
    url = image_url_of(offer)
    if not url:
        return True
    if "images/defaults/" in url:
        return True
    if "frontend/images/brands/" in url:
        return True
    if source == "chain_brand":
        return True
    # Local store jpg that originated as a brand placard still qualifies when
    # image_source says chain_brand (handled above). Plain missing source +
    # defaults path already covered.
    if force:
        return True
    return False


def search_query(mall_name: str, store_name: str) -> str:
    return f"{norm(mall_name)} {norm(store_name)} 香港"


def iter_candidate_offers(
    malls_payload: dict[str, Any],
    *,
    mall_filter: str | None,
    force: bool,
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """Return list of (mall, offer, mall_name)."""
    want = norm(mall_filter).casefold() if mall_filter else ""
    out: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            if want and want not in mall_name.casefold():
                continue
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict):
                    continue
                if needs_google_facade(offer, force=force):
                    out.append((mall, offer, mall_name))
    return out


def text_search(client: httpx.Client, api_key: str, query: str) -> dict[str, Any] | None:
    params = {
        "query": query,
        "key": api_key,
        "language": "zh-HK",
        "region": "hk",
    }
    response = client.get(f"{TEXT_SEARCH_URL}?{urlencode(params)}", timeout=25.0)
    payload = response.json()
    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        print(f"[google] textsearch status={status} query={query!r} error={payload.get('error_message')}")
        return None
    results = payload.get("results") or []
    if not results:
        return None
    return results[0] if isinstance(results[0], dict) else None


def place_photos(client: httpx.Client, api_key: str, place_id: str) -> list[dict[str, Any]]:
    params = {
        "place_id": place_id,
        "fields": "place_id,name,photos,formatted_address",
        "key": api_key,
        "language": "zh-HK",
    }
    response = client.get(f"{DETAILS_URL}?{urlencode(params)}", timeout=25.0)
    payload = response.json()
    if payload.get("status") != "OK":
        return []
    result = payload.get("result") or {}
    photos = result.get("photos") or []
    return [p for p in photos if isinstance(p, dict) and p.get("photo_reference")]


def rank_photos(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer landscape (facade / interior wide shots) over portrait product crops."""

    def score(photo: dict[str, Any]) -> tuple[int, float, int]:
        w = int(photo.get("width") or 0)
        h = int(photo.get("height") or 0)
        ratio = (w / h) if h else 0.0
        landscape = 1 if ratio >= MIN_LANDSCAPE_RATIO else 0
        area = w * h
        return (landscape, ratio, area)

    return sorted(photos, key=score, reverse=True)


def download_photo_bytes(client: httpx.Client, api_key: str, photo_reference: str) -> bytes | None:
    params = {
        "photo_reference": photo_reference,
        "maxwidth": str(MAXWIDTH_DOWNLOAD),
        "key": api_key,
    }
    response = client.get(
        f"{PHOTO_URL}?{urlencode(params)}",
        timeout=40.0,
        follow_redirects=True,
    )
    if response.status_code >= 400:
        return None
    data = response.content
    if len(data) < 1500:
        return None
    ctype = (response.headers.get("content-type") or "").lower()
    if "text/html" in ctype or data[:64].lstrip().lower().startswith((b"<!doctype", b"<html")):
        return None
    return data


def crop_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    """Center-crop to target aspect, then resize (cover semantics)."""
    src = img.convert("RGB")
    sw, sh = src.size
    if sw < 2 or sh < 2:
        raise ValueError("image too small")
    target_ratio = width / height
    src_ratio = sw / sh
    if src_ratio > target_ratio:
        # too wide → crop sides
        new_w = int(sh * target_ratio)
        left = (sw - new_w) // 2
        src = src.crop((left, 0, left + new_w, sh))
    elif src_ratio < target_ratio:
        # too tall → crop top/bottom
        new_h = int(sw / target_ratio)
        top = (sh - new_h) // 2
        src = src.crop((0, top, sw, top + new_h))
    return src.resize((width, height), Image.Resampling.LANCZOS)


def save_facade_jpeg(raw: bytes, dest: Path) -> bool:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            w, h = img.size
            # Soft-reject obvious portrait product shots when that is all we have
            # after ranking — still accept if ratio is only slightly portrait.
            if h > w * 1.35:
                return False
            out = crop_cover(img, OUT_WIDTH, OUT_HEIGHT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        return dest.exists() and dest.stat().st_size > 800
    except Exception as exc:  # noqa: BLE001
        print(f"[google] encode fail {dest.name}: {exc}")
        return False


def stamp_offer(offer: dict[str, Any], store_key: str, *, place_id: str, query: str) -> None:
    rel = f"frontend/images/stores/{store_key}.jpg"
    offer["store_image_url"] = rel
    offer["facade_image_url"] = rel
    offer["image_url"] = rel
    offer["image_source"] = "google_places"
    offer["google_place_id"] = place_id
    offer["google_query"] = query
    offer.pop("brand_id", None)


def apply_brand_or_default(offer: dict[str, Any], store_key: str) -> str:
    dest = STORE_IMG_DIR / f"{store_key}.jpg"
    brand_id = resolve_chain_brand(offer.get("store_name"))
    if brand_id and apply_brand_to_store(brand_id, dest):
        rel = f"frontend/images/stores/{store_key}.jpg"
        offer["store_image_url"] = rel
        offer["facade_image_url"] = rel
        offer["image_url"] = rel
        offer["image_source"] = "chain_brand"
        offer["brand_id"] = brand_id
        return "chain_brand"
    fallback = default_image_for_vertical(offer.get("vertical_category"))
    offer["store_image_url"] = fallback
    offer["facade_image_url"] = fallback
    offer["image_url"] = fallback
    offer.pop("image_source", None)
    offer.pop("brand_id", None)
    return "default"


def ensure_store_key(mall: dict[str, Any], offer: dict[str, Any], mall_name: str) -> str:
    existing = norm(offer.get("store_key"))
    if existing:
        return existing
    # Mirror crawl_mall_directories key rules without importing heavy module cycles.
    from crawl_mall_directories import make_mall_id, make_store_key

    mall_id = norm(mall.get("mall_id")) or make_mall_id(mall_name)
    mall["mall_id"] = mall_id
    key = make_store_key(mall_id, offer.get("shop_number"), offer.get("phone"))
    offer["store_key"] = key
    offer["mall_id"] = mall_id
    return key


def fetch_one(
    client: httpx.Client,
    api_key: str,
    *,
    mall_name: str,
    offer: dict[str, Any],
    store_key: str,
    cache: dict[str, Any],
    sleep_s: float,
) -> bool:
    query = search_query(mall_name, str(offer.get("store_name") or ""))
    cache_key = query.casefold()
    cached = cache.get(cache_key) if isinstance(cache.get(cache_key), dict) else None

    place_id = norm((cached or {}).get("place_id"))
    if not place_id:
        hit = text_search(client, api_key, query)
        time.sleep(sleep_s)
        if not hit:
            cache[cache_key] = {"place_id": "", "status": "zero", "updated_at": utc_now()}
            return False
        place_id = norm(hit.get("place_id"))
        cache[cache_key] = {
            "place_id": place_id,
            "name": hit.get("name"),
            "status": "ok",
            "updated_at": utc_now(),
        }
        # Prefer photos already on the search result when present
        seed_photos = [p for p in (hit.get("photos") or []) if isinstance(p, dict)]
    else:
        seed_photos = []

    if not place_id:
        return False

    photos = place_photos(client, api_key, place_id)
    time.sleep(sleep_s)
    if seed_photos:
        # Merge search photos first (often the hero facade), then details.
        merged: dict[str, dict[str, Any]] = {}
        for photo in seed_photos + photos:
            ref = norm(photo.get("photo_reference"))
            if ref:
                merged[ref] = photo
        photos = list(merged.values())

    if not photos:
        return False

    dest = STORE_IMG_DIR / f"{store_key}.jpg"
    for photo in rank_photos(photos):
        ref = norm(photo.get("photo_reference"))
        if not ref:
            continue
        raw = download_photo_bytes(client, api_key, ref)
        time.sleep(sleep_s)
        if not raw:
            continue
        # Skip strongly portrait frames early when metadata says so
        w = int(photo.get("width") or 0)
        h = int(photo.get("height") or 0)
        if w and h and h > w * 1.35:
            continue
        if save_facade_jpeg(raw, dest):
            stamp_offer(offer, store_key, place_id=place_id, query=query)
            return True

    # Last resort: try any remaining photo even if portrait metadata
    for photo in rank_photos(photos):
        ref = norm(photo.get("photo_reference"))
        if not ref:
            continue
        raw = download_photo_bytes(client, api_key, ref)
        time.sleep(sleep_s)
        if raw and save_facade_jpeg(raw, dest):
            stamp_offer(offer, store_key, place_id=place_id, query=query)
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Google Places facade photos for mall stores")
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument("--mall", type=str, default="", help="Only process malls whose name contains this string")
    parser.add_argument("--limit", type=int, default=0, help="Max candidates to fetch (0 = all)")
    parser.add_argument("--sleep", type=float, default=0.35, help="Delay between Places API calls")
    parser.add_argument("--force", action="store_true", help="Re-fetch even for protected image_source")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--apply-brands",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After Google pass, apply chain brand placards to remaining defaults (layer 3)",
    )
    args = parser.parse_args(argv)

    api_key = get_api_key()
    malls_payload = load_json(args.malls, {})
    if not isinstance(malls_payload, dict) or not malls_payload.get("districts"):
        print(f"[google] missing malls: {args.malls}")
        return 1

    ensure_category_defaults()
    ensure_all_brand_images()
    STORE_IMG_DIR.mkdir(parents=True, exist_ok=True)

    candidates = iter_candidate_offers(
        malls_payload,
        mall_filter=args.mall or None,
        force=args.force,
    )
    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]

    print(
        f"[google] candidates={len(candidates)} mall_filter={args.mall or '*'} "
        f"dry_run={args.dry_run}"
    )
    if not candidates:
        return 0

    if not api_key:
        print(
            "[google] GOOGLE_MAPS_API_KEY not set — skip Places facade fetch; "
            "keeping chain brand / category defaults."
        )
        if args.dry_run:
            for _mall, offer, mall_name in candidates[:20]:
                q = search_query(mall_name, str(offer.get("store_name") or ""))
                print(f"[google] dry-run(no-key) {mall_name} | {offer.get('store_name')} | {q}")
        return 0

    cache = load_json(CACHE_PATH, {})
    if not isinstance(cache, dict):
        cache = {}

    fetched = 0
    failed = 0

    with httpx.Client(
        follow_redirects=True,
        timeout=40.0,
        headers={"User-Agent": "HK-Discount-Project/google-facades"},
    ) as client:
        for mall, offer, mall_name in candidates:
            store_key = ensure_store_key(mall, offer, mall_name)
            store_name = norm(offer.get("store_name"))
            query = search_query(mall_name, store_name)
            if args.dry_run:
                print(f"[google] dry-run {mall_name} | {store_name} | {query}")
                continue
            try:
                ok = fetch_one(
                    client,
                    api_key,
                    mall_name=mall_name,
                    offer=offer,
                    store_key=store_key,
                    cache=cache,
                    sleep_s=max(0.05, float(args.sleep)),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[google] error {mall_name} {store_name}: {exc}")
                ok = False
            if ok:
                fetched += 1
                print(f"[google] OK  {mall_name} | {store_name} -> {store_key}.jpg")
            else:
                failed += 1
                print(f"[google] miss {mall_name} | {store_name}")

    brand_filled = 0
    defaulted = 0
    if args.apply_brands and not args.dry_run:
        # Layer 3-4: anything still not a real facade gets brand card or category default.
        for district in malls_payload.get('districts') or []:
            for mall in (district or {}).get('malls') or []:
                if not isinstance(mall, dict):
                    continue
                mall_name = norm(mall.get('mall_name'))
                if args.mall and norm(args.mall).casefold() not in mall_name.casefold():
                    continue
                for offer in mall.get('store_offers') or []:
                    if not isinstance(offer, dict) or offer.get('type') == 'fallback':
                        continue
                    source = norm(offer.get('image_source'))
                    if source in PROTECTED_SOURCES:
                        continue
                    url = image_url_of(offer)
                    still_placeholder = (
                        not url
                        or 'images/defaults/' in url
                        or 'frontend/images/brands/' in url
                        or source in {'', 'chain_brand'}
                    )
                    if not still_placeholder:
                        continue
                    store_key = ensure_store_key(mall, offer, mall_name)
                    layer = apply_brand_or_default(offer, store_key)
                    if layer == 'chain_brand':
                        brand_filled += 1
                    else:
                        defaulted += 1

    if not args.dry_run:
        write_json(CACHE_PATH, cache)
        write_json(args.malls, malls_payload)

    print(
        "[google] "
        f"fetched={fetched} missed={failed} "
        f"brand_layer={brand_filled} default_layer={defaulted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
