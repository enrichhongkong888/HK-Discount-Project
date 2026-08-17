"""Final polish: kill last fallbacks, expand local chains, prepare category tags."""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

NEW_OVERRIDES = [
    {
        "mall_name": "海怡廣場",
        "district": "南區",
        "title": "海怡廣場（海怡東／西商場）基本資料及泊車資訊",
        "details": "海怡廣場為鴨脷洲海怡半島屋苑商場，分海怡西商場及海怡東商場，以天橋連接；主要服務屋苑居民日常購物，與鴨脷洲「新海怡廣場／Horizon Plaza」並非同一商場。屋苑／商場設有訪客／時租泊車設施，收費及任何消費換泊安排請以場內或管理處公告為準。",
        "source_url": "https://zh.wikipedia.org/wiki/%E6%B5%B7%E6%80%A1%E5%BB%A3%E5%A0%B4_(%E8%A5%BF%E7%BF%BC)",
        "is_evergreen": True,
    },
    {
        "mall_name": "大埔廣場",
        "district": "大埔區",
        "title": "大埔廣場屋苑／商場基本資料及泊車資訊",
        "details": "大埔廣場為大埔市中心居屋連基座商場，官方／管理網站載明地址為新界大埔安泰路一號，設兩層購物商場及住宅。設有時租／訪客泊車，收費及任何消費換泊請以場內或管理處公告為準。客戶服務可經官方網站查詢。",
        "source_url": "http://www.taipoplaza.com.hk/",
        "is_evergreen": True,
    },
    {
        "mall_name": "碧海藍天商場",
        "district": "深水埗區",
        "title": "碧海藍天商場基本資料（AEON 荔枝角店）",
        "details": "碧海藍天（Aqua Marine）位於長沙灣深盛路 8 號，基座為商場；現以 AEON 荔枝角店為主要綜合百貨／超市錨點（地下至二樓）。場內設泊車相關設施／服務，惟未見公開固定免費泊車消費門檻，詳情請向分店或場內查詢。",
        "source_url": "https://www.aeonstores.com.hk/shop_info/detail?id=124",
        "is_evergreen": True,
    },
]

REGISTRY_FIXES = {
    ("南區", "海怡廣場"): {
        "mall_url": "https://zh.wikipedia.org/wiki/%E6%B5%B7%E6%80%A1%E5%BB%A3%E5%A0%B4_(%E8%A5%BF%E7%BF%BC)",
    },
    ("大埔區", "大埔廣場"): {
        "address": "大埔安泰路 1 號",
        "phone": "2665 1229",
        "mall_url": "http://www.taipoplaza.com.hk/",
    },
    ("深水埗區", "碧海藍天商場"): {
        "mall_url": "https://www.aeonstores.com.hk/shop_info/detail?id=124",
    },
}

NEW_CHAINS = [
    {
        "chain_id": "aeon_member",
        "store_name": "AEON",
        "title": "AEON BETA／AEON MEMBER CARD 會員計劃",
        "details": "下載 AEON Mobile 以手機號碼登記可成為免年費 AEON BETA 會員；合資格付款方式消費一般每港幣 $5＝1 分。亦可申請 AEON MEMBER CARD 享額外會員禮遇。積分及升級安排以官方條款為準。",
        "source_url": "https://www.aeonstores.com.hk/aeon_member_card/detail04",
        "is_evergreen": True,
        "phone": "2565 3656",
    },
    {
        "chain_id": "donki_dmiles",
        "store_name": "DON DON DONKI",
        "title": "DONKI App／dMiles 會員計劃",
        "details": "下載官方 DONKI App 成為會員，結帳掃描會員碼可賺取 dMiles，並可兌換電子優惠券或禮品；會員等級會影響賺分倍率。會籍為持續營運；詳情以官方 App／條款為準。",
        "source_url": "https://www.dondondonki.com/hk/app/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "saint_honore_cake_easy",
        "store_name": "聖安娜",
        "title": "聖安娜 Cake Easy 會員計劃",
        "details": "下載聖安娜 Cake Easy 官方 App 登記會員，可出示會員條碼享用會員優惠、電子優惠券及網上訂購取貨等服務。會籍為持續營運；當期優惠以 App 公告為準。",
        "source_url": "http://www.sthonore.com/",
        "is_evergreen": True,
        "phone": "2991 6677",
    },
    {
        "chain_id": "maxims_cakes_eatizen",
        "store_name": "美心西餅",
        "title": "Eatizen 美心薈會員計劃（美心西餅）",
        "details": "美心西餅現統一經 Eatizen 美心薈登記／登入，於參與品牌享用電子券及會員禮遇。會籍為持續營運；詳情以 Eatizen／美心西餅條款為準。",
        "source_url": "https://www.eatizen.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "a1_bakery_members",
        "store_name": "東海堂",
        "title": "A-1 Bakery／東海堂會員計劃",
        "details": "下載 A-1 Bakery 官方 App 登記會員，於旗下分店及網購店取合資格消費可累積電子印章及獎賞積分，並可按累積消費升級。詳情以官方條款為準。",
        "source_url": "https://clickandcollect.a-1bakery.com.hk/zh_HK/membership/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "kee_wah_fans",
        "store_name": "奇華餅家",
        "title": "奇華 Fans 會員計劃",
        "details": "下載「奇華 Fans」App 登記即可成為紅咭會員；合資格消費一般每港幣 $1＝1 分，儲滿 500 分可獲港幣 $5 現金券。銀／金咭按累積消費升級。",
        "source_url": "https://keewah.com/hk/keewah-fans",
        "is_evergreen": True,
        "phone": "2785 6066",
    },
    {
        "chain_id": "jhc_jfun",
        "store_name": "日本城",
        "title": "JHC 日本城 J Fun 會員計劃",
        "details": "下載 J Fun／JHC 官方 App 登記成為 J Fun 會員，於指定分店或網購出示會員碼儲 J 分換現金回贈等獎賞；另可於門市付費升級金會員。詳情以官方條款為準。",
        "source_url": "https://www.jhceshop.com/jfun-tnc",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "yata_app",
        "store_name": "一田",
        "title": "YATA 一田 App 會員計劃",
        "details": "下載全新 YATA App 登記會員，可於一田百貨／超市等門市享用會員獎賞、電子禮遇及店舖資訊。會籍為持續營運；當期優惠以官方 App／公告為準。",
        "source_url": "https://www.yata.hk/tch/promotion/2025-07-crm/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "citysuper_super_e",
        "store_name": "city'super",
        "title": "super e 會員計劃",
        "details": "經 city'super／LOG-ON 網站、App 或門市免費申請 super e；合資格消費一般每港幣 $1＝1 積分，並可兌換電子禮券。年消費達指定額可晉升 super e-gold。",
        "source_url": "https://www.citysuper.com.hk/zh/pages/super-e-membership",
        "is_evergreen": True,
        "phone": "2277 3288",
    },
]

MAJOR = [
    ("中西區", "國際金融中心商場"),
    ("中西區", "太古廣場"),
    ("九龍城區", "又一城"),
    ("九龍城區", "黃埔天地"),
    ("九龍城區", "AIRSIDE"),
    ("九龍城區", "樂富廣場"),
    ("元朗區", "YOHO MALL 形點"),
    ("元朗區", "+WOO 嘉湖"),
    ("北區", "上水廣場"),
    ("南區", "THE SOUTHSIDE"),
    ("大埔區", "大埔超級城"),
    ("屯門區", "V city"),
    ("屯門區", "屯門市廣場"),
    ("東區", "太古城中心"),
    ("沙田區", "新城市廣場"),
    ("沙田區", "新港城中心 MOSTown"),
    ("油尖旺區", "海港城"),
    ("油尖旺區", "朗豪坊"),
    ("油尖旺區", "奧海城"),
    ("油尖旺區", "ELEMENTS 圓方"),
    ("深水埗區", "V Walk"),
    ("灣仔區", "時代廣場"),
    ("荃灣區", "荃灣廣場"),
    ("荃灣區", "OP Mall 海之戀商場"),
    ("葵青區", "青衣城"),
    ("葵青區", "新都會廣場"),
    ("西貢區", "PopCorn"),
    ("西貢區", "新都城中心"),
    ("西貢區", "東港城"),
    ("觀塘區", "apm"),
    ("觀塘區", "德福廣場"),
    ("觀塘區", "MegaBox"),
    ("離島區", "東薈城名店倉"),
    ("黃大仙區", "荷里活廣場"),
    ("黃大仙區", "黃大仙中心"),
]


def presence(chain_id: str, label: str, malls: list[tuple[str, str]], **extra) -> list[dict]:
    rows = []
    for district, mall_name in malls:
        row = {
            "chain_id": chain_id,
            "mall_name": mall_name,
            "district": district,
            "floor": extra.get("floor", ""),
            "shop_number": label,
        }
        if "store_name" in extra:
            row["store_name"] = extra["store_name"]
        if "phone" in extra:
            row["phone"] = extra["phone"]
        rows.append(row)
    return rows


NEW_PRESENCE = (
    [
        {"chain_id": "aeon_member", "mall_name": "康怡廣場", "district": "東區", "floor": "", "shop_number": "AEON STYLE 康怡"},
        {"chain_id": "aeon_member", "mall_name": "黃埔天地", "district": "九龍城區", "floor": "", "shop_number": "AEON STYLE 黃埔"},
        {"chain_id": "aeon_member", "mall_name": "碧海藍天商場", "district": "深水埗區", "floor": "地下至二樓", "shop_number": "AEON 荔枝角店"},
        {"chain_id": "aeon_member", "mall_name": "MegaBox", "district": "觀塘區", "floor": "", "shop_number": "AEON 九龍灣店"},
        {"chain_id": "aeon_member", "mall_name": "屯門市廣場", "district": "屯門區", "floor": "", "shop_number": "AEON 屯門店"},
        {"chain_id": "aeon_member", "mall_name": "THE ONE", "district": "油尖旺區", "floor": "", "shop_number": "AEON 尖沙咀店"},
        {"chain_id": "donki_dmiles", "mall_name": "黃埔天地", "district": "九龍城區", "floor": "", "shop_number": "DON DON DONKI"},
        {"chain_id": "donki_dmiles", "mall_name": "OP Mall 海之戀商場", "district": "荃灣區", "floor": "", "shop_number": "DON DON DONKI"},
        {"chain_id": "donki_dmiles", "mall_name": "荷里活廣場", "district": "黃大仙區", "floor": "", "shop_number": "DON DON DONKI"},
        {"chain_id": "donki_dmiles", "mall_name": "屯門市廣場", "district": "屯門區", "floor": "", "shop_number": "DON DON DONKI"},
        {"chain_id": "citysuper_super_e", "mall_name": "國際金融中心商場", "district": "中西區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "citysuper_super_e", "mall_name": "時代廣場", "district": "灣仔區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "citysuper_super_e", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "citysuper_super_e", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "citysuper_super_e", "mall_name": "THE SOUTHSIDE", "district": "南區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "citysuper_super_e", "mall_name": "AIRSIDE", "district": "九龍城區", "floor": "", "shop_number": "city'super"},
        {"chain_id": "yata_app", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "一田百貨"},
        {"chain_id": "yata_app", "mall_name": "大埔超級城", "district": "大埔區", "floor": "", "shop_number": "一田百貨"},
        {"chain_id": "yata_app", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": "3-4樓", "shop_number": "一田百貨"},
        {"chain_id": "yata_app", "mall_name": "東港城", "district": "西貢區", "floor": "", "shop_number": "一田超市"},
        {"chain_id": "yata_app", "mall_name": "V city", "district": "屯門區", "floor": "地下", "shop_number": "一田超市"},
    ]
    + presence("saint_honore_cake_easy", "聖安娜餅屋", MAJOR)
    + presence("maxims_cakes_eatizen", "美心西餅", MAJOR)
    + presence("jhc_jfun", "日本城", MAJOR)
    + presence(
        "kee_wah_fans",
        "奇華餅家",
        [
            ("東區", "太古城中心"),
            ("屯門區", "屯門市廣場"),
            ("屯門區", "V city"),
            ("元朗區", "元朗廣場"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("觀塘區", "apm"),
            ("西貢區", "PopCorn"),
            ("九龍城區", "又一城"),
            ("灣仔區", "時代廣場"),
        ],
    )
    + presence(
        "a1_bakery_members",
        "東海堂",
        [
            ("黃大仙區", "黃大仙中心"),
            ("黃大仙區", "荷里活廣場"),
            ("深水埗區", "V Walk"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "ELEMENTS 圓方"),
            ("油尖旺區", "奧海城"),
            ("觀塘區", "德福廣場"),
            ("觀塘區", "apm"),
            ("九龍城區", "樂富廣場"),
            ("九龍城區", "又一城"),
            ("九龍城區", "AIRSIDE"),
            ("九龍城區", "黃埔天地"),
            ("沙田區", "新城市廣場"),
            ("元朗區", "YOHO MALL 形點"),
            ("荃灣區", "荃灣廣場"),
        ],
    )
)


def presence_key(row: dict) -> tuple:
    return (
        row["chain_id"],
        row["district"],
        row["mall_name"],
        row.get("store_name") or row.get("shop_number") or "",
    )


def main() -> int:
    registry_path = DATA / "malls-registry.json"
    overrides_path = DATA / "mall_overrides.json"
    chains_path = DATA / "chain_store_offers.json"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    malls = {(m["district"], m["mall_name"]): m for m in registry["malls"]}
    for key, fix in REGISTRY_FIXES.items():
        malls[key].update(fix)
    registry["malls"] = sorted(malls.values(), key=lambda m: (m["district"], m["mall_name"]))
    if "by_district" in registry:
        by_district: dict[str, list] = {}
        for mall in registry["malls"]:
            by_district.setdefault(mall["district"], []).append(mall)
        registry["by_district"] = by_district
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    overrides_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
    existing_ov = {
        (o["district"], o["mall_name"], o["source_url"]): o
        for o in overrides_doc.get("overrides", [])
    }
    for item in NEW_OVERRIDES:
        existing_ov[(item["district"], item["mall_name"], item["source_url"])] = item
    overrides_doc["overrides"] = sorted(
        existing_ov.values(), key=lambda o: (o["district"], o["mall_name"], o["title"])
    )
    overrides_path.write_text(
        json.dumps(overrides_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    chains_doc = json.loads(chains_path.read_text(encoding="utf-8"))
    by_id = {c["chain_id"]: c for c in chains_doc.get("chains", [])}
    for chain in NEW_CHAINS:
        by_id[chain["chain_id"]] = chain
    chains_doc["chains"] = sorted(by_id.values(), key=lambda c: c["chain_id"])

    existing_p = {presence_key(p): p for p in chains_doc.get("presence", [])}
    skipped = 0
    for row in NEW_PRESENCE:
        if (row["district"], row["mall_name"]) not in malls:
            skipped += 1
            continue
        existing_p[presence_key(row)] = row
    chains_doc["presence"] = sorted(
        existing_p.values(),
        key=lambda p: (p["chain_id"], p["district"], p["mall_name"], p.get("shop_number", "")),
    )
    chains_path.write_text(json.dumps(chains_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"overrides={len(overrides_doc['overrides'])} chains={len(chains_doc['chains'])} "
        f"presence={len(chains_doc['presence'])} skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
