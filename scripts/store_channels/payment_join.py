"""Payment / wallet mall promo scrapers joined onto verified store pins.

Raw payment pages almost never publish floor + shop + phone together.
Therefore this channel only emits store offers when a promo can be joined to an
already authenticity-passing directory pin for the same mall + brand.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any

from store_authenticity import authenticity_failures, is_authentic_store_payload

from .brand_aliases import match_brand
from .http_util import afetch_text
from .mall_match import build_registry_index, match_mall

PAYME_OFFERS = "https://payme.hsbc.com.hk/en/offers"
ALIPAY_CANDIDATES = (
    "https://www.alipay.hk/",
    "https://render.alipay.hk/p/c/180020570000063952/index.html",
)
WECHAT_CANDIDATES = (
    "https://pay.weixin.qq.com/index.php/public/wechatpay_zh_hk",
)


def _strip(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(text)
    return re.sub(r"\n+", "\n", text)


def _parse_iso_date(value: str) -> str | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_brand_promos(html: str, *, source_url: str, title_prefix: str) -> list[dict[str, str]]:
    text = _strip(html)
    candidates: list[dict[str, str]] = []
    for block in re.split(r"\n{2,}", text):
        block = re.sub(r"\s+", " ", block).strip()
        if len(block) < 40 or len(block) > 500:
            continue
        if not re.search(r"(off|cashback|discount|\$|%|回贈|折扣|優惠|現金券)", block, re.I):
            continue
        brand = match_brand(block)
        if not brand:
            continue
        dates = re.findall(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})", block)
        start = _parse_iso_date(dates[0]) if dates else None
        end = _parse_iso_date(dates[1]) if len(dates) > 1 else None
        inferred = "0"
        if not start or not end:
            today = date.today()
            start = today.isoformat()
            end = (today + timedelta(days=30)).isoformat()
            inferred = "1"
        candidates.append(
            {
                "chain_id": brand[0],
                "store_name": brand[1],
                "title": f"{title_prefix} × {brand[1]} 專屬優惠",
                "details": block[:400],
                "start_date": start,
                "expiry_date": end,
                "source_url": source_url,
                "mall_hint": block,
                "_dates_inferred": inferred,
            }
        )
    return candidates


async def scrape_payme_promo_candidates() -> list[dict[str, str]]:
    """Best-effort extraction of merchant/mall-ish promo snippets from wallet pages."""
    candidates: list[dict[str, str]] = []
    try:
        html = await afetch_text(PAYME_OFFERS)
        found = _extract_brand_promos(html, source_url=PAYME_OFFERS, title_prefix="PayMe")
        candidates.extend(found)
        print(f"[payme] promo candidates={len(found)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[payme] scrape failed: {exc}")

    for url in ALIPAY_CANDIDATES:
        try:
            html = await afetch_text(url, timeout=30)
            found = _extract_brand_promos(html, source_url=url, title_prefix="AlipayHK")
            candidates.extend(found)
            print(f"[alipay] {url} candidates={len(found)}")
            if found:
                break
        except Exception as exc:  # noqa: BLE001
            print(f"[alipay] fail {url}: {exc}")

    for url in WECHAT_CANDIDATES:
        try:
            html = await afetch_text(url, timeout=30)
            found = _extract_brand_promos(html, source_url=url, title_prefix="WeChat Pay HK")
            candidates.extend(found)
            print(f"[wechatpay] candidates={len(found)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[wechatpay] fail {url}: {exc}")

    print(f"[payment] total promo candidates={len(candidates)}")
    return candidates


def join_promos_to_pins(
    promos: list[dict[str, str]],
    verified_pins: list[dict[str, str]],
    registry_malls: list[dict],
) -> list[dict[str, Any]]:
    """Attach promo content/dates onto matching verified directory pins."""
    index = build_registry_index(registry_malls)
    pin_index: dict[tuple[str, str], dict[str, str]] = {}
    for pin in verified_pins:
        key = (pin.get("chain_id", ""), pin.get("mall_name", ""))
        pin_index[key] = pin

    offers: list[dict[str, Any]] = []
    for promo in promos:
        # Require an explicit date window from the source text.
        if not promo.get("start_date") or not promo.get("expiry_date"):
            continue
        if promo.get("_dates_inferred") == "1":
            continue
        chain_id = promo["chain_id"]
        hit = match_mall(index, mall_hint=promo.get("mall_hint", ""), address=promo.get("mall_hint", ""))
        if not hit:
            continue
        pin = pin_index.get((chain_id, hit.mall_name))
        if not pin:
            continue
        offer = {
            "title": promo["title"],
            "category": "商場優惠",
            "offer_type": "store",
            "is_daily_special": False,
            "is_evergreen": False,
            "created_date": promo["start_date"],
            "created_at": f"{promo['start_date']}T00:00:00+08:00",
            "start_date": promo["start_date"],
            "expiry_date": promo["expiry_date"],
            "discount_info": promo["details"][:120],
            "details": promo["details"],
            "source_url": promo["source_url"],
            "image_url": None,
            "mall_name": pin["mall_name"],
            "district": pin["district"],
            "store_name": pin.get("store_name") or promo["store_name"],
            "floor": pin["floor"],
            "shop_number": pin["shop_number"],
            "phone": pin["phone"],
            "source_name": "payment_join:payme",
        }
        if is_authentic_store_payload(offer):
            offers.append(offer)
        else:
            fails = authenticity_failures(offer)
            print(f"[payme] reject join {offer['store_name']}@{offer['mall_name']}: {fails}")
    print(f"[payme] joined authentic store offers={len(offers)}")
    return offers


async def scrape_payment_joined_offers(
    verified_pins: list[dict[str, str]],
    registry_malls: list[dict],
) -> list[dict[str, Any]]:
    try:
        promos = await scrape_payme_promo_candidates()
    except Exception as exc:  # noqa: BLE001
        print(f"[payme] scrape failed: {exc}")
        return []
    return join_promos_to_pins(promos, verified_pins, registry_malls)
