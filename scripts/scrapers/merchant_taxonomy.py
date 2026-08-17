# -*- coding: utf-8 -*-
"""Merchant taxonomy — classify stores as independent vs chain."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHAIN_PATH = ROOT / "data" / "chain_store_offers.json"

MERCHANT_INDEPENDENT = "independent"
MERCHANT_CHAIN = "chain"

# National / mega retail & F&B groups commonly present in HK malls.
_MEGA_CHAIN_RE = re.compile(
    r"("
    r"屈臣|萬寧|Watsons|Mannings|UNIQLO|無印|MUJI|星巴克|Starbucks|"
    r"AEON|Living\s*PLAZA|豐澤|Fortress|7-?Eleven|OK\s*便利店|"
    r"譚仔|大家樂|百佳|Broadway|百老匯|麥當勞|McDonald|莎莎|Sasa|"
    r"吉野家|必勝客|Pizza\s*Hut|一田|YATA|city'?s?uper|Market\s*Place|"
    r"\bGU\b|鴻福堂|奇華|元氣|DON\s*DON\s*DONKI|Donki|驚安|"
    r"A-?1\s*Bakery|東海堂|周生生|周大福|六福|點點綠|"
    r"H&M|ZARA|Nike|Adidas|Apple\b|Sony|Samsung|KFC|肯德基|"
    r"美心|太興|翠華|茶木|Pacific\s*Coffee|BALENO|Giordano|G2000|"
    r"Colourmix|JHC|日本城|千色店|log-on|Log-on|LOG-ON|"
    r"Chatime|日出茶太|貢茶|CoCo|都可|一芳|可不可|CHAGEE|霸王茶姬|"
    r"PizzaExpress|牛角|榮華|蛋撻王|惠康|Wellcome|Fusion|"
    r"IKEA|宜家|Toys.?R.?Us|LEGO|迪士尼|"
    r"HSBC|恒生|中銀|渣打|花旗|銀行"
    r")",
    re.I,
)

_chain_name_cache: set[str] | None = None


def load_chain_store_names(path: Path | None = None) -> set[str]:
    global _chain_name_cache
    if _chain_name_cache is not None and path is None:
        return _chain_name_cache
    target = path or CHAIN_PATH
    names: set[str] = set()
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for row in payload.get("presence") or []:
            n = str(row.get("store_name") or "").strip()
            if n:
                names.add(n)
        for row in payload.get("chains") or []:
            n = str(row.get("store_name") or "").strip()
            if n:
                names.add(n)
    if path is None:
        _chain_name_cache = names
    return names


def is_chain_store(store_name: str, *, chain_names: set[str] | None = None) -> bool:
    name = str(store_name or "").strip()
    if not name:
        return False
    names = chain_names if chain_names is not None else load_chain_store_names()
    if name in names:
        return True
    # Substring / alias hit against known presence names (short names only).
    lowered = name.casefold()
    for known in names:
        k = known.casefold()
        if len(k) >= 2 and (k in lowered or lowered in k):
            return True
    return bool(_MEGA_CHAIN_RE.search(name))


def classify_merchant_type(
    store_name: str,
    *,
    chain_names: set[str] | None = None,
    source_name: str | None = None,
    quota_fill: bool = False,
) -> str:
    """Return ``independent`` or ``chain``."""
    src = str(source_name or "").strip()
    if quota_fill or src in {
        "small_shop_scraper",
        "food_court_scanner",
        "community_aggregator",
        "social_media_parser",
        "strata_mall_openrice",
    }:
        # Indie channels / quota fills count toward the 70% independent bucket.
        # Still hard-label mega chains as chain when the store name is unmistakably chain
        # and the source is not an explicit indie fill.
        if not quota_fill and is_chain_store(store_name, chain_names=chain_names):
            return MERCHANT_CHAIN
        return MERCHANT_INDEPENDENT
    if is_chain_store(store_name, chain_names=chain_names):
        return MERCHANT_CHAIN
    if src in {
        "chain_store_offers",
        "enrich_flagship_phones",
        "payment_join",
        "payment_join:payme",
    } or src.startswith("payment_join:"):
        return MERCHANT_CHAIN
    return MERCHANT_INDEPENDENT


def annotate_merchant_types(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chain_names = load_chain_store_names()
    out: list[dict[str, Any]] = []
    for raw in offers:
        if not isinstance(raw, dict):
            continue
        offer = dict(raw)
        if str(offer.get("offer_type") or offer.get("type") or "") == "store":
            existing = str(offer.get("merchant_type") or "").strip()
            # Preserve quota balancer stamps (unique-shop 70:30 deck).
            if offer.get("quota_balanced") and existing in {
                MERCHANT_INDEPENDENT,
                MERCHANT_CHAIN,
            }:
                pass
            elif offer.get("quota_fill") and existing in {
                MERCHANT_INDEPENDENT,
                MERCHANT_CHAIN,
            }:
                pass
            elif existing == MERCHANT_INDEPENDENT and str(
                offer.get("source_name") or ""
            ) == "small_shop_scraper":
                pass
            else:
                offer["merchant_type"] = classify_merchant_type(
                    str(offer.get("store_name") or ""),
                    chain_names=chain_names,
                    source_name=str(offer.get("source_name") or ""),
                    quota_fill=bool(offer.get("quota_fill")),
                )
        else:
            offer.setdefault("merchant_type", MERCHANT_CHAIN)
        out.append(offer)
    return out
