"""Maintain HK mall data: promo URLs, evergreen overrides, chain presence."""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

BODY_SELECTORS = {
    "card": "body",
    "title": "h1, h2",
    "discount_info": "main, body",
    "start_date": ".no-date",
    "expiry_date": ".no-date",
    "link": "a[href]",
    "image": "img",
    "daily_special": ".daily-special",
}

# Prefer promotions / parking / events subpages over homepages or example.com stubs.
SOURCE_FIXES = {
    ("中西區", "信德中心"): {
        "url": "https://www.shuntakgroup.com/en/business/property/portfolio/1045",
        "mall_url": "https://www.shuntakgroup.com/",
    },
    ("南區", "香港仔中心商場"): {
        "url": "http://www.aberdeencentre.com.hk/",
        "mall_url": "http://www.aberdeencentre.com.hk/",
    },
    ("屯門區", "屯門時代廣場"): {
        "url": "https://www.trendplazahk.com.hk/tc/promotions.html",
        "mall_url": "https://www.trendplazahk.com.hk/",
    },
    ("荃灣區", "OP Mall 海之戀商場"): {
        "url": "https://www.ckah.com/zh-hant/hong-kong-properties/leasing/817",
        "mall_url": "https://www.ckah.com/zh-hant/hong-kong-properties/leasing/817",
    },
}

NEW_OVERRIDES = [
    {
        "mall_name": "新都城中心",
        "district": "西貢區",
        "title": "新都城中心免費泊車優惠",
        "details": "只限各期停車場私家車時租車位；入車時段約 07:00–22:00。即日電子消費滿港幣 $200／$400 可享 1／2 小時免費泊車。詳情以官方泊車頁及各期禮賓部為準。",
        "source_url": "https://www.metrocity1.com/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "海港城",
        "district": "油尖旺區",
        "title": "海港城 VIC Club 會員禮遇",
        "details": "VIC Club 會員於海港城消費一般每港幣 $1 可賺 1 分（更高級別可賺 1.5／2 分），並可享級別相關額外泊車時數等禮遇。免費泊車換領細則以官方條款及場內公告為準。",
        "source_url": "https://www.harbourcity.com.hk/tc/vic_club/vic-club-tier/",
        "is_evergreen": True,
    },
    {
        "mall_name": "屯門時代廣場",
        "district": "屯門區",
        "title": "屯門時代廣場泊車及 H·COINS 會員",
        "details": "地庫停車場時租：平日（公眾假期除外）約 HK$21／小時，週末及公眾假期約 HK$29／小時；另設平日日泊及夜泊。商場為 H·COINS 參與物業，電子消費可按計劃儲分換獎賞。最新活動見官方推廣頁。",
        "source_url": "https://www.trendplazahk.com.hk/tc/get-here.html?s=parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "香港仔中心商場",
        "district": "南區",
        "title": "ac／香港仔中心商場官方資訊",
        "details": "商場（現稱 ac）官方網站刊載最新推廣與商戶活動；泊車條款請以場內公告為準。",
        "source_url": "http://www.aberdeencentre.com.hk/",
        "is_evergreen": True,
    },
    {
        "mall_name": "信德中心",
        "district": "中西區",
        "title": "信德中心物業及商場概覽",
        "details": "信德中心為信德集團旗下綜合零售及寫字樓物業，設約 270 個泊車位；官方物業組合頁刊載地址與設施概覽。商場推廣主要經官方渠道發佈。",
        "source_url": "https://www.shuntakgroup.com/en/business/property/portfolio/1045",
        "is_evergreen": True,
    },
    {
        "mall_name": "OP Mall 海之戀商場",
        "district": "荃灣區",
        "title": "OP Mall 海之戀商場官方資訊",
        "details": "長江實業官方租賃頁介紹海之戀商場零售組合與大型停車場；最新會員禮遇及泊車推廣以官方 App／場內公告為準。",
        "source_url": "https://www.ckah.com/zh-hant/hong-kong-properties/leasing/817",
        "is_evergreen": True,
    },
    {
        "mall_name": "新港城中心 MOSTown",
        "district": "沙田區",
        "title": "MOSTown／H·COINS 會員積分",
        "details": "新港城中心為 H·COINS 參與商場；於參與商戶以電子支付消費，一般每港幣 $1 可賺 1 H COIN，並可兌換電子優惠券等獎賞。",
        "source_url": "https://www.hcoins.com.hk/",
        "is_evergreen": True,
    },
    {
        "mall_name": "沙田中心",
        "district": "沙田區",
        "title": "沙田中心／H·COINS 會員積分計劃",
        "details": "沙田中心為 H·COINS 參與商場；會員於參與商戶電子消費一般每港幣 $1 可賺 1 H COIN，並可兌換獎賞。",
        "source_url": "https://www.hcoins.com.hk/",
        "is_evergreen": True,
    },
]

NEW_CHAINS = [
    {
        "chain_id": "starbucks_rewards",
        "store_name": "星巴克",
        "title": "Starbucks Rewards™ 獎賞計劃",
        "details": "登記並以已啟動的香港／澳門星巴克卡於參與分店消費，一般每滿港幣／澳門幣 $20 可獲一粒星星；按星星累積晉升會員級別並換領獎賞。詳情以官方 Starbucks Rewards 條款為準。",
        "source_url": "https://www.starbucks.com.hk/zh_HK/questions-about-starbucks-rewards",
        "is_evergreen": True,
        "phone": "2970 6060",
    },
    {
        "chain_id": "cafe_de_coral_club100",
        "store_name": "大家樂",
        "title": "大家樂 Club 100 會員計劃",
        "details": "透過大家樂官方 App 登記 Club 100，可享用會員限定優惠、儲分／樂賞印及手機點餐等禮遇；迎新及當期優惠以 App 公告為準。",
        "source_url": "https://www.club100.hk/",
        "is_evergreen": True,
        "phone": "2750 3388",
    },
    {
        "chain_id": "ok_stamp_it",
        "store_name": "OK便利店",
        "title": "OK Stamp It 印花獎賞計劃",
        "details": "下載官方 OK Stamp It App 登記會員後，可於 OK 便利店儲電子印花、換領獎賞及享用會員專屬優惠；會籍計劃屬持續營運。",
        "source_url": "https://www.circlek.hk/",
        "is_evergreen": True,
        "phone": "2299 1888",
    },
    {
        "chain_id": "hcoins",
        "store_name": "H·COINS",
        "title": "H·COINS 綜合會員計劃",
        "details": "於 H·COINS 參與恒基物業商戶以電子支付消費，一般每港幣 $1 可賺 1 H COIN，並可兌換電子優惠券、H Dollars 等獎賞。",
        "source_url": "https://www.hcoins.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
]

NEW_PRESENCE = [
    {"chain_id": "starbucks_rewards", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "太古廣場", "district": "中西區", "floor": "L1", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "朗豪坊", "district": "油尖旺區", "floor": "L4", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "YOHO MALL 形點", "district": "元朗區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "太古城中心", "district": "東區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "又一城", "district": "九龍城區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "新都會廣場", "district": "葵青區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "東港城", "district": "西貢區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "屯門市廣場", "district": "屯門區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "新港城中心 MOSTown", "district": "沙田區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "OP Mall 海之戀商場", "district": "荃灣區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "starbucks_rewards", "mall_name": "元朗廣場", "district": "元朗區", "floor": "", "shop_number": "星巴克咖啡"},
    {"chain_id": "cafe_de_coral_club100", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "大家樂"},
    {"chain_id": "cafe_de_coral_club100", "mall_name": "太古城中心", "district": "東區", "floor": "", "shop_number": "大家樂"},
    {"chain_id": "cafe_de_coral_club100", "mall_name": "樂富廣場", "district": "九龍城區", "floor": "", "shop_number": "大家樂"},
    {"chain_id": "cafe_de_coral_club100", "mall_name": "黃大仙中心", "district": "黃大仙區", "floor": "", "shop_number": "大家樂"},
    {"chain_id": "cafe_de_coral_club100", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "大家樂"},
    {"chain_id": "ok_stamp_it", "mall_name": "香港仔中心商場", "district": "南區", "floor": "", "shop_number": "OK便利店"},
    {"chain_id": "hcoins", "mall_name": "新港城中心 MOSTown", "district": "沙田區", "floor": "全場參與商戶", "shop_number": "H·COINS"},
    {"chain_id": "hcoins", "mall_name": "沙田中心", "district": "沙田區", "floor": "全場參與商戶", "shop_number": "H·COINS"},
    {"chain_id": "hcoins", "mall_name": "屯門時代廣場", "district": "屯門區", "floor": "全場參與商戶", "shop_number": "H·COINS"},
    {"chain_id": "hcoins", "mall_name": "新都城中心", "district": "西貢區", "floor": "全場參與商戶", "shop_number": "H·COINS"},
    # Extra yuu / moneyback / mcdonalds coverage for previously thin malls
    {"chain_id": "yuu", "mall_name": "東港城", "district": "西貢區", "floor": "", "shop_number": "惠康超級市場"},
    {"chain_id": "yuu", "mall_name": "將軍澳中心 Park Central", "district": "西貢區", "floor": "", "shop_number": "惠康超級市場"},
    {"chain_id": "moneyback", "mall_name": "荷里活廣場", "district": "黃大仙區", "floor": "", "shop_number": "百佳超級市場"},
    {"chain_id": "moneyback", "mall_name": "德福廣場", "district": "觀塘區", "floor": "", "shop_number": "百佳超級市場"},
    {"chain_id": "mcdonalds_app", "mall_name": "MegaBox", "district": "觀塘區", "floor": "", "shop_number": "麥當勞餐廳"},
    {"chain_id": "mcdonalds_app", "mall_name": "PopCorn", "district": "西貢區", "floor": "", "shop_number": "麥當勞餐廳"},
]


def slug_id(name: str, suffix: str) -> str:
    ascii_part = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-").lower()
    ascii_part = ascii_part.encode("ascii", "ignore").decode().strip("-") or "mall"
    return f"{ascii_part}-{suffix}"


def main() -> int:
    registry_path = DATA / "malls-registry.json"
    sources_path = DATA / "sources.json"
    overrides_path = DATA / "mall_overrides.json"
    chains_path = DATA / "chain_store_offers.json"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    malls = {(m["district"], m["mall_name"]): m for m in registry["malls"]}

    # Update registry mall_url for newly found official sites.
    for key, fix in SOURCE_FIXES.items():
        if key in malls and fix.get("mall_url"):
            malls[key]["mall_url"] = fix["mall_url"]
    registry["malls"] = sorted(malls.values(), key=lambda m: (m["district"], m["mall_name"]))
    # rebuild by_district if present
    if "by_district" in registry:
        by_district: dict[str, list] = {}
        for mall in registry["malls"]:
            by_district.setdefault(mall["district"], []).append(mall)
        registry["by_district"] = by_district
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Patch sources URLs away from example.com / homepages where possible.
    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
    sources = sources_doc["sources"]
    existing_ids = {s["id"] for s in sources}
    existing_urls = {s.get("url") for s in sources}
    patched = 0
    for source in sources:
        mall = source.get("mall") or {}
        key = (mall.get("district"), mall.get("mall_name"))
        if key not in SOURCE_FIXES:
            continue
        fix = SOURCE_FIXES[key]
        if source.get("url") != fix["url"]:
            source["url"] = fix["url"]
            patched += 1
        if fix.get("mall_url"):
            source["mall"]["mall_url"] = fix["mall_url"]
        comment = source.get("_comment", "")
        if "example.com" in comment or "mall_url 為 null" in comment:
            source["_comment"] = "已改為官方物業／推廣子頁；常青政策見 mall_overrides。"

    # Merge overrides.
    overrides_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
    existing_ov = {
        (o["district"], o["mall_name"], o["source_url"]): o
        for o in overrides_doc.get("overrides", [])
    }
    for item in NEW_OVERRIDES:
        if (item["district"], item["mall_name"]) not in malls:
            raise SystemExit(f"unknown mall for override: {item}")
        existing_ov[(item["district"], item["mall_name"], item["source_url"])] = item
    overrides_doc["overrides"] = sorted(
        existing_ov.values(), key=lambda o: (o["district"], o["mall_name"], o["title"])
    )
    overrides_path.write_text(
        json.dumps(overrides_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Ensure evergreen sources exist for new overrides.
    insert_at = next(
        (i for i, s in enumerate(sources) if s["id"] in {"hk-mall-template", "skyscanner-hk"}),
        len(sources),
    )
    inserted = 0
    for item in NEW_OVERRIDES:
        if item["source_url"] in existing_urls:
            continue
        mall = malls[(item["district"], item["mall_name"])]
        src = {
            "id": slug_id(item["mall_name"], "evergreen-policy"),
            "enabled": True,
            "_comment": "官方長期政策／會員頁；is_evergreen 保留常態優惠。",
            "target": "malls",
            "name": item["title"],
            "url": item["source_url"],
            "category": "商場優惠",
            "offer_type": "mall",
            "district": item["district"],
            "brand_name": item["mall_name"],
            "is_daily_special": False,
            "is_evergreen": True,
            "title_override": item["title"],
            "details": item["details"],
            "mall": {
                "mall_name": mall["mall_name"],
                "district": mall["district"],
                "address": mall.get("address"),
                "phone": mall.get("phone"),
                "network_phone": mall.get("network_phone"),
                "mall_url": mall.get("mall_url"),
            },
            "selectors": BODY_SELECTORS,
        }
        base = src["id"]
        n = 2
        while src["id"] in existing_ids:
            src["id"] = f"{base}-{n}"
            n += 1
        existing_ids.add(src["id"])
        existing_urls.add(src["url"])
        sources.insert(insert_at, src)
        insert_at += 1
        inserted += 1

    sources_doc["sources"] = sources
    sources_path.write_text(
        json.dumps(sources_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Expand chain store offers.
    chains_doc = json.loads(chains_path.read_text(encoding="utf-8"))
    chain_by_id = {c["chain_id"]: c for c in chains_doc.get("chains", [])}
    for chain in NEW_CHAINS:
        chain_by_id[chain["chain_id"]] = chain
    chains_doc["chains"] = list(chain_by_id.values())

    presence_keys = {
        (p["chain_id"], p["district"], p["mall_name"]) for p in chains_doc.get("presence", [])
    }
    for row in NEW_PRESENCE:
        key = (row["chain_id"], row["district"], row["mall_name"])
        if (row["district"], row["mall_name"]) not in malls:
            raise SystemExit(f"unknown mall for presence: {row}")
        if key not in presence_keys:
            chains_doc.setdefault("presence", []).append(row)
            presence_keys.add(key)
    chains_path.write_text(
        json.dumps(chains_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"patched sources: {patched}; overrides: {len(overrides_doc['overrides'])}; "
        f"inserted sources: {inserted}; chains: {len(chains_doc['chains'])}; "
        f"presence: {len(chains_doc['presence'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
