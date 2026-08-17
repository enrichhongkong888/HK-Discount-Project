"""Expand chain_store_offers.json and retarget store-promotion sources."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

NEW_CHAINS = [
    {
        "chain_id": "kfc_app",
        "store_name": "肯德基",
        "title": "KFC App 會員獎賞計劃",
        "details": "下載官方 KFC HK & Macau App 並登記成為會員，可享用 App 專屬優惠；合資格消費一般每港幣 $1 可賺 1 分，並可選擇累積 KFC 會員積分或 yuu 積分換領獎賞。詳情以官方 App／條款為準。",
        "source_url": "https://www.kfchk.com/",
        "is_evergreen": True,
        "phone": "2310 6900",
    },
    {
        "chain_id": "fairwood_app",
        "store_name": "大快活",
        "title": "大快活 App 會員計劃",
        "details": "下載大快活官方 App 登記成為會員，可享用每週會員獨家優惠、迎新電子券、生日禮遇，以及堂食／外賣手機點餐等服務。會籍為持續營運之會員計劃；當期優惠以 App 公告為準。",
        "source_url": "https://www.fairwood.com.hk/app",
        "is_evergreen": True,
        "phone": "2856 7111",
    },
    {
        "chain_id": "yoshi_club",
        "store_name": "吉野家",
        "title": "YOSHI CLUB 會員計劃",
        "details": "下載吉野家（香港）官方 App 登記 YOSHI CLUB，可預先點餐、下載優惠券、賺取及使用獎賞，並接收會員推廣資訊。會籍計劃屬持續營運；詳情以官方 App／條款為準。",
        "source_url": "https://www.yoshinoya.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "tamjai_club",
        "store_name": "譚仔雲南米線",
        "title": "譚仔會員計劃（TamJai Club）",
        "details": "下載譚仔雲南米線官方 App 登記 TamJai Club；合資格消費一般每港幣 $1 賺 1 分，可用積分兌換獎賞，並可按累積消費解鎖 VIP 禮遇。詳情以官方會員條款為準。",
        "source_url": "https://tamjaimixian.com/introduce-mobile-app/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "samgor_spicy_club",
        "store_name": "譚仔三哥米線",
        "title": "三哥辛會員獎賞計劃",
        "details": "下載譚仔三哥官方 App 登記三哥辛會員；於香港分店合資格消費一般每港幣 $1 賺 1 分，亦可掃描機印收據登記賺分，並可用積分兌換獎賞。詳情以官方條款為準。",
        "source_url": "https://www.tjsamgor.com/hk/introduce-mobile-app/",
        "is_evergreen": True,
        "phone": "8200 1880",
    },
    {
        "chain_id": "pacific_coffee_perfect_cup",
        "store_name": "太平洋咖啡",
        "title": "Perfect Cup Card 會員計劃",
        "details": "透過 Pacific Coffee Hong Kong App 登記 Perfect Cup Card 會員，按會員等級消費賺分（一般每港幣 $1 可賺 1／1.5／2 分），並可享迎新券、生日禮遇及會員專屬優惠。詳情以官方會員計劃為準。",
        "source_url": "https://www.pacificcoffee.com/usMemberPlan/index.html",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "pizza_hut_rewards",
        "store_name": "必勝客",
        "title": "Hut Rewards 會員獎賞計劃",
        "details": "下載 Pizza Hut HK & Macau 官方 App 並加入 Hut Rewards，可於堂食、外賣自取或外送訂購時儲分換獎賞，並享用會員專屬優惠。會籍計劃屬持續營運。詳情以官方 App／條款為準。",
        "source_url": "https://www.pizzahut.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "sasa_vip",
        "store_name": "莎莎",
        "title": "莎莎會員／VIP 計劃",
        "details": "下載 Sasa HK 官方 App 登記會員；門市及網店合資格消費一般每港幣 $1 送 1 積分，積分可折現或兌換獎賞。達指定消費額可升級 VIP。詳情以官方 App／會籍條款為準。",
        "source_url": "https://www.sasa.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "uniqlo_app",
        "store_name": "UNIQLO",
        "title": "UNIQLO App 會員計劃",
        "details": "下載 UNIQLO Hong Kong & Macau 官方 App 並註冊會員，可獲迎新／生日優惠券，並於線上或實體店掃描會員條碼享用 App 會員限定優惠。會籍為持續營運。",
        "source_url": "https://www.uniqlo.com.hk/zh_HK/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "gu_app",
        "store_name": "GU",
        "title": "GU App 會員計劃",
        "details": "下載 GU Hong Kong 官方 App 登入會員，可於結帳掃描會員條碼享用 App 會員限定優惠價，並獲生日折價券等禮遇。會籍為持續營運。",
        "source_url": "https://www.gu-global.com/hk/zh_HK/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "muji_app",
        "store_name": "無印良品",
        "title": "MUJI app 會員積分計劃",
        "details": "下載 MUJI app HK & Macao 註冊會員；於港、澳 MUJI／Café&Meal MUJI 合資格消費一般每港幣／澳門幣 $1 獲 1 積分，累積後可兌換電子現金券。詳情以官方條款為準。",
        "source_url": "https://www.muji.com/hk/mujiapp/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "pricerite_pcoin",
        "store_name": "實惠",
        "title": "P-Coin 會員獎賞計劃",
        "details": "透過實惠網店或官方 App 登記 P-Coin 會員；於實惠／家匠 TMF 等參與品牌合資格購物一般每港幣 $2 獲 1 P-Coin，並可兌換現金回贈或獎賞。詳情以官方條款為準。",
        "source_url": "https://www.pricerite.com.hk/membership/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "citistore_cu_app",
        "store_name": "千色店",
        "title": "CU APP 會員計劃",
        "details": "登記 CU APP 會員，可一站式於千色 Citistore、C生活、APITA、GUU SAN 谷辰及 UNY 生活創庫等實體及網店享用購物及獎賞優惠。會籍計劃屬持續營運。",
        "source_url": "https://www.citistore.com.hk/cu-app-membership/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "sushi_express_members",
        "store_name": "爭鮮",
        "title": "爭鮮會員計劃",
        "details": "下載爭鮮官方會員 App 登記會籍，可累積積分換領獎賞、享用會員專屬活動／優惠。季節印花換購屬短期推廣，不列入常態條款。詳情以官方會員專區為準。",
        "source_url": "https://www.sushiexpress.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
]

# Presence rows generated from verified-programme research (major-mall heuristics).
# Watsons -> MoneyBack; Mannings / 7-Eleven -> yuu (same programme, distinct store label).
AFFILIATE_PRESENCE = [
    {"chain_id": "moneyback", "mall_name": "又一城", "district": "九龍城區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "朗豪坊", "district": "油尖旺區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "YOHO MALL 形點", "district": "元朗區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "V city", "district": "屯門區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "apm", "district": "觀塘區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "時代廣場", "district": "灣仔區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "太古城中心", "district": "東區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "moneyback", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": "", "shop_number": "屈臣氏", "store_name": "屈臣氏", "phone": "2606 8833"},
    {"chain_id": "yuu", "mall_name": "新城市廣場", "district": "沙田區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "YOHO MALL 形點", "district": "元朗區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "朗豪坊", "district": "油尖旺區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "V city", "district": "屯門區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "apm", "district": "觀塘區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "德福廣場", "district": "觀塘區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "青衣城", "district": "葵青區", "floor": "", "shop_number": "萬寧", "store_name": "萬寧", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "新都會廣場", "district": "葵青區", "floor": "", "shop_number": "7-Eleven", "store_name": "7-Eleven", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "海港城", "district": "油尖旺區", "floor": "", "shop_number": "7-Eleven", "store_name": "7-Eleven", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "國際金融中心商場", "district": "中西區", "floor": "", "shop_number": "7-Eleven", "store_name": "7-Eleven", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "時代廣場", "district": "灣仔區", "floor": "", "shop_number": "7-Eleven", "store_name": "7-Eleven", "phone": "2299 1133"},
    {"chain_id": "yuu", "mall_name": "太古廣場", "district": "中西區", "floor": "", "shop_number": "7-Eleven", "store_name": "7-Eleven", "phone": "2299 1133"},
]

# Compact helper to build presence for many malls
MAJOR = [
    ("中西區", "國際金融中心商場"),
    ("中西區", "太古廣場"),
    ("中西區", "置地廣場"),
    ("九龍城區", "又一城"),
    ("九龍城區", "黃埔天地"),
    ("九龍城區", "AIRSIDE"),
    ("九龍城區", "樂富廣場"),
    ("元朗區", "YOHO MALL 形點"),
    ("元朗區", "+WOO 嘉湖"),
    ("元朗區", "元朗廣場"),
    ("北區", "上水廣場"),
    ("北區", "上水中心購物商場"),
    ("南區", "THE SOUTHSIDE"),
    ("大埔區", "大埔超級城"),
    ("屯門區", "V city"),
    ("屯門區", "屯門市廣場"),
    ("東區", "太古城中心"),
    ("東區", "杏花新城"),
    ("東區", "康怡廣場"),
    ("沙田區", "新城市廣場"),
    ("沙田區", "新港城中心 MOSTown"),
    ("沙田區", "圍方 The Wai"),
    ("沙田區", "HomeSquare"),
    ("油尖旺區", "海港城"),
    ("油尖旺區", "朗豪坊"),
    ("油尖旺區", "奧海城"),
    ("油尖旺區", "ELEMENTS 圓方"),
    ("油尖旺區", "K11 MUSEA"),
    ("深水埗區", "西九龍中心"),
    ("深水埗區", "V Walk"),
    ("灣仔區", "時代廣場"),
    ("灣仔區", "Hysan Place"),
    ("荃灣區", "荃灣廣場"),
    ("荃灣區", "荃新天地"),
    ("荃灣區", "D·PARK 愉景新城"),
    ("荃灣區", "OP Mall 海之戀商場"),
    ("葵青區", "青衣城"),
    ("葵青區", "新都會廣場"),
    ("西貢區", "PopCorn"),
    ("西貢區", "新都城中心"),
    ("西貢區", "東港城"),
    ("西貢區", "將軍澳中心 Park Central"),
    ("觀塘區", "apm"),
    ("觀塘區", "德福廣場"),
    ("觀塘區", "MegaBox"),
    ("離島區", "東薈城名店倉"),
    ("黃大仙區", "荷里活廣場"),
    ("黃大仙區", "黃大仙中心"),
]


def presence(chain_id: str, store_label: str, malls: list[tuple[str, str]]) -> list[dict]:
    rows = []
    for district, mall_name in malls:
        rows.append(
            {
                "chain_id": chain_id,
                "mall_name": mall_name,
                "district": district,
                "floor": "",
                "shop_number": store_label,
            }
        )
    return rows


NEW_PRESENCE = (
    presence("uniqlo_app", "UNIQLO", MAJOR)
    + presence(
        "gu_app",
        "GU",
        [
            ("九龍城區", "又一城"),
            ("沙田區", "新城市廣場"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("灣仔區", "時代廣場"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("離島區", "東薈城名店倉"),
            ("南區", "THE SOUTHSIDE"),
        ],
    )
    + presence(
        "muji_app",
        "無印良品",
        [
            ("中西區", "國際金融中心商場"),
            ("中西區", "太古廣場"),
            ("九龍城區", "又一城"),
            ("九龍城區", "AIRSIDE"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "ELEMENTS 圓方"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("灣仔區", "時代廣場"),
            ("灣仔區", "Hysan Place"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("離島區", "東薈城名店倉"),
        ],
    )
    + presence("sasa_vip", "莎莎", MAJOR)
    + presence("fairwood_app", "大快活", MAJOR)
    + presence("kfc_app", "肯德基", MAJOR)
    + presence(
        "pizza_hut_rewards",
        "必勝客",
        [
            ("九龍城區", "又一城"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "奧海城"),
            ("灣仔區", "時代廣場"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "荷里活廣場"),
            ("離島區", "東薈城名店倉"),
            ("北區", "上水廣場"),
        ],
    )
    + presence(
        "pacific_coffee_perfect_cup",
        "太平洋咖啡",
        [
            ("中西區", "國際金融中心商場"),
            ("中西區", "太古廣場"),
            ("九龍城區", "又一城"),
            ("九龍城區", "AIRSIDE"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "ELEMENTS 圓方"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "K11 MUSEA"),
            ("灣仔區", "時代廣場"),
            ("灣仔區", "Hysan Place"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("離島區", "東薈城名店倉"),
            ("南區", "數碼港商場"),
        ],
    )
    + presence(
        "yoshi_club",
        "吉野家",
        [
            ("九龍城區", "黃埔天地"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "奧海城"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "荷里活廣場"),
            ("北區", "上水廣場"),
        ],
    )
    + presence(
        "tamjai_club",
        "譚仔雲南米線",
        [
            ("九龍城區", "又一城"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "奧海城"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "荷里活廣場"),
            ("北區", "上水廣場"),
        ],
    )
    + presence(
        "samgor_spicy_club",
        "譚仔三哥米線",
        [
            ("九龍城區", "黃埔天地"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "奧海城"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "荷里活廣場"),
            ("北區", "上水廣場"),
        ],
    )
    + presence(
        "sushi_express_members",
        "爭鮮",
        [
            ("九龍城區", "又一城"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("油尖旺區", "奧海城"),
            ("灣仔區", "時代廣場"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "PopCorn"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "荷里活廣場"),
            ("離島區", "東薈城名店倉"),
        ],
    )
    + presence(
        "pricerite_pcoin",
        "實惠",
        [
            ("沙田區", "HomeSquare"),
            ("沙田區", "新城市廣場"),
            ("元朗區", "YOHO MALL 形點"),
            ("元朗區", "+WOO 嘉湖"),
            ("屯門區", "V city"),
            ("屯門區", "屯門市廣場"),
            ("東區", "太古城中心"),
            ("油尖旺區", "奧海城"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "黃大仙中心"),
            ("北區", "上水廣場"),
            ("大埔區", "大埔超級城"),
        ],
    )
    + presence(
        "citistore_cu_app",
        "千色店",
        [
            ("沙田區", "新城市廣場"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "屯門市廣場"),
            ("東區", "太古城中心"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "新都城中心"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "黃大仙中心"),
            ("北區", "上水廣場"),
        ],
    )
    + presence(
        "cafe_de_coral_club100",
        "大家樂",
        MAJOR,
    )
    + presence(
        "mcdonalds_app",
        "麥當勞",
        MAJOR,
    )
    + presence(
        "starbucks_rewards",
        "星巴克咖啡",
        MAJOR,
    )
    + presence(
        "ok_stamp_it",
        "OK便利店",
        [
            ("南區", "香港仔中心商場"),
            ("九龍城區", "樂富廣場"),
            ("黃大仙區", "黃大仙中心"),
            ("葵青區", "葵涌廣場"),
            ("元朗區", "T Town"),
            ("北區", "粉嶺名都商場"),
            ("荃灣區", "綠楊坊"),
            ("東區", "北角匯"),
            ("沙田區", "沙田中心"),
            ("屯門區", "錦薈坊"),
        ],
    )
    + AFFILIATE_PRESENCE
)

# Prefer store / dining / merchant promotion subpages over generic mall hubs.
STORE_PROMO_SOURCES = {
    ("九龍城區", "又一城"): "https://www.festivalwalk.com.hk/zh-hk/happenings",
    ("油尖旺區", "海港城"): "https://www.harbourcity.com.hk/en/event_type/sales-offer/",
    ("灣仔區", "時代廣場"): "https://timessquare.com.hk/happenings/",
    ("東區", "太古城中心"): "https://www.cityplaza.com/en/whats-on",
    ("沙田區", "新城市廣場"): "https://www.newtownplaza.com.hk/happenings/",
    ("元朗區", "YOHO MALL 形點"): "https://www.yohomall.hk/en/happenings",
    ("觀塘區", "apm"): "https://www.hkapm.com.hk/en/happening.html",
    ("觀塘區", "德福廣場"): "https://www.telford-plaza.com/en/promotions",
    ("西貢區", "PopCorn"): "https://www.popcorntko.com.hk/en/happenings",
    ("葵青區", "青衣城"): "https://www.maritimesquare.com/tch/promotions",
    ("屯門區", "V city"): "https://www.vcity.com.hk/tch/happening/happening.jsp",
    ("油尖旺區", "朗豪坊"): "https://www.langhamplace.com.hk/zh-hk/whats-on",
    ("油尖旺區", "ELEMENTS 圓方"): "https://www.elementshk.com/tch/elements/promotions",
    ("黃大仙區", "荷里活廣場"): "https://www.plazahollywood.com.hk/en/happenings-en",
    ("荃灣區", "荃灣廣場"): "https://www.tsuenwanplaza.com.hk/en/happenings/",
}


def presence_key(row: dict) -> tuple:
    return (
        row["chain_id"],
        row["district"],
        row["mall_name"],
        row.get("store_name") or row.get("shop_number") or "",
    )


def main() -> int:
    registry = {
        (m["district"], m["mall_name"])
        for m in json.loads((DATA / "malls-registry.json").read_text(encoding="utf-8"))["malls"]
    }
    chains_path = DATA / "chain_store_offers.json"
    doc = json.loads(chains_path.read_text(encoding="utf-8"))

    by_id = {c["chain_id"]: c for c in doc.get("chains", [])}
    for chain in NEW_CHAINS:
        by_id[chain["chain_id"]] = chain
    doc["chains"] = sorted(by_id.values(), key=lambda c: c["chain_id"])

    existing = {presence_key(p): p for p in doc.get("presence", [])}
    skipped = 0
    for row in NEW_PRESENCE:
        key_mall = (row["district"], row["mall_name"])
        if key_mall not in registry:
            skipped += 1
            continue
        existing[presence_key(row)] = row
    doc["presence"] = sorted(
        existing.values(),
        key=lambda p: (p["chain_id"], p["district"], p["mall_name"], p.get("shop_number", "")),
    )
    chains_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Retarget selected sources toward merchant/dining promotion hubs.
    sources_path = DATA / "sources.json"
    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
    updated = 0
    for source in sources_doc["sources"]:
        mall = source.get("mall") or {}
        key = (mall.get("district"), mall.get("mall_name"))
        if key not in STORE_PROMO_SOURCES:
            continue
        # Prefer updating non-evergreen listing sources; keep evergreen parking sources intact.
        if source.get("is_evergreen"):
            continue
        new_url = STORE_PROMO_SOURCES[key]
        if source.get("url") != new_url and source.get("enabled"):
            source["url"] = new_url
            source["_comment"] = "定向商戶／活動推廣子頁，優先捕捉個別商店優惠。"
            updated += 1
    sources_path.write_text(
        json.dumps(sources_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"chains={len(doc['chains'])} presence={len(doc['presence'])} "
        f"skipped_unknown_malls={skipped} store_promo_sources_updated={updated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
