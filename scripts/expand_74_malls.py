"""One-shot expansion of sources.json + mall_overrides.json for all 74 registry malls."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

NEW_OVERRIDES = [
    {
        "mall_name": "朗豪坊",
        "district": "油尖旺區",
        "title": "朗豪坊免費泊車優惠",
        "details": "憑最多兩張不同商戶即日電子消費單據（每張須滿 HK$100）換領：平日消費滿 HK$200／HK$400 可享 1／2 小時；週末及公眾假期滿 HK$400／HK$600 可享 1／2 小時。即日戲票兩張及 LP CLUB 會員可另享額外時數。",
        "source_url": "https://www.langhamplace.com.hk/zh-hk/visit-us/parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "奧海城",
        "district": "油尖旺區",
        "title": "奧海城免費泊車優惠",
        "details": "平日於 1／2／3 期消費滿 HK$200／HK$400 可享 1／2 小時。週末及公眾假期：1 期滿 HK$200／HK$400 享 1／2 小時；2／3 期滿 HK$300／HK$600 享 1／2 小時。憑最多兩張不同商戶即日電子單據換領。",
        "source_url": "https://www.olympiancity.com.hk/tc/Parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "太古廣場",
        "district": "中西區",
        "title": "太古廣場 above 會員免費泊車",
        "details": "above 會員於太古廣場／三座／六座及星街小區指定商戶，即日累積電子消費滿 HK$500，或下午 5 時後滿 HK$300，可享 3 小時免費泊車；above Blue 會員可額外 1 小時。亦可憑 above 積分換領泊車時數。",
        "source_url": "https://www.pacificplace.com.hk/zh-hk/entertainment/happenings/free-parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "置地廣場",
        "district": "中西區",
        "title": "置地廣場 BESPOKE 免費代客泊車",
        "details": "BESPOKE 雋環會員憑最多三張即日合資格單據：消費滿 HK$1,500／HK$4,000 可享 2／4 小時免費代客泊車；晚上 6 時後進場之指定餐飲消費滿 HK$500／HK$1,000 可享 2／4 小時。",
        "source_url": "https://www.landmark.hk/tc/whats-on/happenings/complimentary-valet-parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "國際金融中心商場",
        "district": "中西區",
        "title": "ifc mall 免費泊車及 CLUB ic 泊車禮遇",
        "details": "即日單一電子消費滿 HK$300／HK$500 可享 2／3 小時免費泊車；消費滿 HK$2,000 可換領 4 小時免費代客泊車。CLUB ic Lifetime／Black 會員每日可換領 2 小時、Platinum 會員 1 小時會員泊車。",
        "source_url": "https://ifc.com.hk/en/mall/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "K11 MUSEA",
        "district": "油尖旺區",
        "title": "K11 MUSEA KLUB 11 免費泊車",
        "details": "只限 KLUB 11 會員。憑 K11 MUSEA 或 K11 購物藝術館即日單據：星期一至四消費滿 HK$200／HK$300 可享 2／3 小時；星期五至日及公眾假期滿 HK$500／HK$800 可享 2／3 小時。",
        "source_url": "https://www.k11musea.com/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "K11購物藝術館",
        "district": "油尖旺區",
        "title": "K11 購物藝術館 KLUB 11 免費泊車",
        "details": "只限 KLUB 11 會員於 B4 時租停車場換領。星期一至四消費滿 HK$300／HK$500 可享 1／2 小時；星期五至日及公眾假期滿 HK$500／HK$800 可享 1／2 小時。",
        "source_url": "https://hk.k11.com/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "THE ONE",
        "district": "油尖旺區",
        "title": "THE ONE 免費泊車及午市泊車優惠",
        "details": "憑最多兩張不同商戶即日機印單據，於 UG2 顧客服務中心換領，每日最多可享 3 小時免費泊車；百老匯戲院即日票尾亦適用。另設午市餐飲泊車優惠，每日最多 2 小時。",
        "source_url": "https://www.the-one.hk/mobile/tc/gettingthere/parking.asp",
        "is_evergreen": True,
    },
    {
        "mall_name": "V city",
        "district": "屯門區",
        "title": "V city The Point 會員免費泊車",
        "details": "只限 The Point 會員。平日消費滿 HK$200／HK$400 或 1,500 積分可享 1／2 小時；週末及公眾假期滿 HK$700／HK$900 或 4,000 積分可享 1／2 小時。入車時段 07:00–22:00，每次最多合共 2 小時。",
        "source_url": "https://www.vcity.com.hk/tch/parking/parking.jsp",
        "is_evergreen": True,
    },
    {
        "mall_name": "荃新天地",
        "district": "荃灣區",
        "title": "荃新天地免費泊車優惠",
        "details": "於荃新天地或荃新天地 2 即日電子消費滿 HK$200／HK$400，可享 1／2 小時免費泊車（入車時段 10:00–22:00）。憑最多兩張不同商戶即日機印單據換領。",
        "source_url": "https://citywalk.com.hk/tc/Parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "荃灣廣場",
        "district": "荃灣區",
        "title": "荃灣廣場 The Point 會員免費泊車",
        "details": "只限 The Point 會員。入車時段 10:00–22:00，即日消費滿 HK$200／HK$400 可享 1／2 小時；平日指定餐飲消費滿 HK$200 可額外 1 小時。亦可按平日／假日積分門檻換領。",
        "source_url": "https://www.tsuenwanplaza.com.hk/tc/parking-tc/",
        "is_evergreen": True,
    },
    {
        "mall_name": "青衣城",
        "district": "葵青區",
        "title": "青衣城 MTR Mobile 免費泊車優惠",
        "details": "MTR Mobile 會員尊享。平日／After 6／週末可按消費或戲票換領最高 4 小時；平日另設餐飲泊車禮遇。詳情以青衣城官方條款為準。",
        "source_url": "https://www.maritimesquare.com/tch/promotions/free-parking-privilege",
        "is_evergreen": True,
    },
    {
        "mall_name": "THE SOUTHSIDE",
        "district": "南區",
        "title": "THE SOUTHSIDE 泊車優惠",
        "details": "只限 MTR Mobile 會員。基本優惠：消費滿 HK$200／HK$500 可享 1／3 小時；平日餐飲／After 6／戲票另設禮遇。詳情以官方條款為準。",
        "source_url": "https://www.thesouthside.com.hk/tch/promotions/parking-promotion",
        "is_evergreen": True,
    },
    {
        "mall_name": "D·PARK 愉景新城",
        "district": "荃灣區",
        "title": "D·PARK 如心賞會員消費泊車優惠",
        "details": "如心賞會員憑最多兩張即日不同商戶電子單據：平日消費滿 HK$100／HK$200／HK$300／HK$400／HK$500 可享 1 至 5 小時；週末及公眾假期滿 HK$200／HK$300／HK$400 可享 1／2／3 小時。",
        "source_url": "https://www.dpark.com.hk/contact?lang=tc",
        "is_evergreen": True,
    },
    {
        "mall_name": "V Walk",
        "district": "深水埗區",
        "title": "V Walk The Point 會員免費泊車",
        "details": "只限 The Point 會員。平日消費滿 HK$200／HK$300 或 1,500 積分可享 1／2 小時；週末及公眾假期滿 HK$300／HK$500 或 3,000 積分可享 1／2 小時。",
        "source_url": "https://www.vwalk.com.hk/tch/access/parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "圍方 The Wai",
        "district": "沙田區",
        "title": "圍方免費泊車優惠",
        "details": "平日消費及餐飲可按時段換領 1 至 4 小時免費泊車；週末及公眾假期滿 HK$300／HK$600 可享 2／4 小時。兩張英皇戲院 Plus+ 即日戲票可換領 3 小時。",
        "source_url": "https://www.thewaimall.com/tch/promotions/free-parking-privilege",
        "is_evergreen": True,
    },
    {
        "mall_name": "皇室堡",
        "district": "灣仔區",
        "title": "皇室堡免費泊車及午市泊車優惠",
        "details": "憑最多兩張不同商戶即日機印單據：平日消費滿 HK$200／HK$400／HK$500 可享 1／2／3 小時；週末及公眾假期滿 HK$300／HK$500／HK$600 可享 1／2／3 小時。平日午市餐飲另設泊車禮遇。",
        "source_url": "https://www.windsorhouse.hk/index.php?id=178&lang=tc&sec=event",
        "is_evergreen": True,
    },
    {
        "mall_name": "杏花新城",
        "district": "東區",
        "title": "杏花新城免費泊車優惠",
        "details": "憑不多於兩張即日電子消費單據：平日消費滿 HK$200／HK$300 可享 1／2 小時；週末及公眾假期滿 HK$400 可享 2 小時。平日 After 6 夜泊另設消費滿 HK$200 最高 4 小時禮遇。",
        "source_url": "https://www.paradise-mall.com.hk/tch/promotions/free_parking_privilege",
        "is_evergreen": True,
    },
    {
        "mall_name": "北角匯",
        "district": "東區",
        "title": "北角匯 The Point 會員免費泊車",
        "details": "只限 The Point 會員。平日單一商戶消費滿 HK$200 或累積滿 HK$400 可享 1／2 小時；週末及公眾假期單一滿 HK$400 或累積滿 HK$800 可享 1／2 小時。",
        "source_url": "https://www.harbournorth.com.hk/zh/valet-parking-tc/",
        "is_evergreen": True,
    },
    {
        "mall_name": "東薈城名店倉",
        "district": "離島區",
        "title": "東薈城名店倉免費泊車禮遇",
        "details": "即日單一電子消費滿 HK$200／HK$400 可換領免費泊車（適用 P2／P3，不適用 P1；每日最多 3 小時）。CLUB CG 會員每日可額外 1 小時。",
        "source_url": "https://www.citygateoutlets.com.hk/zh-hk/offer-events/events/parking-offers/",
        "is_evergreen": True,
    },
    {
        "mall_name": "大埔超級城",
        "district": "大埔區",
        "title": "大埔超級城 The Point 會員免費泊車",
        "details": "只限 The Point 會員，並只適用多層停車場。平日消費滿 HK$200／HK$300／HK$400 可享 1／2／3 小時；週末及公眾假期消費滿 HK$400 可享 2 小時。",
        "source_url": "https://taipomegamall.shkp.com/parking/",
        "is_evergreen": True,
    },
    {
        "mall_name": "粉嶺名都商場",
        "district": "北區",
        "title": "粉嶺名都商場購物泊車優惠",
        "details": "平日消費滿 HK$200／HK$300 可享 1／2 小時；週末及公眾假期滿 HK$300／HK$500 可享 1／2 小時。於 G/F 禮賓部 07:00–23:59 辦理。",
        "source_url": "https://www.fanlingcentre.com.hk/html/tc/parking",
        "is_evergreen": True,
    },
    {
        "mall_name": "東港城",
        "district": "西貢區",
        "title": "東港城 The Point 會員免費泊車",
        "details": "只限 The Point 會員。平日消費或積分可換領 1 至 3 小時；週末及公眾假期滿 HK$400／HK$600 可享 2／3 小時。最多兩組即日機印發票。",
        "source_url": "https://www.eastpointcity.com.hk/parking-2/",
        "is_evergreen": True,
    },
    {
        "mall_name": "將軍澳中心 Park Central",
        "district": "西貢區",
        "title": "將軍澳中心 The Point 會員免費泊車",
        "details": "只限 The Point 會員，入車時段 10:00–22:00。平日消費滿 HK$300／HK$500 可享 2／3 小時；週末及公眾假期滿 HK$400／HK$600 可享 2／3 小時。",
        "source_url": "https://www.park-central.com.hk/tc-parking-service/",
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

STUB_SELECTORS = {
    "card": ".replace-with-verified-offer-card",
    "title": "h1, h2",
    "discount_info": "main, body",
    "start_date": ".start-date",
    "expiry_date": ".expiry-date",
    "link": "a[href]",
    "image": "img",
    "daily_special": ".daily-special",
}


def parking_source(item: dict, mall_meta: dict) -> dict:
    slug = (
        item["source_url"]
        .rstrip("/")
        .split("//", 1)[-1]
        .replace(".", "-")
        .replace("/", "-")[:40]
    )
    return {
        "id": f"parking-{mall_meta['mall_name']}-{slug}".encode("ascii", "ignore").decode()
        or f"parking-{hash(item['mall_name']) & 0xffff}",
        "enabled": True,
        "_comment": "官方泊車條款頁未設短期截止日；is_evergreen 保留長期泊車政策。",
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
            "mall_name": mall_meta["mall_name"],
            "district": mall_meta["district"],
            "address": mall_meta.get("address"),
            "phone": mall_meta.get("phone"),
            "network_phone": mall_meta.get("network_phone"),
            "mall_url": mall_meta.get("mall_url"),
        },
        "selectors": BODY_SELECTORS,
    }


def stub_source(mall: dict, comment: str) -> dict:
    mall_url = mall.get("mall_url") or f"https://example.com/mall/{mall['mall_name']}"
    safe_id = "".join(ch if ch.isalnum() else "-" for ch in mall["mall_name"]).strip("-").lower()
    safe_id = safe_id.encode("ascii", "ignore").decode() or f"mall-{hash(mall['mall_name']) & 0xffff}"
    return {
        "id": f"{safe_id}-profile-stub",
        "enabled": False,
        "_comment": comment,
        "target": "malls",
        "name": mall["mall_name"],
        "url": mall_url,
        "category": "商場優惠",
        "district": mall["district"],
        "brand_name": mall["mall_name"],
        "is_daily_special": False,
        "mall": {
            "mall_name": mall["mall_name"],
            "district": mall["district"],
            "address": mall.get("address"),
            "phone": mall.get("phone"),
            "network_phone": mall.get("network_phone"),
            "mall_url": mall.get("mall_url"),
        },
        "selectors": STUB_SELECTORS,
    }


def slug_id(mall_name: str, suffix: str) -> str:
    ascii_part = "".join(ch if ch.isalnum() else "-" for ch in mall_name).strip("-").lower()
    ascii_part = ascii_part.encode("ascii", "ignore").decode().strip("-") or "mall"
    return f"{ascii_part}-{suffix}"


def main() -> int:
    registry = json.loads((DATA / "malls-registry.json").read_text(encoding="utf-8"))
    malls = { (m["district"], m["mall_name"]): m for m in registry["malls"] }

    overrides_path = DATA / "mall_overrides.json"
    overrides_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
    existing_ov = {
        (o["district"], o["mall_name"], o["source_url"]): o
        for o in overrides_doc.get("overrides", [])
    }
    for item in NEW_OVERRIDES:
        key = (item["district"], item["mall_name"], item["source_url"])
        if (item["district"], item["mall_name"]) not in malls:
            raise SystemExit(f"override mall missing from registry: {item}")
        existing_ov[key] = item
    overrides_doc["overrides"] = sorted(
        existing_ov.values(),
        key=lambda o: (o["district"], o["mall_name"], o["title"]),
    )
    overrides_path.write_text(
        json.dumps(overrides_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    sources_path = DATA / "sources.json"
    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
    sources = sources_doc["sources"]
    covered = {
        (s["mall"]["district"], s["mall"]["mall_name"])
        for s in sources
        if s.get("target") == "malls" and s.get("mall")
    }
    existing_ids = {s["id"] for s in sources}
    existing_urls = {s["url"] for s in sources if s.get("target") == "malls"}

    # Ensure every NEW_OVERRIDE has a corresponding enabled evergreen source.
    insert_before = next(
        (i for i, s in enumerate(sources) if s["id"] in {"hk-mall-template", "skyscanner-hk"}),
        len(sources),
    )
    to_insert: list[dict] = []

    for item in NEW_OVERRIDES:
        mall = malls[(item["district"], item["mall_name"])]
        if item["source_url"] in existing_urls:
            continue
        src = {
            "id": slug_id(item["mall_name"], "parking-privileges"),
            "enabled": True,
            "_comment": "官方泊車條款頁未設短期截止日；is_evergreen 保留長期泊車政策。",
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
        # Avoid id collisions
        base_id = src["id"]
        n = 2
        while src["id"] in existing_ids:
            src["id"] = f"{base_id}-{n}"
            n += 1
        existing_ids.add(src["id"])
        existing_urls.add(src["url"])
        covered.add((mall["district"], mall["mall_name"]))
        to_insert.append(src)

    # Add disabled stubs for any registry mall still missing from sources.
    for mall in registry["malls"]:
        key = (mall["district"], mall["mall_name"])
        if key in covered:
            continue
        comment = (
            "registry mall_url 為 null，暫無可靠官方優惠來源。"
            if not mall.get("mall_url")
            else "尚未核實可穩定抓取的優惠卡片／常設泊車政策頁；先以官方主站作 stub。"
        )
        src = stub_source(mall, comment)
        base_id = src["id"]
        n = 2
        while src["id"] in existing_ids:
            src["id"] = f"{base_id}-{n}"
            n += 1
        existing_ids.add(src["id"])
        covered.add(key)
        to_insert.append(src)

    sources[insert_before:insert_before] = to_insert
    sources_doc["sources"] = sources
    sources_path.write_text(
        json.dumps(sources_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Coverage report
    mall_sources = [s for s in sources if s.get("target") == "malls" and s.get("mall")]
    unique = {(s["mall"]["district"], s["mall"]["mall_name"]) for s in mall_sources}
    unique.discard(("沙田區", "請填入商場名稱"))
    enabled = {
        (s["mall"]["district"], s["mall"]["mall_name"])
        for s in mall_sources
        if s.get("enabled") and s["mall"]["mall_name"] != "請填入商場名稱"
    }
    ov_unique = {(o["district"], o["mall_name"]) for o in overrides_doc["overrides"]}
    print(f"registry: {len(malls)}")
    print(f"sources unique malls: {len(unique)}")
    print(f"enabled unique malls: {len(enabled)}")
    print(f"overrides unique malls: {len(ov_unique)}")
    print(f"inserted sources: {len(to_insert)}")
    missing = sorted(set(malls) - unique)
    if missing:
        print("STILL MISSING:", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
