# -*- coding: utf-8 -*-
"""領展 (Link REIT) 與恒隆 (Hang Lung) 商場商戶目錄渠道。

優先呼叫 LinkHK 內部 JSON API（scripts/scrapers/linkreit_api.py），
失敗時降級至公開目錄 HTML，再降級至驗證過的 cache；並合併 seed。
缺欄者丟棄。僅輸出通過 store_authenticity 六欄＋lifecycle 的
store offers／verified pins。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

from .brand_aliases import match_brand
from .http_util import afetch_text, normalize_phone, shared_http
from .mall_match import build_registry_index, match_mall
from .offer_emit import build_store_offer, filter_authentic

# Allow ``from scrapers...`` when imported as store_channels.link_reit_channel
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from scrapers.linkreit_api import (  # noqa: E402
    load_api_cache as load_linkreit_api_cache,
    scrape_linkreit_api_rows,
)

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "data" / "link_hanglung_tenants.json"
CACHE_PATH = ROOT / "data" / "cache" / "link_reit_offers.json"
PINS_CACHE = ROOT / "data" / "cache" / "link_reit_pins.json"
SOURCE_NAME = "link_reit_channel"

# Registry mall_name -> public directory URLs (best-effort).
LINK_HANG_LUNG_DIRECTORIES: list[dict[str, str]] = [
    {
        "mall_name": "赤柱廣場",
        "district": "南區",
        "developer": "link",
        "url": "https://www.stanleyplaza.com/tc/shopping",
    },
    {
        "mall_name": "樂富廣場",
        "district": "九龍城區",
        "developer": "link",
        "url": "https://www.lokfuplaza.com/tc/shopping",
    },
    {
        "mall_name": "黃大仙中心",
        "district": "黃大仙區",
        "developer": "link",
        "url": "https://www.templemall.com.hk/tc/shopping",
    },
    {
        "mall_name": "康怡廣場",
        "district": "東區",
        "developer": "hanglung",
        "url": "https://www.kornhillplaza.com.hk/tc/shopping",
    },
    {
        "mall_name": "荷里活廣場",
        "district": "黃大仙區",
        "developer": "hanglung",
        "url": "https://www.plaza-hollywood.com.hk/tc/shopping",
    },
]

DEFAULT_DETAILS = (
    "發展商目錄商戶常態禮遇：惠顧正價貨品／餐飲可享商場會員或店內當期推廣折扣；"
    "實際條款以店內告示及官方 App 為準。"
)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[link] fail load {path}: {exc}")
        return None


def _strip(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return unescape(re.sub(r"\n+", "\n", text))


def _extract_json_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []
    for pat in (
        r'<script[^>]+type="application/ld\+json"[^>]*>([\s\S]*?)</script>',
        r"__NEXT_DATA__\s*=\s*(\{[\s\S]*?\})\s*;\s*</script>",
        r"window\.__NUXT__\s*=\s*(\{[\s\S]*?\});",
    ):
        for m in re.finditer(pat, html, flags=re.I):
            raw = m.group(1).strip()
            try:
                blobs.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return blobs


def _walk_tenant_dicts(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        keys = {k.lower() for k in node}
        if {"name", "phone"} <= keys or {"shopname", "tel"} <= keys or (
            "name" in keys and ("shopno" in keys or "shop_number" in keys or "unit" in keys)
        ):
            out.append(node)
        for v in node.values():
            _walk_tenant_dicts(v, out)
    elif isinstance(node, list):
        for item in node:
            _walk_tenant_dicts(item, out)


def parse_directory_html(html: str, *, source_url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for blob in _extract_json_blobs(html):
        found: list[dict] = []
        _walk_tenant_dicts(blob, found)
        for node in found:
            name = str(
                node.get("name")
                or node.get("shopName")
                or node.get("shop_name")
                or node.get("title")
                or ""
            ).strip()
            phone = normalize_phone(
                str(node.get("phone") or node.get("tel") or node.get("telephone") or "")
            )
            floor = str(node.get("floor") or node.get("level") or "").strip()
            shop = str(
                node.get("shop_number")
                or node.get("shopNo")
                or node.get("unit")
                or node.get("shop")
                or ""
            ).strip()
            if name and phone:
                rows.append(
                    {
                        "store_name": name,
                        "phone": phone,
                        "floor": floor,
                        "shop_number": shop,
                        "source_url": source_url,
                    }
                )

    text = _strip(html)
    for chunk in re.split(r"\n{2,}", text):
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if len(chunk) < 20 or len(chunk) > 400:
            continue
        phone_m = re.search(r"(\d{4}\s*\d{4})", chunk)
        shop_m = re.search(r"([A-Za-z]?\d+[A-Za-z0-9\-]*)\s*號舖|Shop\s*([A-Za-z]?\d+)", chunk, re.I)
        floor_m = re.search(r"(\d+\s*樓|L\d+|G/?F|地下|UG|LG|B\d)", chunk, re.I)
        if not (phone_m and shop_m and floor_m):
            continue
        name = chunk.split()[0][:40]
        rows.append(
            {
                "store_name": name,
                "phone": normalize_phone(phone_m.group(1)),
                "floor": floor_m.group(1),
                "shop_number": (shop_m.group(1) or shop_m.group(2) or "").strip(),
                "details": chunk[:300],
                "source_url": source_url,
            }
        )
    return rows


def seed_tenants() -> list[dict[str, Any]]:
    payload = _load_json(SEED_PATH)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [r for r in (payload.get("tenants") or payload.get("stores") or []) if isinstance(r, dict)]
    return []


def tenant_to_pin_and_offer(
    row: dict[str, Any],
    registry: list[dict],
    *,
    default_mall: str = "",
    default_district: str = "",
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    index = build_registry_index(registry)
    hint = str(row.get("mall_hint") or row.get("mall_name") or default_mall).strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit and default_mall:
        hit = match_mall(index, mall_hint=default_mall, address=default_district)
    if not hit:
        return None, None

    store = str(row.get("store_name") or "").strip()
    floor = str(row.get("floor") or "").strip()
    shop = str(row.get("shop_number") or "").strip()
    phone = normalize_phone(str(row.get("phone") or ""))
    source_url = str(row.get("source_url") or "").strip()
    if not (store and floor and shop and phone and source_url):
        return None, None

    brand = match_brand(store)
    pin: dict[str, str] | None = None
    if brand:
        pin = {
            "chain_id": brand[0],
            "mall_name": hit.mall_name,
            "district": hit.district,
            "floor": floor,
            "shop_number": shop,
            "phone": phone,
            "store_name": brand[1],
            "verification_status": VERIFICATION_VERIFIED,
            "source": SOURCE_NAME,
            "source_url": source_url,
        }
        if not presence_is_verified(pin):
            pin = None

    details = str(row.get("details") or row.get("offer_text") or DEFAULT_DETAILS).strip()
    title = str(row.get("title") or "").strip() or f"{store}｜發展商目錄常態優惠"
    offer = build_store_offer(
        mall_name=hit.mall_name,
        district=hit.district,
        store_name=store,
        floor=floor,
        shop_number=shop,
        phone=phone,
        title=title,
        details=details[:500],
        source_url=source_url,
        source_name=SOURCE_NAME,
        is_evergreen=bool(row.get("is_evergreen", True)),
        start_date=str(row.get("start_date") or "").strip() or None,
        expiry_date=str(row.get("expiry_date") or "").strip() or None,
    )
    return pin, offer


def _ingest_rows(
    rows: list[dict[str, Any]],
    registry_malls: list[dict],
    *,
    pins: list[dict[str, str]],
    offers: list[dict[str, Any]],
    seen_pin: set[tuple[str, str, str]],
    seen_offer: set[tuple[str, str, str]],
    default_mall: str = "",
    default_district: str = "",
) -> None:
    for row in rows:
        pin, offer = tenant_to_pin_and_offer(
            row,
            registry_malls,
            default_mall=default_mall or str(row.get("mall_hint") or ""),
            default_district=default_district or str(row.get("district") or ""),
        )
        if pin:
            key = (pin["chain_id"], pin["mall_name"], pin["shop_number"])
            if key not in seen_pin:
                seen_pin.add(key)
                pins.append(pin)
        if offer:
            key = (offer["mall_name"], offer["store_name"], offer["shop_number"])
            if key not in seen_offer:
                seen_offer.add(key)
                offers.append(offer)


def _load_verified_caches() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    pins_payload = _load_json(PINS_CACHE)
    offers_payload = _load_json(CACHE_PATH)
    pins = (
        [p for p in (pins_payload.get("pins") or []) if isinstance(p, dict)]
        if isinstance(pins_payload, dict)
        else []
    )
    offers = (
        [o for o in (offers_payload.get("offers") or []) if isinstance(o, dict)]
        if isinstance(offers_payload, dict)
        else []
    )
    return pins, offers  # type: ignore[return-value]


async def scrape_link_hanglung_directories(
    registry_malls: list[dict],
    *,
    live: bool = True,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    pins: list[dict[str, str]] = []
    offers: list[dict[str, Any]] = []
    seen_pin: set[tuple[str, str, str]] = set()
    seen_offer: set[tuple[str, str, str]] = set()

    _ingest_rows(
        seed_tenants(),
        registry_malls,
        pins=pins,
        offers=offers,
        seen_pin=seen_pin,
        seen_offer=seen_offer,
    )

    live_ok = False
    if live:
        # 1) LinkHK JSON API for Link REIT centres
        try:
            api_rows = await scrape_linkreit_api_rows()
            if api_rows:
                _ingest_rows(
                    api_rows,
                    registry_malls,
                    pins=pins,
                    offers=offers,
                    seen_pin=seen_pin,
                    seen_offer=seen_offer,
                )
                live_ok = True
                print(f"[link] using live LinkHK JSON API rows={len(api_rows)}")
            else:
                print("[link] LinkHK JSON API empty → HTML / cache")
        except Exception as exc:  # noqa: BLE001
            print(f"[link] LinkHK JSON API error → HTML / cache: {exc}")

        if not live_ok:
            cached_api = load_linkreit_api_cache()
            if cached_api:
                _ingest_rows(
                    cached_api,
                    registry_malls,
                    pins=pins,
                    offers=offers,
                    seen_pin=seen_pin,
                    seen_offer=seen_offer,
                )
                print(f"[link] degraded to LinkHK API row cache rows={len(cached_api)}")

        # 2) Public directory HTML (Hang Lung + Link microsites)
        async def _one(meta: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
            url = meta["url"]
            try:
                html = await afetch_text(url, timeout=45)
            except Exception as exc:  # noqa: BLE001
                print(f"[link] fetch fail {url}: {exc}")
                return meta, []
            parsed = parse_directory_html(html, source_url=url)
            print(f"[link] {meta['mall_name']} html_candidates={len(parsed)}")
            return meta, parsed

        live_results = await asyncio.gather(*[_one(meta) for meta in LINK_HANG_LUNG_DIRECTORIES])
        html_n = 0
        for meta, parsed in live_results:
            html_n += len(parsed)
            enriched = [
                {
                    **row,
                    "mall_hint": meta["mall_name"],
                    "source_url": row.get("source_url") or meta["url"],
                }
                for row in parsed
            ]
            _ingest_rows(
                enriched,
                registry_malls,
                pins=pins,
                offers=offers,
                seen_pin=seen_pin,
                seen_offer=seen_offer,
                default_mall=meta["mall_name"],
                default_district=meta["district"],
            )
        if html_n:
            live_ok = True

    offers = filter_authentic(offers, label="link")

    if offers or pins:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"offers": offers}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        PINS_CACHE.write_text(
            json.dumps({"pins": pins}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[link] pins={len(pins)} authentic_offers={len(offers)}")
        return pins, offers

    # Hard degrade so expand never loses Link coverage mid-outage
    cached_pins, cached_offers = _load_verified_caches()
    if cached_pins or cached_offers:
        print(
            f"[link] fallback verified cache pins={len(cached_pins)} "
            f"offers={len(cached_offers)}"
        )
        return cached_pins, cached_offers
    print(f"[link] pins={len(pins)} authentic_offers={len(offers)}")
    return pins, offers


def main() -> int:
    import asyncio

    payload = _load_json(ROOT / "data" / "malls-registry.json") or {}
    registry = list(payload.get("malls") or []) if isinstance(payload, dict) else []

    async def _run() -> None:
        async with shared_http():
            await scrape_link_hanglung_directories(registry, live=True)

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
