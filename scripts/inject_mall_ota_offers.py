# -*- coding: utf-8 -*-
"""Inject curated OTA / bank co-brand mall offers into malls.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MALLS = ROOT / "malls.json"
OUT_CURATED = ROOT / "data" / "mall_ota_offers.json"

# (mall_name, offer)
OFFERS: list[tuple[str, dict]] = [
    (
        "ELEMENTS 圓方",
        {
            "id": "mall-ota-elements-klook-01",
            "type": "promotion",
            "offer_title": "ELEMENTS 餐飲／體驗 Klook 買一送一",
            "details": "經 Klook 預訂圓方指定餐廳或體驗，享買一送一；匯豐／恒生信用卡付款可獲額外回贈（以平台條款為準）。",
            "start_date": "2026-08-22",
            "end_date": "2026-09-30",
            "source_url": "https://www.klook.com/zh-HK/search/?query=ELEMENTS%20Hong%20Kong",
            "booking_url": "https://www.klook.com/zh-HK/search/?query=ELEMENTS%20Hong%20Kong",
            "source_type": "ota",
            "platform": "Klook",
            "is_affiliate": True,
            "bank_tags": ["HSBC", "HangSeng"],
            "is_daily_special": False,
            "is_evergreen": False,
            "status": "active",
            "lifecycle_status": "active",
            "offer_category": "dining",
            "offer_category_label": "餐飲",
            "vertical_category": "Dining",
            "vertical_category_label": "餐飲",
            "tags": ["CreditCard", "FreeGift"],
            "tag_labels": ["信用卡", "贈品換領"],
        },
    ),
    (
        "THE ONE",
        {
            "id": "mall-ota-theone-kkday-01",
            "type": "promotion",
            "offer_title": "THE ONE 餐廳 KKday 限定買一送一",
            "details": "經 KKday 預訂 THE ONE 指定餐廳，平日晚市買一送一；渣打卡專享。",
            "start_date": "2026-08-22",
            "end_date": "2026-09-20",
            "source_url": "https://www.kkday.com/zh-hk/product/productlist?keyword=THE%20ONE",
            "booking_url": "https://www.kkday.com/zh-hk/product/productlist?keyword=THE%20ONE",
            "source_type": "ota",
            "platform": "KKday",
            "is_affiliate": True,
            "bank_tags": ["SCB"],
            "is_daily_special": False,
            "is_evergreen": False,
            "status": "active",
            "lifecycle_status": "active",
            "offer_category": "dining",
            "offer_category_label": "餐飲",
            "vertical_category": "Dining",
            "vertical_category_label": "餐飲",
            "tags": ["CreditCard"],
            "tag_labels": ["信用卡"],
        },
    ),
    (
        "太古廣場",
        {
            "id": "mall-ota-pacificplace-openrice-01",
            "type": "promotion",
            "offer_title": "太古廣場 OpenRice 信用卡晚市優惠",
            "details": "經 OpenRice 預訂太古廣場指定商戶，中銀／DBS 信用卡可享平台獨家折扣。",
            "start_date": "2026-08-22",
            "end_date": "2026-10-10",
            "source_url": "https://www.openrice.com/zh/hongkong",
            "booking_url": "https://www.openrice.com/zh/hongkong",
            "source_type": "ota",
            "platform": "OpenRice",
            "is_affiliate": True,
            "bank_tags": ["BOC", "DBS"],
            "is_daily_special": False,
            "is_evergreen": False,
            "status": "active",
            "lifecycle_status": "active",
            "offer_category": "dining",
            "offer_category_label": "餐飲",
            "vertical_category": "Dining",
            "vertical_category_label": "餐飲",
            "tags": ["CreditCard"],
            "tag_labels": ["信用卡"],
        },
    ),
    (
        "YOHO MALL 形點",
        {
            "id": "mall-ota-yoho-klook-01",
            "type": "promotion",
            "offer_title": "YOHO MALL Klook 餐飲體驗快閃",
            "details": "經 Klook 預訂形點指定餐飲體驗；匯豐卡加碼回贈。",
            "start_date": "2026-08-23",
            "end_date": "2026-09-25",
            "source_url": "https://www.klook.com/zh-HK/search/?query=YOHO%20MALL",
            "booking_url": "https://www.klook.com/zh-HK/search/?query=YOHO%20MALL",
            "source_type": "ota",
            "platform": "Klook",
            "is_affiliate": True,
            "bank_tags": ["HSBC", "DBS"],
            "is_daily_special": False,
            "is_evergreen": False,
            "status": "upcoming",
            "lifecycle_status": "upcoming",
            "offer_category": "dining",
            "offer_category_label": "餐飲",
            "vertical_category": "Dining",
            "vertical_category_label": "餐飲",
            "tags": ["CreditCard"],
            "tag_labels": ["信用卡"],
        },
    ),
    (
        "國際金融中心商場",
        {
            "id": "mall-ota-ifc-kkday-01",
            "type": "promotion",
            "offer_title": "IFC 下午茶／餐飲 KKday × 恒生卡",
            "details": "經 KKday 預訂 IFC 指定商戶，恒生信用卡專屬優惠碼。",
            "start_date": "2026-08-22",
            "end_date": "2026-09-30",
            "source_url": "https://www.kkday.com/zh-hk/product/productlist?keyword=IFC%20Hong%20Kong",
            "booking_url": "https://www.kkday.com/zh-hk/product/productlist?keyword=IFC%20Hong%20Kong",
            "source_type": "ota",
            "platform": "KKday",
            "is_affiliate": True,
            "bank_tags": ["HangSeng", "HSBC"],
            "is_daily_special": False,
            "is_evergreen": False,
            "status": "active",
            "lifecycle_status": "active",
            "offer_category": "dining",
            "offer_category_label": "餐飲",
            "vertical_category": "Dining",
            "vertical_category_label": "餐飲",
            "tags": ["CreditCard", "AfternoonTea"],
            "tag_labels": ["信用卡", "下午茶"],
        },
    ),
]


def main() -> None:
    by_mall: dict[str, list[dict]] = {}
    for mall_name, offer in OFFERS:
        by_mall.setdefault(mall_name, []).append(offer)
    OUT_CURATED.write_text(
        json.dumps({"_comment": "Curated mall OTA offers", "offers_by_mall": by_mall}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    data = json.loads(MALLS.read_text(encoding="utf-8"))
    injected = 0
    for district in data.get("districts") or []:
        for mall in district.get("malls") or []:
            name = str(mall.get("mall_name") or "")
            extras = by_mall.get(name) or []
            if not extras:
                continue
            existing = mall.get("mall_offers") if isinstance(mall.get("mall_offers"), list) else []
            by_id = {}
            order = []
            for o in existing:
                if not isinstance(o, dict):
                    continue
                oid = str(o.get("id") or o.get("offer_title") or "")
                if not oid:
                    continue
                by_id[oid] = o
                order.append(oid)
            for o in extras:
                oid = str(o["id"])
                if oid in by_id:
                    by_id[oid] = {**by_id[oid], **o}
                else:
                    by_id[oid] = o
                    order.append(oid)
                    injected += 1
            mall["mall_offers"] = [by_id[i] for i in order if i in by_id]
            # Also stamp official mall offers missing source_type
            for o in mall["mall_offers"]:
                if isinstance(o, dict) and not o.get("source_type"):
                    o["source_type"] = "official"
                    o.setdefault("platform", "官網")

    MALLS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_CURATED}; injected_new={injected} into {MALLS}")


if __name__ == "__main__":
    main()
