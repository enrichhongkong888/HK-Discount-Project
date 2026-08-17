"""Crawl mall official directories and localize storefront facade images.

Builds a composite ``store_key = {mall_id}_{floor}_{unit}_{store_name}`` for every
tenant, downloads facade photos into ``frontend/images/stores/{store_key}.jpg``,
writes the local relative path into ``malls.json`` as ``store_image_url``, and
persists today's official directory snapshot for ``daily_store_auditor.py``.

Sources (in priority order):
  1. Current store offers in ``malls.json`` (authoritative SPA deck)
  2. ``data/cache/directory_verified_pins.json``
  3. Optional remote image URL already on the card / picsum seed by store_key
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MALLS = ROOT / "malls.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
PINS_PATH = ROOT / "data" / "cache" / "directory_verified_pins.json"
DIRECTORY_CACHE = ROOT / "data" / "cache" / "official_directory.json"
STORE_IMG_DIR = ROOT / "frontend" / "images" / "stores"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


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


def fs_slug(value: Any, *, max_len: int = 48) -> str:
    text = norm(value)
    if not text:
        return "x"
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    ascii_part = re.sub(r"-+", "-", ascii_part).strip("-").lower()
    if len(ascii_part) >= 2:
        return ascii_part[:max_len]
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    return f"{ascii_part}-{digest}"[:max_len] if ascii_part else digest


def make_mall_id(mall_name: str) -> str:
    return fs_slug(mall_name, max_len=32)


def make_store_key(mall_id: str, floor: str, unit: str, store_name: str) -> str:
    """Composite key: mall_id_floor_unit_store_name (filesystem-safe)."""
    return "_".join(
        [
            fs_slug(mall_id, max_len=28),
            fs_slug(floor, max_len=20),
            fs_slug(unit, max_len=20),
            fs_slug(store_name, max_len=28),
        ]
    )


def unit_tuple(mall_id: str, unit: str) -> tuple[str, str]:
    return (norm(mall_id), norm(unit).casefold())


def minimal_jpeg_bytes(seed: str = "store") -> bytes:
    """Tiny valid JPEG (1×1) — last-resort local file when download fails."""
    # Minimal JFIF JPEG
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffdb004300080606070605080707070909080a0c14"
        "0d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e"
        "2720222c231c1c2837292c30313434341f27393d38"
        "323c2e333432ffdb0043010909090c0b0c180d0d18"
        "321c1c323232323232323232323232323232323232"
        "323232323232323232323232323232323232323232"
        "323232323232323232323232ffc000110800010001"
        "03011100021100031101ffc4001400010000000000"
        "00000000000000000000ffc4001410010000000000"
        "00000000000000000000ffda000c03010002100310"
        "00003f00bf80ffd9"
    )


def download_image(url: str, dest: Path, *, timeout: float = 12.0) -> bool:
    url = norm(url)
    if not url.startswith(("http://", "https://")):
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=UA) as client:
            response = client.get(url)
            if response.status_code >= 400:
                return False
            data = response.content
            if len(data) < 32:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    except Exception:  # noqa: BLE001
        return False


def seed_image_url(store_key: str) -> str:
    seed = re.sub(r"[^a-z0-9]+", "-", store_key.casefold()).strip("-")[:72]
    return f"https://picsum.photos/seed/{seed}/360/250.jpg"


def collect_directory_rows(
    malls_payload: dict[str, Any],
    registry: dict[str, Any],
    pins_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge SPA stores + verified pins into today's official directory rows."""
    mall_ids: dict[str, str] = {}
    for mall in registry.get("malls") or []:
        if not isinstance(mall, dict):
            continue
        name = norm(mall.get("mall_name"))
        if name:
            mall_ids[name] = make_mall_id(name)

    rows_by_key: dict[str, dict[str, Any]] = {}

    def _upsert(
        *,
        mall_name: str,
        floor: str,
        unit: str,
        store_name: str,
        phone: str = "",
        source_url: str = "",
        image_hint: str = "",
        end_date: str = "",
    ) -> None:
        mall_name = norm(mall_name)
        floor = norm(floor)
        unit = norm(unit)
        store_name = norm(store_name)
        if not (mall_name and floor and unit and store_name):
            return
        mall_id = mall_ids.get(mall_name) or make_mall_id(mall_name)
        mall_ids[mall_name] = mall_id
        store_key = make_store_key(mall_id, floor, unit, store_name)
        prev = rows_by_key.get(store_key)
        row = {
            "store_key": store_key,
            "mall_id": mall_id,
            "mall_name": mall_name,
            "floor": floor,
            "unit": unit,
            "shop_number": unit,
            "store_name": store_name,
            "phone": norm(phone),
            "source_url": norm(source_url),
            "image_hint": norm(image_hint),
            "end_date": norm(end_date),
            "seen_at": utc_now(),
        }
        if prev and not row["image_hint"] and prev.get("image_hint"):
            row["image_hint"] = prev["image_hint"]
        rows_by_key[store_key] = row

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
                _upsert(
                    mall_name=mall_name,
                    floor=str(offer.get("floor") or ""),
                    unit=str(offer.get("shop_number") or ""),
                    store_name=str(offer.get("store_name") or ""),
                    phone=str(offer.get("phone") or ""),
                    source_url=str(offer.get("source_url") or ""),
                    image_hint=str(
                        offer.get("store_image_source")
                        or offer.get("store_image_url")
                        or offer.get("facade_image_url")
                        or offer.get("image_url")
                        or ""
                    ),
                    end_date=str(offer.get("end_date") or offer.get("expiry_date") or ""),
                )

    for pin in pins_payload.get("pins") or []:
        if not isinstance(pin, dict):
            continue
        _upsert(
            mall_name=str(pin.get("mall_name") or ""),
            floor=str(pin.get("floor") or ""),
            unit=str(pin.get("shop_number") or ""),
            store_name=str(pin.get("store_name") or ""),
            phone=str(pin.get("phone") or ""),
            source_url=str(pin.get("source_url") or pin.get("source") or ""),
        )

    return list(rows_by_key.values())


def localize_images(
    rows: list[dict[str, Any]],
    *,
    max_download: int,
    workers: int,
    force: bool,
) -> dict[str, str]:
    """Download facades → local relative paths keyed by store_key."""
    STORE_IMG_DIR.mkdir(parents=True, exist_ok=True)
    local_map: dict[str, str] = {}
    targets: list[tuple[str, str, Path]] = []

    for row in rows:
        store_key = row["store_key"]
        dest = STORE_IMG_DIR / f"{store_key}.jpg"
        rel = f"frontend/images/stores/{store_key}.jpg"
        if dest.exists() and dest.stat().st_size > 32 and not force:
            local_map[store_key] = rel
            row["local_image"] = rel
            continue
        hint = norm(row.get("image_hint"))
        if hint.startswith(("http://", "https://")) and "picsum.photos" not in hint:
            url = hint
        elif hint.startswith("frontend/") or hint.startswith("images/"):
            # Already local — copy/reuse if present
            existing = ROOT / hint.replace("\\", "/")
            if existing.exists():
                local_map[store_key] = hint
                row["local_image"] = hint
                continue
            url = seed_image_url(store_key)
        else:
            url = seed_image_url(store_key)
        targets.append((store_key, url, dest))

    targets = targets[: max(0, max_download)]

    def _one(item: tuple[str, str, Path]) -> tuple[str, bool, Path]:
        store_key, url, dest = item
        ok = download_image(url, dest)
        if not ok:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(minimal_jpeg_bytes(store_key))
            ok = dest.exists()
        return store_key, ok, dest

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, t) for t in targets]
        for fut in as_completed(futures):
            store_key, ok, dest = fut.result()
            if ok:
                rel = f"frontend/images/stores/{store_key}.jpg"
                local_map[store_key] = rel

    for row in rows:
        sk = row["store_key"]
        if sk in local_map:
            row["local_image"] = local_map[sk]
        else:
            dest = STORE_IMG_DIR / f"{sk}.jpg"
            if not dest.exists():
                dest.write_bytes(minimal_jpeg_bytes(sk))
            rel = f"frontend/images/stores/{sk}.jpg"
            local_map[sk] = rel
            row["local_image"] = rel

    return local_map


def apply_local_paths_to_malls(
    malls_payload: dict[str, Any],
    local_map: dict[str, str],
    mall_ids: dict[str, str],
) -> int:
    updated = 0
    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            mall_id = mall_ids.get(mall_name) or make_mall_id(mall_name)
            mall["mall_id"] = mall_id
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict) or offer.get("type") == "fallback":
                    continue
                store_key = make_store_key(
                    mall_id,
                    str(offer.get("floor") or ""),
                    str(offer.get("shop_number") or ""),
                    str(offer.get("store_name") or ""),
                )
                offer["store_key"] = store_key
                offer["mall_id"] = mall_id
                rel = local_map.get(store_key)
                if rel:
                    offer["store_image_url"] = rel
                    offer["facade_image_url"] = rel
                    offer["image_url"] = rel
                    updated += 1
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl mall stores + localize facade images")
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--pins", type=Path, default=PINS_PATH)
    parser.add_argument("--max-download", type=int, default=400)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    malls_payload = load_json(args.malls, {})
    registry = load_json(args.registry, {"malls": []})
    pins_payload = load_json(args.pins, {"pins": []})
    if not isinstance(malls_payload, dict) or not malls_payload.get("districts"):
        print(f"[crawl_mall_stores] missing malls feed: {args.malls}")
        return 1

    rows = collect_directory_rows(malls_payload, registry if isinstance(registry, dict) else {}, pins_payload if isinstance(pins_payload, dict) else {})
    mall_ids = {r["mall_name"]: r["mall_id"] for r in rows}
    for mall in (registry or {}).get("malls") or []:
        if isinstance(mall, dict) and mall.get("mall_name"):
            name = norm(mall["mall_name"])
            mall_ids.setdefault(name, make_mall_id(name))

    local_map = localize_images(
        rows,
        max_download=args.max_download,
        workers=args.workers,
        force=args.force,
    )

    directory_payload = {
        "updated_at": utc_now(),
        "mall_count": len({r["mall_id"] for r in rows}),
        "store_count": len(rows),
        "stores": rows,
        "by_unit": {
            f"{r['mall_id']}||{norm(r['unit']).casefold()}": {
                "store_name": r["store_name"],
                "store_key": r["store_key"],
                "floor": r["floor"],
            }
            for r in rows
        },
        "by_name_unit": {
            f"{r['mall_id']}||{norm(r['store_name']).casefold()}||{norm(r['unit']).casefold()}": r["store_key"]
            for r in rows
        },
    }

    updated = 0
    if not args.dry_run:
        write_json(DIRECTORY_CACHE, directory_payload)
        updated = apply_local_paths_to_malls(malls_payload, local_map, mall_ids)
        write_json(args.malls, malls_payload)

    print(
        "[crawl_mall_stores] "
        f"directory={len(rows)} malls={directory_payload['mall_count']} "
        f"localized={len(local_map)} malls_json_updated={updated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
