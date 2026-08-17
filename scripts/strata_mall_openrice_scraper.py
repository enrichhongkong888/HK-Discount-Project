# -*- coding: utf-8 -*-
"""民生／分拆業權商場：OpenRice 與地區美食指南結構化抓取。

優先呼叫 OpenRice 內部 JSON API（scripts/scrapers/openrice_api.py），
失敗時降級至 HTML 列表解析，再降級至驗證過的 cache；並合併 seed。
僅六欄齊全且通過 store_authenticity 者會輸出。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from store_authenticity import is_precise_phone, is_precise_shop_number  # noqa: E402

from scrapers.openrice_api import (  # noqa: E402
    load_api_cache as load_openrice_api_cache,
    scrape_openrice_api_rows,
)
from store_channels.http_util import afetch_text, normalize_phone, shared_http  # noqa: E402
from store_channels.mall_match import build_registry_index, match_mall  # noqa: E402
from store_channels.offer_emit import build_store_offer, filter_authentic  # noqa: E402

SEED_PATH = ROOT / "data" / "strata_openrice_seed.json"
CACHE_PATH = ROOT / "data" / "cache" / "strata_openrice_offers.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
SOURCE_NAME = "strata_mall_openrice"

# Priority strata / dense neighbourhood malls in the 74-mall registry.
STRATA_MALLS = (
    "葵涌廣場",
    "大埔廣場",
    "西九龍中心",
    "中環街市",
    "OP Mall 海之戀商場",
    "合和商場",
    "利東街",
    "碧海藍天商場",
    "數碼港商場",
    "赤柱廣場",
    "置地廣場",
    "K11 MUSEA",
    "愉景灣北商場 DB North Plaza",
)

_PROMO_RE = re.compile(
    r"(外賣|下午茶|折扣|優惠|減\$|滿\$|\%|第二件|套餐|放題|半價|現金券|會員)"
)
_PHONE_RE = re.compile(r"(?:\+?852[-\s]?)?(\d{4}\s*-?\s*\d{4})")
_SHOP_RE = re.compile(
    r"(?:Shop\s*)?([A-Za-z]?\d+[A-Za-z0-9\-/,]*)\s*(?:號舖|舖|鋪)",
    re.I,
)
_FLOOR_RE = re.compile(
    r"((?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:/F|樓|層)|地下|地庫|平台|美食廣場)",
    re.I,
)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[openrice] fail load {path}: {exc}")
        return None


def load_registry() -> list[dict]:
    payload = _load_json(REGISTRY_PATH) or {}
    return list(payload.get("malls") or []) if isinstance(payload, dict) else []


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:p|div|li|tr|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"[ \t]+", " ", text))


def parse_openrice_listing(html: str, *, mall_hint: str, source_url: str) -> list[dict[str, Any]]:
    """Best-effort extraction from OpenRice search/list HTML."""
    text = _strip_html(html)
    rows: list[dict[str, Any]] = []
    # Split on restaurant-like blocks containing a phone + 舖
    chunks = re.split(r"\n{2,}", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 40 or len(chunk) > 800:
            continue
        if mall_hint and mall_hint not in chunk and not re.search(re.escape(mall_hint[:4]), chunk):
            # Still allow if shop + phone present; mall matched later via address.
            pass
        phone_m = _PHONE_RE.search(chunk)
        shop_m = _SHOP_RE.search(chunk)
        floor_m = _FLOOR_RE.search(chunk)
        if not (phone_m and shop_m and floor_m):
            continue
        if not _PROMO_RE.search(chunk):
            # Require promo-like wording for this channel; otherwise seed handles evergreen.
            continue
        # Store name: first non-empty short line or quoted
        store = ""
        qm = re.search(r"[「『]([^」』]{2,40})[」』]", chunk)
        if qm:
            store = qm.group(1).strip()
        else:
            for line in chunk.splitlines():
                line = line.strip()
                if 2 <= len(line) <= 40 and not _PHONE_RE.search(line):
                    store = line
                    break
        if not store:
            continue
        rows.append(
            {
                "store_name": store,
                "floor": floor_m.group(1).strip(),
                "shop_number": shop_m.group(1).replace("，", ",").strip(),
                "phone": normalize_phone(phone_m.group(1)),
                "details": chunk[:400],
                "title": f"{store}｜OpenRice 門市／外賣優惠",
                "mall_hint": mall_hint,
                "address": chunk[:180],
                "source_url": source_url,
                "is_evergreen": False,
            }
        )
    return rows


async def fetch_openrice_for_mall(mall_name: str) -> list[dict[str, Any]]:
    url = f"https://www.openrice.com/zh/hongkong/restaurants?whatwhere={quote(mall_name)}"
    try:
        html = await afetch_text(url, timeout=45)
    except Exception as exc:  # noqa: BLE001
        print(f"[openrice] fetch fail {mall_name}: {exc}")
        return []
    rows = parse_openrice_listing(html, mall_hint=mall_name, source_url=url)
    print(f"[openrice] {mall_name} live_candidates={len(rows)}")
    return rows


def seed_rows() -> list[dict[str, Any]]:
    payload = _load_json(SEED_PATH)
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [r for r in (payload.get("stores") or payload.get("offers") or []) if isinstance(r, dict)]
    return []


def row_to_offer(row: dict[str, Any], registry: list[dict]) -> dict[str, Any] | None:
    if row.get("enabled") is False:
        return None
    index = build_registry_index(registry)
    hint = str(row.get("mall_hint") or row.get("mall_name") or "").strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=hint, address=address or hint)
    if not hit:
        return None
    store = str(row.get("store_name") or "").strip()
    floor = str(row.get("floor") or "").strip()
    shop = str(row.get("shop_number") or "").strip()
    phone = normalize_phone(str(row.get("phone") or ""))
    details = str(row.get("details") or row.get("offer_text") or "").strip()
    title = str(row.get("title") or "").strip() or f"{store}｜民生商場小店／美食優惠"
    source_url = str(row.get("source_url") or "").strip()
    if not source_url:
        return None
    if not (store and floor and is_precise_shop_number(shop) and is_precise_phone(phone) and details):
        return None
    if not _PROMO_RE.search(details) and not row.get("is_evergreen"):
        return None
    start = str(row.get("start_date") or "").strip() or None
    end = str(row.get("expiry_date") or "").strip() or None
    return build_store_offer(
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
        start_date=start,
        expiry_date=end,
        is_evergreen=bool(row.get("is_evergreen", True if not start else False)),
    )


def _load_verified_offer_cache() -> list[dict[str, Any]]:
    payload = _load_json(CACHE_PATH)
    if isinstance(payload, dict):
        return [o for o in (payload.get("offers") or []) if isinstance(o, dict)]
    return []


async def scrape_strata_openrice_offers(
    *,
    live: bool = True,
    malls: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry()
    targets = malls or STRATA_MALLS
    rows = seed_rows()
    live_ok = False

    if live:
        # 1) Prefer internal JSON API
        try:
            api_rows = await scrape_openrice_api_rows(targets)
            if api_rows:
                rows.extend(api_rows)
                live_ok = True
                print(f"[openrice] using live JSON API rows={len(api_rows)}")
            else:
                print("[openrice] JSON API empty → HTML fallback")
        except Exception as exc:  # noqa: BLE001
            print(f"[openrice] JSON API error → HTML fallback: {exc}")

        # 2) HTML listing (legacy) if API yielded nothing
        if not live_ok:
            live_groups = await asyncio.gather(*(fetch_openrice_for_mall(mall) for mall in targets))
            html_n = 0
            for group in live_groups:
                html_n += len(group)
                rows.extend(group)
            if html_n:
                live_ok = True
                print(f"[openrice] using HTML rows={html_n}")

        # 3) Verified API/row cache if both live paths failed
        if not live_ok:
            cached_rows = load_openrice_api_cache()
            if cached_rows:
                rows.extend(cached_rows)
                print(f"[openrice] degraded to API row cache rows={len(cached_rows)}")
            else:
                print("[openrice] no live data; seeds + prior offer cache only")

    offers: list[dict[str, Any]] = []
    for row in rows:
        offer = row_to_offer(row, registry)
        if offer:
            offers.append(offer)
    kept = filter_authentic(offers, label="openrice")

    if kept:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"offers": kept}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[openrice] authentic_offers={len(kept)} (from rows={len(rows)})")
        return kept

    # Hard degrade: previous validated offers so pipeline never goes empty
    cached_offers = _load_verified_offer_cache()
    if cached_offers:
        print(f"[openrice] fallback verified offer cache offers={len(cached_offers)}")
        return cached_offers
    print(f"[openrice] authentic_offers=0 (from rows={len(rows)})")
    return kept


def main() -> int:
    async def _run() -> None:
        async with shared_http():
            await scrape_strata_openrice_offers(live=True)

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
