# -*- coding: utf-8 -*-
"""Merge mall_official_offers.json + refresh OTA OpenRice/Klook/KKday URLs into malls.json."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MALLS = ROOT / "malls.json"
OFFICIAL = ROOT / "data" / "mall_official_offers.json"
OTA = ROOT / "data" / "mall_ota_offers.json"

PACIFIC_HAPPENINGS = "https://www.pacificplace.com.hk/zh-hk/entertainment/happenings"
PACIFIC_HOME = "https://www.pacificplace.com.hk/zh-hk"


def openrice_where(mall_name: str) -> str:
    return f"https://www.openrice.com/zh/hongkong/restaurants?where={quote(mall_name)}"


def upsert_offers(existing: list, extras: list) -> list:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for o in existing:
        if not isinstance(o, dict):
            continue
        oid = str(o.get("id") or o.get("offer_title") or "")
        if not oid:
            continue
        by_id[oid] = o
        order.append(oid)
    for o in extras:
        oid = str(o.get("id") or "")
        if not oid:
            continue
        if oid in by_id:
            by_id[oid] = {**by_id[oid], **o}
        else:
            by_id[oid] = o
            order.append(oid)
    return [by_id[i] for i in order if i in by_id]


def fix_existing_offer(mall_name: str, offer: dict) -> dict:
    o = dict(offer)
    platform = str(o.get("platform") or "").lower()
    source = str(o.get("source_type") or "").lower()
    url = str(o.get("booking_url") or o.get("source_url") or "")

    if platform == "openrice" or "openrice.com" in url:
        fixed = openrice_where(mall_name)
        o["booking_url"] = fixed
        o["source_url"] = fixed
        o["platform"] = "OpenRice"
        o["source_type"] = o.get("source_type") or "ota"

    if mall_name == "太古廣場":
        # Replace expired campaign deep links with happenings hub
        if "pacificplace.com.hk" in url and (
            "redemption" in url
            or "pp-summer" in url
            or "/happenings/" in url and url.rstrip("/").count("/") > 5
        ):
            o["source_url"] = PACIFIC_HAPPENINGS
            o["booking_url"] = PACIFIC_HAPPENINGS
            o.setdefault("source_type", "official")
            o.setdefault("platform", "官網")

    if source in {"", "official"} and not o.get("platform"):
        o["platform"] = "官網"
        o["source_type"] = "official"

    return o


def main() -> None:
    official = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    ota = json.loads(OTA.read_text(encoding="utf-8")) if OTA.exists() else {}
    hubs = official.get("hubs") or {}
    official_by = official.get("offers_by_mall") or {}
    ota_by = ota.get("offers_by_mall") or {}

    # Refresh OpenRice OTA curated rows to where= search
    for mall_name, offers in list(ota_by.items()):
        for offer in offers:
            if str(offer.get("platform") or "").lower() == "openrice":
                fixed = openrice_where(mall_name)
                offer["booking_url"] = fixed
                offer["source_url"] = fixed
    OTA.write_text(
        json.dumps({"_comment": ota.get("_comment") or "Curated mall OTA offers", "offers_by_mall": ota_by}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    data = json.loads(MALLS.read_text(encoding="utf-8"))
    patched = 0
    for district in data.get("districts") or []:
        for mall in district.get("malls") or []:
            name = str(mall.get("mall_name") or "")
            offers = [fix_existing_offer(name, o) for o in (mall.get("mall_offers") or []) if isinstance(o, dict)]
            extras: list[dict] = []
            extras.extend(official_by.get(name) or [])
            extras.extend(ota_by.get(name) or [])
            before = json.dumps(offers, ensure_ascii=False)
            offers = upsert_offers(offers, extras)
            # Stamp hub metadata for frontend fallback
            hub = hubs.get(name)
            if hub:
                mall["official_home"] = hub.get("home")
                mall["official_happenings"] = hub.get("happenings")
            mall["mall_offers"] = offers
            if json.dumps(offers, ensure_ascii=False) != before or hub:
                patched += 1

    data["mall_official_hubs"] = hubs
    MALLS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched_malls={patched} hubs={len(hubs)} wrote {MALLS}")


if __name__ == "__main__":
    main()
