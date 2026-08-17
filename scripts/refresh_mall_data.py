"""Refresh data/sources.json promo URLs and expand evergreen mall overrides."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

PROMO_URLS = {
    ("中西區", "中環街市"): "https://www.centralmarket.hk/tc/event-calendar",
    ("中西區", "信德中心"): "https://www.shuntakgroup.com/en/business/property/portfolio/1045",
    ("九龍城區", "樂富廣場"): "https://www.linkhk.com/tc/promotion/",
    ("元朗區", "+WOO 嘉湖"): "https://www.fortunemalls.com.hk/tc/promotions",
    ("元朗區", "T Town"): "https://www.linkhk.com/tc/promotion/",
    ("元朗區", "元朗廣場"): "https://www.yuenlongplaza.com/happenings/",
    ("北區", "上水匯 spot"): "https://www.ssspot.com.hk/news.aspx",
    ("北區", "上水廣場"): "https://www.landmarknorth.com.hk/",
    ("南區", "數碼港商場"): "https://connect.cyberport.hk/zh-hk/the-arcade/",
    ("南區", "赤柱廣場"): "https://www.linkhk.com/tc/promotion/",
    ("屯門區", "錦薈坊"): "https://www.k-point.com.hk/%e6%9c%80%e6%96%b0%e6%b4%bb%e5%8b%95/",
    ("東區", "康怡廣場"): "https://www.hanglungmalls.com/promotions?mall=kornhill-plaza",
    ("沙田區", "HomeSquare"): "https://www.homesquare.com.hk/zh-hant/event-promotions",
    ("沙田區", "新港城中心 MOSTown"): "https://www.mostown.com.hk/tc/",
    ("沙田區", "沙田中心"): "https://www.shatinplazacentre.com.hk/tc/promotions/index.shtml",
    ("深水埗區", "昇悅商場"): "https://ckmalls.com.hk/cht/promotion/?id=4",
    ("深水埗區", "西九龍中心"): "https://dragoncentre.com.hk/en/blogs/offers",
    ("灣仔區", "Hysan Place"): "https://www.leegardens.com.hk/car-park-promotion.aspx",
    ("灣仔區", "利東街"): "https://www.leetungavenue.com.hk/tc/",
    ("灣仔區", "合和中心"): "https://www.hopewellcentre.com/cht/hc_parking.htm",
    ("灣仔區", "合和商場"): "https://www.hopewellhill.com.hk/zh-hk/parking",
    ("荃灣區", "綠楊坊"): "https://www.lukyeunggalleria.com/tch/happenings",
    ("葵青區", "新都會廣場"): "https://www.metroplaza.com.hk/",
    ("離島區", "愉景灣北商場 DB North Plaza"): "https://www.visitdiscoverybay.com/en/whats-hot-event/176",
    ("離島區", "愉景灣廣場 DB Plaza"): "https://www.visitdiscoverybay.com/en/whats-hot-event/103",
    ("黃大仙區", "黃大仙中心"): "https://www.linkhk.com/tc/promotion/",
}

MALL_URL_UPDATES = {
    ("南區", "數碼港商場"): "https://connect.cyberport.hk/zh-hk/the-arcade/",
    ("沙田區", "沙田中心"): "https://www.shatinplazacentre.com.hk/",
    ("深水埗區", "西九龍中心"): "https://dragoncentre.com.hk/",
    ("灣仔區", "Hysan Place"): "https://www.hysanplace.com.hk/",
    ("灣仔區", "合和商場"): "https://www.hopewellhill.com.hk/",
}

NEW_OVERRIDES = [
    {
        "mall_name": "數碼港商場",
        "district": "南區",
        "title": "數碼港商場消費免費泊車優惠",
        "details": "單一電子消費滿 HK$100／HK$200 可享 1／2 小時；累積滿 HK$400（最多兩張不同商戶單據）可享 4 小時。星期一至五（公眾假期除外）下午 5 時或以後入車，同日 17:00–22:00 食肆單一消費滿 HK$100 可享 5 小時。換領：商場一樓客戶服務部。",
        "source_url": "https://connect.cyberport.hk/zh-hk/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "西九龍中心",
        "district": "深水埗區",
        "title": "西九龍中心免費泊車優惠",
        "details": "星期一至五以電子消費滿港幣 $200 或以上，或星期六、日及公眾假期滿港幣 $300 或以上，最高可獲最多 4 小時免費泊車（含即日及下次使用泊車券安排）。最多可累積五張不同商戶電子消費收據；詳情以場內公告為準。",
        "source_url": "https://dragoncentre.com.hk/parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "Hysan Place",
        "district": "灣仔區",
        "title": "利園區／希慎廣場免費泊車優惠",
        "details": "星期一至四（公眾假期除外）於利園區以電子貨幣／八達通即日消費滿 HK$400 享 3 小時免費泊車；星期五、六、日及公眾假期滿 HK$600 享 3 小時。最多兩組即日機印單據；須成為會員並經 Lee Gardens App 換領。",
        "source_url": "https://www.leegardens.com.hk/car-park-promotion.aspx",
        "is_evergreen": True,
    },
    {
        "mall_name": "合和商場",
        "district": "灣仔區",
        "title": "合和商場／Hopewell Hill 免費泊車優惠",
        "details": "電子消費滿 HK$200／HK$400／HK$600 可享 1／2／3 小時，或晚上 6 時後入車可按門檻享用夜泊至翌日早上 8 時。最多兩張即日機印發票連電子貨幣單據；適用合和商場及胡忠大廈停車場。",
        "source_url": "https://www.hopewellhill.com.hk/zh-hk/parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "康怡廣場",
        "district": "東區",
        "title": "康怡廣場 hello 恒隆積分泊車禮遇",
        "details": "hello 恒隆會員可經 App／小程序以積分兌換電子泊車券。時租：首半小時 HK$18，其後每小時 HK$27；另設平日日泊及夜泊收費。詳情以恒隆商場官方泊車頁為準。",
        "source_url": "https://hanglungmalls.com/parking?mall=kornhill-plaza",
        "is_evergreen": True,
    },
    {
        "mall_name": "元朗廣場",
        "district": "元朗區",
        "title": "元朗廣場 The Point 會員泊車禮遇",
        "details": "元朗廣場為 The Point 體系商場；會員可按官方／App 公佈以消費或積分換領免費泊車。時租參考：平日約 HK$24／小時，週末及公眾假期約 HK$28／小時。",
        "source_url": "https://www.yuenlongplaza.com/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "+WOO 嘉湖",
        "district": "元朗區",
        "title": "+WOO 嘉湖商場會員及泊車資訊",
        "details": "請參閱官方推廣頁查閱最新商場活動。停車場時租：星期一至五約 HK$19／小時；週末及公眾假期約 HK$22／小時。消費換泊如有推出，以官網及場內公告為準。",
        "source_url": "https://www.fortunemalls.com.hk/tc/promotions",
        "is_evergreen": True,
    },
    {
        "mall_name": "綠楊坊",
        "district": "荃灣區",
        "title": "綠楊坊鄰近訪客泊車資訊",
        "details": "顧客可泊綠楊新邨時租訪客停車場；訪客時租約 HK$17／小時。最新活動與優惠請參閱綠楊坊官方 Happenings 頁。",
        "source_url": "https://www.lukyeunggalleria.com/tch/promotions/carparkinfo",
        "is_evergreen": True,
    },
    {
        "mall_name": "愉景灣廣場 DB Plaza",
        "district": "離島區",
        "title": "愉景灣 Spend & Ride 交通禮遇",
        "details": "私人車輛進入愉景灣受限。訪客可於指定餐飲電子消費後，按官方活動條款換領回程交通相關禮遇（Spend & Ride）；門檻與時段以 visitdiscoverybay.com 公告為準。",
        "source_url": "https://www.visitdiscoverybay.com/en/whats-hot-event/103",
        "is_evergreen": True,
    },
    {
        "mall_name": "愉景灣北商場 DB North Plaza",
        "district": "離島區",
        "title": "愉景灣北商場活動及交通資訊",
        "details": "私人車輛進入愉景灣受限，訪客通常於欣澳／東涌泊車再轉巴士。最新商場活動與 Spend & Ride 等禮遇以官方 What’s Hot 頁為準。",
        "source_url": "https://www.visitdiscoverybay.com/en/whats-hot-event/176",
        "is_evergreen": True,
    },
    {
        "mall_name": "中環街市",
        "district": "中西區",
        "title": "中環街市最新活動及市集優惠",
        "details": "中環街市定期舉辦市集、工作坊與品牌活動；最新日程與報名詳情見官方活動日曆。",
        "source_url": "https://www.centralmarket.hk/tc/event-calendar",
        "is_evergreen": True,
    },
    {
        "mall_name": "錦薈坊",
        "district": "屯門區",
        "title": "錦薈坊最新活動",
        "details": "錦薈坊為 The Point 體系商場；最新推廣與活動見官方「最新活動」頁，會員泊車禮遇以 The Point App／場內公告為準。",
        "source_url": "https://www.k-point.com.hk/%e6%9c%80%e6%96%b0%e6%b4%bb%e5%8b%95/",
        "is_evergreen": True,
    },
    {
        "mall_name": "HomeSquare",
        "district": "沙田區",
        "title": "HomeSquare 活動推廣及泊車資訊",
        "details": "HomeSquare 官方活動推廣頁刊載最新家居展銷與商場優惠；泊車條款見官方泊車頁，換領安排以場內及最新公告為準。",
        "source_url": "https://www.homesquare.com.hk/zh-hant/event-promotions",
        "is_evergreen": True,
    },
    {
        "mall_name": "新港城中心 MOSTown",
        "district": "沙田區",
        "title": "新港城中心 MOSTown 泊車及推廣資訊",
        "details": "MOSTown 官方網站提供最新推廣與泊車優惠入口；消費換泊門檻及會員加碼以官網及場內最新條款為準。",
        "source_url": "https://www.mostown.com.hk/tc/",
        "is_evergreen": True,
    },
    {
        "mall_name": "沙田中心",
        "district": "沙田區",
        "title": "沙田中心及沙田廣場最新推廣",
        "details": "恒基沙田中心及沙田廣場官方推廣頁刊載最新商場活動；泊車及消費禮遇以官網與場內公告為準。",
        "source_url": "https://www.shatinplazacentre.com.hk/tc/promotions/index.shtml",
        "is_evergreen": True,
    },
    {
        "mall_name": "樂富廣場",
        "district": "九龍城區",
        "title": "樂富廣場／領展商場最新推廣",
        "details": "樂富廣場屬領展商場網絡；最新推廣與「優惠泊」等泊車禮遇見領展客戶網推廣頁及場內公告。",
        "source_url": "https://www.linkhk.com/tc/promotion/",
        "is_evergreen": True,
    },
    {
        "mall_name": "黃大仙中心",
        "district": "黃大仙區",
        "title": "黃大仙中心／領展商場最新推廣",
        "details": "黃大仙中心（Temple Mall）屬領展商場網絡；最新推廣與泊車禮遇見領展客戶網推廣頁及場內公告。",
        "source_url": "https://www.linkhk.com/tc/promotion/",
        "is_evergreen": True,
    },
    {
        "mall_name": "T Town",
        "district": "元朗區",
        "title": "T Town／領展商場最新推廣",
        "details": "T Town 屬領展商場網絡；最新推廣與泊車安排見領展客戶網推廣頁、物業頁及場內公告。",
        "source_url": "https://www.linkhk.com/tc/promotion/",
        "is_evergreen": True,
    },
    {
        "mall_name": "赤柱廣場",
        "district": "南區",
        "title": "赤柱廣場／領展商場最新推廣",
        "details": "赤柱廣場屬領展商場網絡；最新推廣見領展客戶網推廣頁，商場資料見 shopCentre 頁。",
        "source_url": "https://www.linkhk.com/tc/promotion/",
        "is_evergreen": True,
    },
    {
        "mall_name": "上水廣場",
        "district": "北區",
        "title": "上水廣場 The Point 免觸式泊車",
        "details": "上水廣場為 The Point 免觸式泊車適用商場之一；會員可按指定消費或積分於 App 換領泊車時數，詳情以 The Point 官方條款為準。",
        "source_url": "https://www.thepoint.com.hk/sc/contactless-parking.html",
        "is_evergreen": True,
    },
    {
        "mall_name": "新都會廣場",
        "district": "葵青區",
        "title": "新都會廣場 The Point 免觸式泊車",
        "details": "新都會廣場為 The Point 免觸式泊車適用商場之一；會員可按指定消費或積分於 App 換領泊車時數，詳情以 The Point 官方條款為準。",
        "source_url": "https://www.thepoint.com.hk/sc/contactless-parking.html",
        "is_evergreen": True,
    },
    {
        "mall_name": "上水匯 spot",
        "district": "北區",
        "title": "上水匯 spot 最新消息及活動",
        "details": "上水匯 spot 官方新聞頁刊載最新商場消息與活動；交通資訊見 how-to-go 頁。",
        "source_url": "https://www.ssspot.com.hk/news.aspx",
        "is_evergreen": True,
    },
    {
        "mall_name": "昇悅商場",
        "district": "深水埗區",
        "title": "昇悅商場最新推廣",
        "details": "昇悅商場推廣活動見 CK Malls 官方推廣列表；最新條款與換領安排以場內及官方公告為準。",
        "source_url": "https://ckmalls.com.hk/cht/promotion/?id=4",
        "is_evergreen": True,
    },
    {
        "mall_name": "利東街",
        "district": "灣仔區",
        "title": "利東街精彩活動及優惠推介",
        "details": "利東街官方網站刊載最新活動、優惠推介及泊車相關資訊；詳情以官網及場內公告為準。",
        "source_url": "https://www.leetungavenue.com.hk/tc/",
        "is_evergreen": True,
    },
]

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


def slug_id(name: str, suffix: str) -> str:
    ascii_part = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-").lower()
    ascii_part = ascii_part.encode("ascii", "ignore").decode().strip("-") or "mall"
    return f"{ascii_part}-{suffix}"


def main() -> int:
    sources_path = DATA / "sources.json"
    overrides_path = DATA / "mall_overrides.json"
    registry = json.loads((DATA / "malls-registry.json").read_text(encoding="utf-8"))
    malls = {(m["district"], m["mall_name"]): m for m in registry["malls"]}

    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
    sources = sources_doc["sources"]
    existing_ids = {s["id"] for s in sources}
    existing_urls = {s.get("url") for s in sources}

    # Update stub / homepage URLs to promotion subpages.
    updated = 0
    for source in sources:
        mall = source.get("mall") or {}
        key = (mall.get("district"), mall.get("mall_name"))
        if key not in PROMO_URLS:
            continue
        new_url = PROMO_URLS[key]
        if source.get("url") != new_url:
            source["url"] = new_url
            updated += 1
        if key in MALL_URL_UPDATES:
            source["mall"]["mall_url"] = MALL_URL_UPDATES[key]
        # Keep stubs disabled unless they already have evergreen parking details.
        if not source.get("enabled") and source.get("is_evergreen"):
            source["enabled"] = True

    # Merge overrides.
    overrides_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
    existing = {
        (o["district"], o["mall_name"], o["source_url"]): o
        for o in overrides_doc.get("overrides", [])
    }
    for item in NEW_OVERRIDES:
        if (item["district"], item["mall_name"]) not in malls:
            raise SystemExit(f"unknown mall: {item}")
        existing[(item["district"], item["mall_name"], item["source_url"])] = item
    overrides_doc["overrides"] = sorted(
        existing.values(), key=lambda o: (o["district"], o["mall_name"], o["title"])
    )
    overrides_path.write_text(
        json.dumps(overrides_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Ensure each new override has an enabled evergreen source.
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
            "_comment": "官方長期政策／活動資訊頁；is_evergreen 保留常態優惠。",
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
                "mall_url": MALL_URL_UPDATES.get(
                    (mall["district"], mall["mall_name"]), mall.get("mall_url")
                ),
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
    print(
        f"updated source urls: {updated}; new overrides: {len(NEW_OVERRIDES)}; "
        f"inserted sources: {inserted}; total overrides: {len(overrides_doc['overrides'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
