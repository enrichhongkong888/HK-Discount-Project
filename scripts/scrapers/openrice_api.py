# -*- coding: utf-8 -*-
"""OpenRice internal JSON search API (bypasses HTML listing parse).

Endpoint: GET https://www.openrice.com/api/v2/search
  - regionId=0 (Hong Kong)
  - whatwhere=<mall name>
  - uiLang=zh, sortBy=ORScoreDesc

Uses shared httpx.AsyncClient via afetch_json, Accept: application/json,
Referer/Origin disguise, and asyncio.Semaphore(2) + domain-level limit.
On failure, callers should degrade to verified cache.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from store_channels.http_util import afetch_text, normalize_phone

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "openrice_api_rows.json"

SEARCH_URL = "https://www.openrice.com/api/v2/search"
REGION_HK = 0
ROWS_PER_PAGE = 30
MAX_PAGES = 2

# Dedicated OpenRice throttle (also gated by domain semaphore openrice.com=2).
_OPENRICE_SEM = asyncio.Semaphore(2)

JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
    "Origin": "https://www.openrice.com",
}

API_TIMEOUT = httpx.Timeout(connect=3.0, read=20.0, write=20.0, pool=3.0)

_SHOP_RE = re.compile(
    r"(?:Shop\s*)?([A-Za-z]?\d+[A-Za-z0-9\-/,]*)\s*(?:號舖|舖|鋪)",
    re.I,
)
_FLOOR_RE = re.compile(
    r"((?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:/F|樓|層)|地下|地庫|平台|美食廣場)",
    re.I,
)

DEFAULT_DINING_TITLE = "店內指定特惠套餐 / 堂食折扣"
# Legacy long boilerplate — treated as generic so it is never shown as a title.
EVERGREEN_DINING = DEFAULT_DINING_TITLE
_LEGACY_EVERGREEN = (
    "OpenRice 門市／外賣常態禮遇：堂食或外賣自取惠顧可享店內當期推廣；"
    "實際條款以 OpenRice App／店內告示為準。"
)
_LEGACY_SHORT_DEFAULT = "店內當期指定餐飲優惠（請參閱門市告示）"

_GENERIC_TITLE_RE = re.compile(
    r"^(?:OpenRice\s*)?(?:門市／外賣(?:常態禮遇|優惠)|門市\s*/\s*外賣(?:常態禮遇|優惠))(?:[:：]|$)",
    re.I,
)

# Concrete promo signals: cash amount, % off, voucher wording, named set deals.
_SUBSTANTIVE_OFFER_RE = re.compile(
    r"("
    r"\$\s*\d+|HK\$\s*\d+|港幣\s*\d+|"
    r"\d+(?:\.\d+)?\s*折|\d+\s*%\s*(?:off|折扣)?|"
    r"現金券|現金劵|餐飲券|優惠券|禮券|coupon|voucher|"
    r"半價|買一送一|BOGO|第二件|"
    r"減\s*\$|滿\s*\$|即減|回贈|"
    r"套餐|放題|特惠|折扣|訂座|外賣|自取|即買即用|限時"
    r")",
    re.I,
)


def is_generic_openrice_title(text: str) -> bool:
    """Alias used by callers; same as is_generic_text."""
    return is_generic_text(text)


def is_generic_text(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    if t in (DEFAULT_DINING_TITLE, EVERGREEN_DINING, _LEGACY_EVERGREEN, _LEGACY_SHORT_DEFAULT):
        return True
    if "OpenRice 門市 / 外賣常態禮遇" in t or "OpenRice 門市／外賣常態禮遇" in t:
        return True
    if "OpenRice 門市/外賣常態禮遇" in t:
        return True
    if "店內指定特惠套餐" in t or "店內當期指定餐飲優惠" in t:
        return True
    if t in ("門市／外賣優惠", "OpenRice 門市／外賣優惠", "OpenRice 門市 / 外賣常態禮遇"):
        return True
    if _GENERIC_TITLE_RE.match(t):
        return True
    if re.match(r"^OpenRice\s", t, re.I) and len(t) < 48 and "優惠" in t:
        return True
    return False


def is_substantive_offer_title(text: str) -> bool:
    """True only when title carries a concrete dining promo (not placeholder copy)."""
    t = _normalize_promo_title(str(text or ""))
    if not t or is_generic_text(t):
        return False
    if _SUBSTANTIVE_OFFER_RE.search(t):
        return True
    # Named voucher / set-meal product titles from OpenRice (e.g. dish-named coupons).
    if len(t) >= 4 and "門市" not in t and "常態" not in t and "告示" not in t:
        return True
    return False


def has_substantive_dining_offer(raw: dict[str, Any]) -> bool:
    title = extract_real_offer_title(raw)
    return is_substantive_offer_title(title)


def _normalize_promo_title(text: str) -> str:
    t = str(text or "").strip()
    if "｜" in t:
        t = t.split("｜", 1)[-1].strip()
    if re.match(r"^OpenRice\s+", t, re.I):
        stripped = re.sub(r"^OpenRice\s+", "", t, flags=re.I).strip()
        if stripped and not is_generic_text(stripped):
            return stripped
    return t


def _voucher_titles_from_raw(raw: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    def _push(value: Any) -> None:
        text = _normalize_promo_title(str(value or ""))
        if not text or is_generic_text(text):
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        titles.append(text[:120])

    vouchers = raw.get("vouchers")
    if isinstance(vouchers, list):
        for item in vouchers:
            if not isinstance(item, dict):
                continue
            _push(
                item.get("title")
                or item.get("voucher_title")
                or item.get("shortTitle")
                or item.get("name")
            )
    related = raw.get("relatedVoucher")
    if isinstance(related, dict):
        _push(
            related.get("title")
            or related.get("voucher_title")
            or related.get("shortTitle")
            or related.get("name")
        )
    return titles


def extract_real_offer_title(raw: dict[str, Any]) -> str:
    """Extract concrete promo title; short default only when nothing useful exists."""
    # 1. Prefer voucher / cash-coupon titles (join multiple).
    voucher_titles = _voucher_titles_from_raw(raw)
    if voucher_titles:
        return " / ".join(voucher_titles)[:160]

    # 2. Specific discount / promo description fields.
    for key in (
        "offer_name",
        "discount_text",
        "voucher_title",
        "promotion_title",
        "promo_title",
        "title",
        "description",
        "details",
    ):
        val = raw.get(key)
        if not isinstance(val, str):
            continue
        text = _normalize_promo_title(val)
        if text and not is_generic_text(text):
            return text[:160]

    # 3. Booking / takeaway discount tags.
    booking = str(
        raw.get("booking_discount_text")
        or raw.get("takeaway_discount_text")
        or ""
    ).strip()
    if booking and not is_generic_text(booking):
        return f"線上預約享 {booking}"[:160]

    # 4. No concrete discount detail — short placeholder (never long boilerplate).
    return ""


def display_offer_title(raw: dict[str, Any]) -> str:
    """Return substantive promo title only; empty string means drop the offer."""
    title = extract_real_offer_title(raw)
    return title if is_substantive_offer_title(title) else ""


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[openrice_api] fail load {path}: {exc}")
        return None


def save_api_cache(rows: list[dict[str, Any]], *, merge: bool = True) -> None:
    """Persist rows; when merge=True keep prior mall_hint groups that have no new rows."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = list(rows)
    if merge:
        prior = load_api_cache()
        new_malls = {
            str(r.get("mall_hint") or r.get("mall_name") or "").strip()
            for r in rows
            if str(r.get("mall_hint") or r.get("mall_name") or "").strip()
        }
        for row in prior:
            hint = str(row.get("mall_hint") or row.get("mall_name") or "").strip()
            if hint and hint not in new_malls:
                merged.append(row)
    CACHE_PATH.write_text(
        json.dumps({"rows": merged, "source": "openrice_api"}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def load_api_cache() -> list[dict[str, Any]]:
    payload = _load_json(CACHE_PATH)
    if isinstance(payload, dict):
        rows = payload.get("rows") or []
        return [r for r in rows if isinstance(r, dict)]
    return []


def _first_phone(poi: dict[str, Any]) -> str:
    phones = poi.get("phones") or []
    if isinstance(phones, list) and phones:
        return normalize_phone(str(phones[0]))
    return normalize_phone(str(poi.get("phone") or ""))


# OpenRice photoTypeId hints (community / observed). Prefer door/env; never treat as food alone.
_PHOTO_TYPE_DOOR = {1, 2}  # door / environment when present
_PHOTO_TYPE_FOOD = {3, 5, 6, 7}  # food / dish / menu variants when present

_FACADE_LABEL_RE = re.compile(
    r"("
    r"door|doorshot|door[\s_-]?photo|storefront|facade|façade|exterior|"
    r"environment|ambiance|ambience|interior(?!\s*food)|"
    r"門面|门面|店面|外觀|外观|舖面|铺面|招牌|門口|门口|環境|环境|店內環境|店内环境"
    r")",
    re.I,
)
_FOOD_LABEL_RE = re.compile(
    r"("
    r"food|dish|dishes|menu|meal|cuisine|dessert|drink|beverage|"
    r"coffee|latte|mocha|cappuccino|espresso|tea|smoothie|juice|"
    r"sandwich|burger|steak|pizza|sushi|ramen|noodle|pasta|"
    r"tiramisu|cake|bread|toast|salad|soup|rice|"
    r"菜|餐|美食|餸|饭|飯|麵|面|粥|粉|飯糰|三文治|漢堡|汉堡|"
    r"牛扒|牛排|刺身|壽司|寿司|甜品|蛋糕|咖啡|奶茶|飲品|饮品|"
    r"套餐|外賣餐|菜单|菜單|價目|价目|foodie|#food"
    r")",
    re.I,
)


def _abs_media_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return f"https://www.openrice.com{text}"
    return ""


def _photo_blob(photo: dict[str, Any]) -> str:
    parts = [
        photo.get("caption"),
        photo.get("otherCaption"),
        photo.get("photoType"),
        photo.get("photoTypeName"),
        photo.get("category"),
        photo.get("categoryName"),
        photo.get("label"),
        photo.get("type"),
        photo.get("typeName"),
        photo.get("album"),
        photo.get("albumName"),
        photo.get("tag"),
        photo.get("tags"),
        photo.get("mediaType"),
        photo.get("mediaUnitType"),
    ]
    return " ".join(str(p or "") for p in parts)


def _photo_url_from_obj(photo: Any) -> str:
    if isinstance(photo, str):
        return _abs_media_url(photo)
    if not isinstance(photo, dict):
        return ""
    urls = photo.get("urls") if isinstance(photo.get("urls"), dict) else {}
    for key in ("standard", "full", "mx", "lv", "thumbnail", "icon"):
        hit = _abs_media_url(urls.get(key))
        if hit:
            return hit
    return _abs_media_url(
        photo.get("url")
        or photo.get("photoUrl")
        or photo.get("photo_url")
        or photo.get("image")
        or photo.get("imageUrl")
    )


def is_food_photo(photo: Any) -> bool:
    """True when a photo is tagged / captioned as food, dish, or menu."""
    if not isinstance(photo, dict):
        return False
    if photo.get("isRmsMenu") in (True, 1, "1"):
        return True
    tid = photo.get("photoTypeId")
    try:
        if tid is not None and int(tid) in _PHOTO_TYPE_FOOD:
            return True
    except (TypeError, ValueError):
        pass
    blob = _photo_blob(photo)
    if _FOOD_LABEL_RE.search(blob):
        return True
    return False


def is_facade_or_environment_photo(photo: Any, *, treat_door_field: bool = False) -> bool:
    """True for door / environment / storefront / facade / exterior photos."""
    if treat_door_field:
        return True
    if not isinstance(photo, dict):
        return False
    if is_food_photo(photo):
        return False
    tid = photo.get("photoTypeId")
    try:
        if tid is not None and int(tid) in _PHOTO_TYPE_DOOR:
            return True
    except (TypeError, ValueError):
        pass
    blob = _photo_blob(photo)
    if _FACADE_LABEL_RE.search(blob):
        return True
    # Explicit string category fields
    for key in ("photoType", "photoTypeName", "category", "categoryName", "label", "type", "typeName"):
        val = str(photo.get(key) or "").strip().lower()
        if val in {
            "door",
            "environment",
            "storefront",
            "facade",
            "exterior",
            "門面",
            "门面",
            "環境",
            "环境",
        }:
            return True
    return False


def extract_poi_image_url(poi: dict[str, Any]) -> str:
    """Prefer OpenRice door/environment facade; never return food/dish/menu shots."""
    if not isinstance(poi, dict):
        return ""

    # 1) Official doorPhoto (OpenRice curated storefront) — highest priority.
    door = poi.get("doorPhoto") or poi.get("door_photo")
    if isinstance(door, (dict, str)):
        hit = _photo_url_from_obj(door)
        if hit:
            return hit

    # 2) Scan photo arrays — only keep facade / environment labelled shots.
    photo_lists: list[Any] = []
    for key in ("photos", "photoList", "photo_list", "images", "image_urls", "poiPhotos"):
        items = poi.get(key)
        if isinstance(items, list) and items:
            photo_lists.append(items)

    facade_candidates: list[str] = []
    for items in photo_lists:
        for item in items:
            if is_food_photo(item):
                continue
            if not is_facade_or_environment_photo(item):
                continue
            hit = _photo_url_from_obj(item)
            if hit:
                facade_candidates.append(hit)
    if facade_candidates:
        return facade_candidates[0]

    # 3) Fallback: brand logo / storefront banner — still never food.
    for key in (
        "logo_url",
        "logoUrl",
        "logo",
        "brandLogo",
        "brand_logo",
        "bizLogo",
        "shopLogo",
        "coverPhoto",
        "cover_photo",
        "banner",
        "banner_url",
        "bannerUrl",
        "doorPhotoUrl",
        "storefront_url",
        "storefrontUrl",
    ):
        raw = poi.get(key)
        if isinstance(raw, dict):
            if is_food_photo(raw):
                continue
            hit = _photo_url_from_obj(raw)
            if hit:
                return hit
        else:
            hit = _abs_media_url(raw)
            if hit and not _FOOD_LABEL_RE.search(str(raw)):
                return hit

    # 4) No safe facade/logo — return empty (caller may use neutral placeholder).
    return ""


def _parse_floor_shop(poi: dict[str, Any]) -> tuple[str, str]:
    floor = str(poi.get("floor") or "").strip()
    address = str(poi.get("address") or "").strip()
    shop = ""
    shop_m = _SHOP_RE.search(address)
    if shop_m:
        shop = shop_m.group(1).replace("，", ",").strip()
    if not floor:
        floor_m = _FLOOR_RE.search(address)
        if floor_m:
            floor = floor_m.group(1).strip()
    return floor, shop


def _promo_from_poi(poi: dict[str, Any]) -> tuple[str, str, bool, str | None, str | None]:
    """Return (title_suffix, details, is_evergreen, start_date, expiry_date)."""
    for key in ("vouchers", "promotions", "coupons", "bizCoupons", "relatedVoucher"):
        items = poi.get(key)
        if key == "relatedVoucher" and isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            continue
        first = items[0]
        if not isinstance(first, dict):
            continue
        title = str(
            first.get("title")
            or first.get("voucher_title")
            or first.get("offer_name")
            or first.get("discount_text")
            or first.get("shortTitle")
            or first.get("name")
            or first.get("promoTitle")
            or ""
        ).strip()
        desc = str(
            first.get("description")
            or first.get("desc")
            or first.get("content")
            or title
            or ""
        ).strip()
        start = None
        end = None
        for sk in ("startTime", "start_date", "effective_from", "validFrom"):
            raw = first.get(sk)
            if not raw:
                continue
            text = str(raw).strip()
            if len(text) >= 10 and text[4] == "-":
                start = text[:10]
                break
        for ek in ("endTime", "expiry_date", "end_date", "validTo", "expireTime"):
            raw = first.get(ek)
            if not raw:
                continue
            text = str(raw).strip()
            if len(text) >= 10 and text[4] == "-":
                end = text[:10]
                break
        if title or desc:
            details = (desc or title)[:500]
            if title and title not in details:
                details = f"{title}。{details}"[:500]
            evergreen = not (start and end)
            return title, details, evergreen, start, end
    return "", EVERGREEN_DINING, True, None, None


def poi_to_row(poi: dict[str, Any], *, mall_hint: str) -> dict[str, Any] | None:
    name = str(poi.get("name") or "").strip()
    # Strip trailing mall annotation: "Bamboo Thai (朗豪坊)"
    name = re.sub(r"\s*[\(（][^)）]{1,40}[\)）]\s*$", "", name).strip() or name
    floor, shop = _parse_floor_shop(poi)
    phone = _first_phone(poi)
    if not (name and floor and shop and phone):
        return None
    title_sfx, details, evergreen, start, end = _promo_from_poi(poi)
    source_url = str(poi.get("shortenUrl") or "").strip()
    if not source_url:
        poi_id = poi.get("poiId")
        if poi_id:
            source_url = f"https://www.openrice.com/zh/hongkong/r-{poi_id}"
        else:
            return None
    promo_fields: dict[str, Any] = {
        "title": title_sfx,
        "details": details,
        "vouchers": poi.get("vouchers"),
        "relatedVoucher": poi.get("relatedVoucher"),
    }
    display_title = display_offer_title(promo_fields)
    image_url = extract_poi_image_url(poi)
    row: dict[str, Any] = {
        "store_name": name,
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "details": details,
        "title": f"{name}｜{display_title}"[:120],
        "offer_name": title_sfx or None,
        "voucher_title": (" / ".join(_voucher_titles_from_raw(poi)) or None),
        "discount_text": str(poi.get("discountText") or poi.get("discount_text") or "").strip() or None,
        "mall_hint": mall_hint,
        "address": str(poi.get("address") or mall_hint),
        "source_url": source_url,
        "is_evergreen": evergreen,
        "poi_id": poi.get("poiId"),
        "mall_name_api": str(poi.get("mallName") or "").strip(),
    }
    if image_url:
        row["image"] = image_url
        row["photo_url"] = image_url
    if start:
        row["start_date"] = start
    if end:
        row["expiry_date"] = end
    return row



async def _search_page(mall_name: str, *, start_at: int) -> list[dict[str, Any]]:
    params = {
        "uiLang": "zh",
        "regionId": str(REGION_HK),
        "whatwhere": mall_name,
        "rows": str(ROWS_PER_PAGE),
        "startAt": str(start_at),
        "sortBy": "ORScoreDesc",
    }
    url = f"{SEARCH_URL}?{urlencode(params)}"
    async with _OPENRICE_SEM:
        raw = await afetch_text(url, timeout=API_TIMEOUT, headers=JSON_HEADERS)
    text = (raw or "").lstrip()
    if not text.startswith("{") and not text.startswith("["):
        raise ValueError("non-json response (bot challenge or blocked)")
    data = json.loads(text)
    if not isinstance(data, dict):
        return []
    results = (data.get("paginationResult") or {}).get("results") or []
    return [r for r in results if isinstance(r, dict)]


async def search_mall_pois(mall_name: str) -> list[dict[str, Any]]:
    """Fetch POIs for one mall across a few pages; empty on hard failure."""
    collected: list[dict[str, Any]] = []
    seen: set[Any] = set()
    try:
        for page in range(MAX_PAGES):
            batch = await _search_page(mall_name, start_at=page * ROWS_PER_PAGE)
            if not batch:
                break
            for poi in batch:
                pid = poi.get("poiId")
                if pid in seen:
                    continue
                seen.add(pid)
                collected.append(poi)
            if len(batch) < ROWS_PER_PAGE:
                break
    except Exception as exc:  # noqa: BLE001
        print(f"[openrice_api] search fail {mall_name}: {exc}")
        return []
    return collected


async def scrape_openrice_api_rows(
    malls: tuple[str, ...] | list[str],
    *,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Live JSON scrape → normalized seed-compatible rows.

    Returns [] when the API is unavailable or yields no parseable six-field rows
    (caller should fall back to verified cache / HTML / seeds).
    """
    rows: list[dict[str, Any]] = []
    api_failures = 0

    async def _one(mall: str) -> tuple[str, list[dict[str, Any]], bool]:
        pois = await search_mall_pois(mall)
        if not pois:
            return mall, [], True  # treat empty as soft failure for that mall
        out: list[dict[str, Any]] = []
        for poi in pois:
            # Prefer POIs that mention the mall in mallName or address.
            mall_name_api = str(poi.get("mallName") or "")
            address = str(poi.get("address") or "")
            if mall not in mall_name_api and mall not in address and mall[:4] not in address:
                # Still keep if floor/shop parse; mall_match will gate later.
                pass
            row = poi_to_row(poi, mall_hint=mall)
            if row:
                out.append(row)
        return mall, out, False

    results = await asyncio.gather(*(_one(m) for m in malls))
    for mall, mall_rows, failed in results:
        if failed:
            api_failures += 1
        print(f"[openrice_api] {mall} pois_rows={len(mall_rows)}")
        rows.extend(mall_rows)

    if not rows:
        print(f"[openrice_api] no rows (mall_failures={api_failures}/{len(malls)})")
        return []

    if persist_cache:
        save_api_cache(rows, merge=True)
    print(f"[openrice_api] live_rows={len(rows)}")
    return rows
