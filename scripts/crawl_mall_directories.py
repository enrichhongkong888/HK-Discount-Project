"""Crawl mall directories for REAL storefront photos and localize them.

Composite key (branch-unique)::
    store_key = f"{mall_id}_{unit}_{phone}"

Image layers (this script owns layer 1 + interim 3/4; Google fills layer 2 next)::
  1. OpenRice / YOHO / Link / Swire directory facades (most accurate)
  2. ``fetch_google_facades.py`` — Google Places real photos
  3. Chain brand placards (Watsons / MUJI / …) via ``chain_brand_images``
  4. Category defaults under ``images/defaults/``

Never picsum / stock landscapes. Downloads to ``frontend/images/stores/{store_key}.jpg``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

DEFAULT_MALLS = ROOT / "malls.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
DIRECTORY_CACHE = ROOT / "data" / "cache" / "official_directory.json"
STORE_IMG_DIR = ROOT / "frontend" / "images" / "stores"
DEFAULT_LOCAL = "images/defaults/restaurant_default.png"
BRAND_IMG_DIR = ROOT / "frontend" / "images" / "brands"

from chain_brand_images import (  # noqa: E402
    apply_brand_to_store,
    default_image_for_vertical,
    ensure_all_brand_images,
    ensure_category_defaults,
    resolve_chain_brand,
)


LINK_BASE = "https://www.linkhk.com"
LINK_API = f"{LINK_BASE}/linkweb/api"
YOHO_CMS = "https://cms.yohomall.hk"
OPENRICE_SEARCH = "https://www.openrice.com/api/v2/search"

LINK_CENTRE_IDS: dict[str, int] = {
    "樂富廣場": 7,
    "赤柱廣場": 28,
    "T Town": 135,
    "黃大仙中心": 164,
}

# Swire public shopping pages (HTML cards; image when present)
SWIRE_SHOPPING_PAGES: dict[str, str] = {
    "太古廣場": "https://www.pacificplace.com.hk/zh-hk/shopping",
    "太古城中心": "https://www.cityplaza.com/zh-hk/shop",
    "又一城": "https://www.festivalwalk.com.hk/tc/shopping",
}

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

JSON_HEADERS = {
    **UA,
    "Accept": "application/json, text/plain, */*",
}

_SHOP_RE = re.compile(r"([A-Za-z]?\d+[A-Za-z0-9\-/&]*)\s*號舖", re.I)
_FLOOR_RE = re.compile(
    r"((?:[A-Za-z]區)?(?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:/F|樓|層)|地下|地庫|平台)",
    re.I,
)


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


def phone_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def fs_slug(value: Any, *, max_len: int = 40) -> str:
    text = norm(value)
    if not text:
        return "x"
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    ascii_part = re.sub(r"-+", "-", ascii_part).strip("-").lower()
    if len(ascii_part) >= 2:
        return ascii_part[:max_len]
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def make_mall_id(mall_name: str) -> str:
    return fs_slug(mall_name, max_len=32)


def make_store_key(mall_id: str, unit: str, phone: str) -> str:
    """Composite key: mall_id_unit_phone (branch-unique)."""
    unit_s = fs_slug(unit or "na", max_len=24)
    phone_s = phone_digits(phone) or "0"
    return f"{fs_slug(mall_id, max_len=28)}_{unit_s}_{phone_s}"


def is_forbidden_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        bad in u
        for bad in (
            "picsum.photos",
            "placeholder",
            "lorempixel",
            "unsplash.com/random",
            "via.placeholder",
        )
    )


def is_real_remote_image(url: str) -> bool:
    u = norm(url)
    if not u.startswith(("http://", "https://")):
        return False
    if is_forbidden_image_url(u):
        return False
    return True


def absolute_url(base: str, path: str) -> str:
    path = norm(path)
    if path.startswith("//"):
        return "https:" + path
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(base if base.endswith("/") else base + "/", path.lstrip("/"))


def download_image(url: str, dest: Path, *, timeout: float = 15.0) -> bool:
    if not is_real_remote_image(url):
        return False
    try:
        headers = {**UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            if response.status_code >= 400:
                return False
            ctype = (response.headers.get("content-type") or "").lower()
            data = response.content
            if len(data) < 800:
                return False
            # Reject obvious HTML error pages
            if "text/html" in ctype or data[:64].lstrip().lower().startswith((b"<!doctype", b"<html")):
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    except Exception:  # noqa: BLE001
        return False


def parse_floor_shop(text: str) -> tuple[str, str]:
    loc = norm(text)
    shop = ""
    floor = ""
    m = _SHOP_RE.search(loc)
    if m:
        shop = m.group(1).strip()
    f = _FLOOR_RE.search(loc)
    if f:
        floor = f.group(1).strip()
    return floor, shop


# ---------------------------------------------------------------------------
# Directory crawlers
# ---------------------------------------------------------------------------


def crawl_yoho_shops(client: httpx.Client) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 25):
        query = urlencode(
            {
                "pagination[page]": page,
                "pagination[pageSize]": 100,
                "populate[display_image]": "*",
                "populate[mall_shop_number]": "*",
            }
        )
        try:
            response = client.get(f"{YOHO_CMS}/api/shops?{query}", headers=JSON_HEADERS, timeout=30)
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[crawl] yoho page {page} fail: {exc}")
            break
        data = payload.get("data") if isinstance(payload, dict) else None
        if not data:
            break
        for item in data:
            attrs = item.get("attributes") if isinstance(item, dict) else None
            if not isinstance(attrs, dict):
                continue
            name = norm(attrs.get("display_name"))
            phone = norm(attrs.get("phone"))
            loc_node = ((attrs.get("mall_shop_number") or {}).get("data") or {})
            loc = loc_node.get("attributes") if isinstance(loc_node, dict) else {}
            if not isinstance(loc, dict):
                loc = {}
            unit = norm(loc.get("shop_number") or attrs.get("shop_number"))
            floor = norm(loc.get("floor") or attrs.get("floor"))
            mall_code = norm(loc.get("mall"))
            if mall_code:
                label = {
                    "mall-1": "YOHO MALL I",
                    "mall-2": "YOHO MALL II",
                    "mall-mix": "YOHO MIX",
                }.get(mall_code, mall_code)
                floor = f"{label} {floor}".strip()
            img_data = (attrs.get("display_image") or {}).get("data")
            image_url = ""
            if isinstance(img_data, list) and img_data:
                img_attrs = (img_data[0] or {}).get("attributes") or {}
                image_url = absolute_url(YOHO_CMS, str(img_attrs.get("url") or ""))
            elif isinstance(img_data, dict):
                img_attrs = img_data.get("attributes") or {}
                image_url = absolute_url(YOHO_CMS, str(img_attrs.get("url") or ""))
            if not (name and unit and phone and is_real_remote_image(image_url)):
                continue
            rows.append(
                {
                    "source": "yoho_cms",
                    "mall_name": "YOHO MALL 形點",
                    "store_name": name,
                    "floor": floor or "YOHO",
                    "unit": unit,
                    "phone": phone,
                    "image_url": image_url,
                }
            )
        meta = (payload.get("meta") or {}).get("pagination") or {}
        if page >= int(meta.get("pageCount") or page):
            break
        time.sleep(0.15)
    print(f"[crawl] yoho real photos={len(rows)}")
    return rows


def crawl_link_centre(client: httpx.Client, mall_name: str, centre_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        response = client.get(
            f"{LINK_API}/shopCentre/{centre_id}",
            headers={**JSON_HEADERS, "Referer": f"{LINK_BASE}/tc/", "Origin": LINK_BASE},
            timeout=25,
        )
        data = (response.json() or {}).get("data") or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[crawl] link {mall_name} fail: {exc}")
        return rows

    featured: list[dict[str, Any]] = []
    for bucket, key in (("shop", "shopList"), ("dine", "dineList")):
        block = data.get(bucket) or {}
        featured.extend([x for x in (block.get(key) or []) if isinstance(x, dict)])

    for item in featured:
        shop_id = item.get("shopId")
        name = norm(item.get("shopNameTc") or item.get("shopNameEn"))
        photo = absolute_url(LINK_BASE, str(item.get("shopPhotoPath") or ""))
        phone = ""
        floor = ""
        unit = ""
        if shop_id:
            try:
                detail = client.get(
                    f"{LINK_API}/shop/{shop_id}",
                    headers={**JSON_HEADERS, "Referer": f"{LINK_BASE}/tc/", "Origin": LINK_BASE},
                    timeout=20,
                ).json()
                info = ((detail.get("data") or {}).get("shopInfo") or {})
                phone = norm(info.get("telephone"))
                floor, unit = parse_floor_shop(str(info.get("locationTc") or ""))
                photos = info.get("shopPhotos") or []
                if photos and isinstance(photos[0], dict):
                    photo = absolute_url(LINK_BASE, str(photos[0].get("shopPhotoPath") or photo))
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass
        if not (name and unit and phone and is_real_remote_image(photo)):
            # Keep featured photo even if unit parse failed — skip without unit/phone
            continue
        rows.append(
            {
                "source": "linkreit",
                "mall_name": mall_name,
                "store_name": name,
                "floor": floor or "商場",
                "unit": unit,
                "phone": phone,
                "image_url": photo,
            }
        )
    print(f"[crawl] link {mall_name} real photos={len(rows)}")
    return rows


def crawl_openrice_mall(client: httpx.Client, mall_name: str, *, max_pages: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for page in range(max_pages):
        params = {
            "uiLang": "zh",
            "regionId": "0",
            "whatwhere": mall_name,
            "rows": "20",
            "startAt": str(page * 20),
            "sortBy": "ORScoreDesc",
        }
        try:
            response = client.get(
                f"{OPENRICE_SEARCH}?{urlencode(params)}",
                headers={
                    **JSON_HEADERS,
                    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
                    "Origin": "https://www.openrice.com",
                },
                timeout=25,
            )
            if response.status_code >= 400:
                break
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[crawl] openrice {mall_name} p{page} fail: {exc}")
            break
        results = ((payload.get("paginationResult") or {}).get("results") or [])
        if not results:
            break
        for poi in results:
            if not isinstance(poi, dict):
                continue
            poi_id = poi.get("poiId")
            if poi_id in seen:
                continue
            seen.add(poi_id)
            name = norm(poi.get("name"))
            name = re.sub(r"\s*[\(（][^)）]{1,40}[\)）]\s*$", "", name).strip() or name
            phones = poi.get("phones") or []
            phone = ""
            if isinstance(phones, list) and phones:
                phone = norm(phones[0])
            floor, unit = parse_floor_shop(str(poi.get("address") or ""))
            door = poi.get("doorPhoto") or {}
            image_url = ""
            if isinstance(door, dict):
                urls = door.get("urls") if isinstance(door.get("urls"), dict) else {}
                image_url = norm(urls.get("standard") or door.get("url") or "")
            if not (name and phone and is_real_remote_image(image_url)):
                continue
            # Unit may be missing — use phone as unit fallback so key stays unique.
            if not unit:
                unit = f"OR{phone_digits(phone)[-4:]}"
            rows.append(
                {
                    "source": "openrice",
                    "mall_name": mall_name,
                    "store_name": name,
                    "floor": floor or "商場",
                    "unit": unit,
                    "phone": phone,
                    "image_url": image_url,
                }
            )
        if len(results) < 20:
            break
        time.sleep(0.35)
    return rows



def crawl_swire_shopping(client: httpx.Client, mall_name: str, url: str) -> list[dict[str, Any]]:
    """Best-effort scrape of Swire shopping directory pages for tenant images."""
    rows: list[dict[str, Any]] = []
    try:
        response = client.get(url, headers={**UA, "Accept": "text/html"}, timeout=35)
        html = response.text
    except Exception as exc:  # noqa: BLE001
        print(f"[crawl] swire {mall_name} fail: {exc}")
        return rows

    # Card-like blocks with title + optional image URL
    patterns = [
        re.compile(
            r"title:\s*'(?P<title>(?:\\'|[^'])*)'[\s\S]{0,400}?image:\s*'(?P<img>(?:\\'|[^'])*)'",
            re.I,
        ),
        re.compile(
            r'data-name=["\'](?P<title>[^"\']+)["\'][^>]{0,300}?(?:src|data-src)=["\'](?P<img>https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)',
            re.I,
        ),
        re.compile(
            r'(?:src|data-src)=["\'](?P<img>https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\'][^>]{0,200}?alt=["\'](?P<title>[^"\']{2,80})',
            re.I,
        ),
    ]
    seen: set[str] = set()
    for pat in patterns:
        for m in pat.finditer(html):
            name = norm(m.group("title"))
            image_url = absolute_url(url, m.group("img"))
            if not name or not is_real_remote_image(image_url):
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            # Synthetic unit/phone so directory index can match by name within mall
            rows.append(
                {
                    "source": "swire_directory",
                    "mall_name": mall_name,
                    "store_name": name,
                    "floor": "商場",
                    "unit": f"SW{len(rows)+1:03d}",
                    "phone": "",
                    "image_url": image_url,
                }
            )
    print(f"[crawl] swire {mall_name} image cards={len(rows)}")
    return rows


def crawl_all_directories(mall_names: list[str], *, openrice_pages: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        rows.extend(crawl_yoho_shops(client))
        for mall_name, centre_id in LINK_CENTRE_IDS.items():
            rows.extend(crawl_link_centre(client, mall_name, centre_id))
        for mall_name, page_url in SWIRE_SHOPPING_PAGES.items():
            rows.extend(crawl_swire_shopping(client, mall_name, page_url))
        for i, mall_name in enumerate(mall_names):
            batch = crawl_openrice_mall(client, mall_name, max_pages=openrice_pages)
            rows.extend(batch)
            if (i + 1) % 10 == 0:
                print(f"[crawl] openrice progress {i + 1}/{len(mall_names)}")
            time.sleep(0.25)
    # Deduplicate by mall+phone (or mall+name when phone missing)
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        mall_id = make_mall_id(row["mall_name"])
        phone = phone_digits(row.get("phone"))
        if phone and len(phone) >= 8:
            key = f"{mall_id}||p||{phone}"
        else:
            key = f"{mall_id}||n||{norm(row.get('store_name')).casefold()}"
        prev = best.get(key)
        if not prev or (len(row.get("unit") or "") > len(prev.get("unit") or "")):
            best[key] = row
    out = list(best.values())
    print(f"[crawl] unique directory rows with real photos={len(out)}")
    return out


# ---------------------------------------------------------------------------
# Match + localize against malls.json
# ---------------------------------------------------------------------------


def index_directory(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_phone: dict[str, dict[str, Any]] = {}
    by_unit: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        mall_id = make_mall_id(row["mall_name"])
        row = {**row, "mall_id": mall_id}
        phone = phone_digits(row.get("phone"))
        if phone and len(phone) >= 8:
            by_phone[f"{mall_id}||{phone}"] = row
        unit = norm(row.get("unit"))
        if unit:
            by_unit[f"{mall_id}||{unit.casefold()}"] = row
        name = norm(row.get("store_name"))
        if name:
            by_name[f"{mall_id}||{name.casefold()}"] = row
            # Also index short brand token (first chunk before space / ｜)
            token = re.split(r"[\s\|｜/]+", name)[0].casefold()
            if len(token) >= 2:
                by_name.setdefault(f"{mall_id}||{token}", row)
    return by_phone, by_unit, by_name


def match_offer(
    *,
    mall_id: str,
    offer: dict[str, Any],
    by_phone: dict[str, dict[str, Any]],
    by_unit: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    phone = phone_digits(offer.get("phone"))
    unit = norm(offer.get("shop_number") or offer.get("unit"))
    name = norm(offer.get("store_name"))
    if phone and len(phone) >= 8:
        hit = by_phone.get(f"{mall_id}||{phone}")
        if hit:
            return hit
    if unit:
        hit = by_unit.get(f"{mall_id}||{unit.casefold()}")
        if hit:
            return hit
    if name:
        hit = by_name.get(f"{mall_id}||{name.casefold()}")
        if hit:
            return hit
        token = re.split(r"[\s\|｜/]+", name)[0].casefold()
        if len(token) >= 2:
            hit = by_name.get(f"{mall_id}||{token}")
            if hit:
                return hit
    return None


def apply_to_malls(
    malls_payload: dict[str, Any],
    by_phone: dict[str, dict[str, Any]],
    by_unit: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
    *,
    max_download: int,
    workers: int,
) -> tuple[int, int, list[dict[str, Any]]]:
    STORE_IMG_DIR.mkdir(parents=True, exist_ok=True)
    matched = 0
    downloaded = 0
    directory_rows: list[dict[str, Any]] = []
    download_jobs: list[tuple[str, str, Path, dict[str, Any], str]] = []
    brand_applied = 0

    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            mall_id = make_mall_id(mall_name)
            mall["mall_id"] = mall_id
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict) or offer.get("type") == "fallback":
                    continue
                unit = norm(offer.get("shop_number"))
                phone = norm(offer.get("phone"))
                store_key = make_store_key(mall_id, unit, phone)
                offer["store_key"] = store_key
                offer["mall_id"] = mall_id

                hit = match_offer(
                    mall_id=mall_id,
                    offer=offer,
                    by_phone=by_phone,
                    by_unit=by_unit,
                    by_name=by_name,
                )
                remote = norm((hit or {}).get("image_url"))
                dest = STORE_IMG_DIR / f"{store_key}.jpg"

                if hit and is_real_remote_image(remote):
                    matched += 1
                    directory_rows.append(
                        {
                            **hit,
                            "store_key": store_key,
                            "matched_store_name": offer.get("store_name"),
                            "matched_unit": unit,
                            "matched_phone": phone,
                        }
                    )
                    download_jobs.append((store_key, remote, dest, offer, "directory_crawl"))
                else:
                    brand_id = resolve_chain_brand(offer.get("store_name"))
                    if brand_id and apply_brand_to_store(brand_id, dest):
                        rel = f"frontend/images/stores/{store_key}.jpg"
                        offer["store_image_url"] = rel
                        offer["facade_image_url"] = rel
                        offer["image_url"] = rel
                        offer["image_source"] = "chain_brand"
                        offer["brand_id"] = brand_id
                        matched += 1
                        brand_applied += 1
                    else:
                        fallback = default_image_for_vertical(offer.get("vertical_category"))
                        offer["store_image_url"] = fallback
                        offer["facade_image_url"] = fallback
                        offer["image_url"] = fallback
                        offer.pop("image_source", None)
                        offer.pop("brand_id", None)

    download_jobs = download_jobs[: max(0, max_download)]

    def _one(job: tuple[str, str, Path, dict[str, Any], str]) -> tuple[str, bool, dict[str, Any], str]:
        store_key, url, dest, offer, source = job
        ok = download_image(url, dest)
        return store_key, ok, offer, source

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_one, job) for job in download_jobs]
        for fut in as_completed(futures):
            store_key, ok, offer, source = fut.result()
            rel = f"frontend/images/stores/{store_key}.jpg"
            if ok:
                offer["store_image_url"] = rel
                offer["facade_image_url"] = rel
                offer["image_url"] = rel
                offer["image_source"] = source
                downloaded += 1
            else:
                brand_id = resolve_chain_brand(offer.get("store_name"))
                if brand_id and apply_brand_to_store(brand_id, dest := STORE_IMG_DIR / f"{store_key}.jpg"):
                    offer["store_image_url"] = rel
                    offer["facade_image_url"] = rel
                    offer["image_url"] = rel
                    offer["image_source"] = "chain_brand"
                    offer["brand_id"] = brand_id
                    brand_applied += 1
                else:
                    fallback = default_image_for_vertical(offer.get("vertical_category"))
                    offer["store_image_url"] = fallback
                    offer["facade_image_url"] = fallback
                    offer["image_url"] = fallback
                    offer.pop("image_source", None)

    print(f"[crawl] brand_placards_applied={brand_applied}")
    return matched, downloaded, directory_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl mall directories for real facade photos")
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--openrice-pages", type=int, default=2)
    parser.add_argument("--max-download", type=int, default=400)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--skip-crawl", action="store_true", help="Reuse official_directory.json cache")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    malls_payload = load_json(args.malls, {})
    registry = load_json(args.registry, {"malls": []})
    if not isinstance(malls_payload, dict) or not malls_payload.get("districts"):
        print(f"[crawl_mall_directories] missing malls: {args.malls}")
        return 1

    mall_names = []
    if isinstance(registry, dict):
        for mall in registry.get("malls") or []:
            if isinstance(mall, dict) and mall.get("mall_name"):
                mall_names.append(norm(mall["mall_name"]))
    if not mall_names:
        for district in malls_payload.get("districts") or []:
            for mall in district.get("malls") or []:
                if isinstance(mall, dict) and mall.get("mall_name"):
                    mall_names.append(norm(mall["mall_name"]))

    if args.skip_crawl:
        cached = load_json(DIRECTORY_CACHE, {})
        crawled = [
            r
            for r in (cached.get("crawled") or cached.get("stores") or [])
            if isinstance(r, dict) and is_real_remote_image(str(r.get("image_url") or ""))
        ]
        print(f"[crawl] reused cache rows={len(crawled)}")
    else:
        crawled = crawl_all_directories(mall_names, openrice_pages=args.openrice_pages)

    ensure_category_defaults()
    ensure_all_brand_images()
    by_phone, by_unit, by_name = index_directory(crawled)
    matched, downloaded, directory_rows = apply_to_malls(
        malls_payload,
        by_phone,
        by_unit,
        by_name,
        max_download=args.max_download,
        workers=args.workers,
    )

    # Build auditor indexes from matched + crawled
    stores_for_audit = []
    for row in crawled:
        mall_id = make_mall_id(row["mall_name"])
        store_key = make_store_key(mall_id, row.get("unit"), row.get("phone"))
        stores_for_audit.append(
            {
                "store_key": store_key,
                "mall_id": mall_id,
                "mall_name": row["mall_name"],
                "floor": row.get("floor"),
                "unit": row.get("unit"),
                "shop_number": row.get("unit"),
                "store_name": row.get("store_name"),
                "phone": row.get("phone"),
                "image_url": row.get("image_url"),
                "source": row.get("source"),
                "seen_at": utc_now(),
            }
        )

    directory_payload = {
        "updated_at": utc_now(),
        "mall_count": len(set(make_mall_id(n) for n in mall_names)),
        "store_count": len(stores_for_audit),
        "matched_offers": matched,
        "downloaded": downloaded,
        "crawled": crawled,
        "stores": stores_for_audit,
        "by_unit": {
            f"{r['mall_id']}||{norm(r['unit']).casefold()}": {
                "store_name": r["store_name"],
                "store_key": r["store_key"],
                "floor": r.get("floor"),
                "phone": r.get("phone"),
            }
            for r in stores_for_audit
        },
        "by_name_unit": {
            f"{r['mall_id']}||{norm(r['store_name']).casefold()}||{norm(r['unit']).casefold()}": r["store_key"]
            for r in stores_for_audit
        },
        "by_phone": {
            f"{r['mall_id']}||{phone_digits(r['phone'])}": r["store_key"]
            for r in stores_for_audit
            if phone_digits(r.get("phone"))
        },
    }

    if not args.dry_run:
        write_json(DIRECTORY_CACHE, directory_payload)
        write_json(args.malls, malls_payload)

    # Stats: how many cards still on default vs local facade
    real_local = 0
    defaulted = 0
    picsum_left = 0
    for district in malls_payload.get("districts") or []:
        for mall in district.get("malls") or []:
            for offer in mall.get("store_offers") or []:
                if not isinstance(offer, dict) or offer.get("type") == "fallback":
                    continue
                url = str(offer.get("store_image_url") or "")
                if "picsum" in url:
                    picsum_left += 1
                elif url.startswith("frontend/images/stores/"):
                    real_local += 1
                else:
                    defaulted += 1

    print(
        "[crawl_mall_directories] "
        f"crawled={len(crawled)} matched={matched} downloaded={downloaded} "
        f"local_real={real_local} defaulted={defaulted} picsum_left={picsum_left}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
