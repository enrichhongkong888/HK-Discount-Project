"""Enrich chain_store_offers.json with group loyalty programmes, everyday brands,
and more concrete evergreen benefit wording. Then rematerialize SPA feeds."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from store_authenticity import VERIFICATION_PENDING, VERIFICATION_VERIFIED  # noqa: E402

CHAIN_PATH = ROOT / "data" / "chain_store_offers.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
DEFAULT_FLOOR = ""
MALL_WIDE_FLOOR = "全場參與商戶"

# High-footfall malls used for F&B / retail chain presence (subset of registry).
MAJOR: list[tuple[str, str]] = [
    ("中西區", "國際金融中心商場"),
    ("中西區", "太古廣場"),
    ("九龍城區", "AIRSIDE"),
    ("九龍城區", "又一城"),
    ("九龍城區", "樂富廣場"),
    ("九龍城區", "黃埔天地"),
    ("元朗區", "+WOO 嘉湖"),
    ("元朗區", "YOHO MALL 形點"),
    ("元朗區", "元朗廣場"),
    ("北區", "上水廣場"),
    ("南區", "THE SOUTHSIDE"),
    ("南區", "海怡廣場"),
    ("南區", "香港仔中心商場"),
    ("大埔區", "大埔超級城"),
    ("屯門區", "V city"),
    ("屯門區", "屯門市廣場"),
    ("屯門區", "屯門時代廣場"),
    ("東區", "北角匯"),
    ("東區", "太古城中心"),
    ("東區", "康怡廣場"),
    ("沙田區", "HomeSquare"),
    ("沙田區", "圍方 The Wai"),
    ("沙田區", "新城市廣場"),
    ("沙田區", "新港城中心 MOSTown"),
    ("油尖旺區", "ELEMENTS 圓方"),
    ("油尖旺區", "K11 MUSEA"),
    ("油尖旺區", "THE ONE"),
    ("油尖旺區", "奧海城"),
    ("油尖旺區", "朗豪坊"),
    ("油尖旺區", "海港城"),
    ("深水埗區", "V Walk"),
    ("深水埗區", "西九龍中心"),
    ("灣仔區", "Hysan Place"),
    ("灣仔區", "時代廣場"),
    ("荃灣區", "D·PARK 愉景新城"),
    ("荃灣區", "OP Mall 海之戀商場"),
    ("荃灣區", "荃新天地"),
    ("荃灣區", "荃灣廣場"),
    ("葵青區", "新都會廣場"),
    ("葵青區", "青衣城"),
    ("西貢區", "PopCorn"),
    ("西貢區", "將軍澳中心 Park Central"),
    ("西貢區", "新都城中心"),
    ("西貢區", "東港城"),
    ("觀塘區", "MegaBox"),
    ("觀塘區", "apm"),
    ("觀塘區", "德福廣場"),
    ("離島區", "東薈城名店倉"),
    ("黃大仙區", "荷里活廣場"),
    ("黃大仙區", "黃大仙中心"),
]

# Property-group programmes -> malls in our 74-mall registry.
GROUP_MALLS: dict[str, list[tuple[str, str]]] = {
    "the_point": [
        ("中西區", "國際金融中心商場"),
        ("九龍城區", "AIRSIDE"),
        ("元朗區", "YOHO MALL 形點"),
        ("元朗區", "元朗廣場"),
        ("北區", "上水廣場"),
        ("南區", "THE SOUTHSIDE"),
        ("大埔區", "大埔超級城"),
        ("屯門區", "V city"),
        ("屯門區", "錦薈坊"),
        ("東區", "北角匯"),
        ("沙田區", "HomeSquare"),
        ("沙田區", "圍方 The Wai"),
        ("沙田區", "新城市廣場"),
        ("深水埗區", "V Walk"),
        ("荃灣區", "荃灣廣場"),
        ("葵青區", "新都會廣場"),
        ("西貢區", "PopCorn"),
        ("西貢區", "東港城"),
        ("觀塘區", "apm"),
    ],
    "splus_rewards": [
        ("屯門區", "屯門市廣場"),
        ("油尖旺區", "奧海城"),
        ("荃灣區", "荃新天地"),
    ],
    "hcoins": [
        ("屯門區", "屯門時代廣場"),
        ("沙田區", "新港城中心 MOSTown"),
        ("沙田區", "沙田中心"),
        ("西貢區", "新都城中心"),
        ("西貢區", "將軍澳中心 Park Central"),
    ],
    "pacific_place_above": [
        ("中西區", "太古廣場"),
    ],
    "club_ic": [
        ("中西區", "國際金融中心商場"),
    ],
    "my_festival": [
        ("九龍城區", "又一城"),
    ],
    "klub11": [
        ("油尖旺區", "K11 MUSEA"),
        ("油尖旺區", "K11購物藝術館"),
    ],
    "harbour_cityzen": [
        ("油尖旺區", "海港城"),
    ],
    "times_square_members": [
        ("灣仔區", "時代廣場"),
    ],
}

# Enrich / replace details for existing chains (must stay evergreen & concrete).
DETAIL_UPDATES: dict[str, str] = {
    "a1_bakery_members": (
        "下載 A-1 Bakery／東海堂官方 App 登記會員；合資格門市或網購消費可累積電子印章及獎賞積分，"
        "並可按累積消費額升級會籍。積分／印章可兌換現金券或指定產品；當期倍率與迎新禮以 App 公告為準。"
    ),
    "aeon_member": (
        "下載 AEON Mobile 以手機號碼免費登記 AEON BETA；合資格付款方式消費一般每港幣 $5＝1 分，"
        "積分可兌換電子現金券。另可申請 AEON MEMBER CARD 享額外會員禮遇；升級門檻及換領以官方條款為準。"
    ),
    "cafe_de_coral_club100": (
        "透過大家樂 App 登記 Club 100：可享會員限定電子券、儲分／樂賞印、手機點餐及生日禮遇。"
        "合資格堂食／外賣消費可累積積分換領產品或現金券；迎新及每週優惠以 App 公告為準。"
    ),
    "citistore_cu_app": (
        "登記 CU APP 會員後，可於千色 Citistore、C生活、APITA、GUU SAN 谷辰及 UNY 等實體／網店"
        "出示會員碼儲分及換領現金回贈或電子券；會籍持續營運，當期倍數及門檻以 App 為準。"
    ),
    "citysuper_super_e": (
        "經 city'super／LOG-ON 網站、App 或門市免費申請 super e；合資格消費一般每港幣 $1＝1 積分，"
        "積分可兌換電子禮券。年消費達指定額可晉升 super e-gold，享更高換領及專屬禮遇。"
    ),
    "donki_dmiles": (
        "下載 DONKI App 成為會員並於結帳掃描會員碼：合資格消費可賺 dMiles，"
        "並可按會員等級提升賺分倍率；dMiles 可兌換電子優惠券或禮品，詳情以 App／條款為準。"
    ),
    "fairwood_app": (
        "下載大快活 App 登記會員，可享每週會員獨家電子券、迎新券、生日禮遇及手機點餐。"
        "合資格消費可累積會員獎賞換領食品或現金券；當期折扣以 App「會員優惠」為準。"
    ),
    "gu_app": (
        "下載 GU Hong Kong App 登入會員，結帳掃描會員條碼即可享用 App 會員限定優惠價；"
        "另可獲迎新／生日折價券。折扣幅度及適用貨品以 App 當期公告為準。"
    ),
    "hcoins": (
        "於 H·COINS 參與恒基地產商場商戶以電子支付消費，一般每港幣 $1＝1 H COIN；"
        "指定千色／CU 等商戶連結 CU APP 後可享每港幣 $1＝2 H COIN。"
        "每 250 H COIN 約可兌換 HK$1 H Dollar（每 10 H Dollar＝HK$10），亦可換電子券；詳情以官方條款為準。"
    ),
    "jhc_jfun": (
        "下載 J Fun／JHC App 登記 J Fun 會員，於指定分店或網購出示會員碼儲 J 分；"
        "J 分可兌換現金回贈。另可於門市付費升級金會員享更高賺分或專屬券；詳情以官方條款為準。"
    ),
    "kee_wah_fans": (
        "下載「奇華 Fans」App 即成紅咭會員；合資格消費一般每港幣 $1＝1 分，"
        "儲滿 500 分可獲港幣 $5 現金券。銀／金咭按累積消費升級，享更高換領或專屬禮遇。"
    ),
    "kfc_app": (
        "下載 KFC HK & Macau App 登記會員：可享 App 專屬套餐優惠；合資格消費一般每港幣 $1＝1 分，"
        "可選擇累積 KFC 積分或 yuu 積分換領獎賞。當期電子券折扣以 App 為準。"
    ),
    "maxims_cakes_eatizen": (
        "美心西餅統一經 Eatizen 美心薈登入：於參與品牌出示會員碼可儲分／用電子券，"
        "並可兌換現金券或產品。會籍持續營運；當期積分倍數及換領以 Eatizen／美心條款為準。"
    ),
    "mcdonalds_app": (
        "登記麥當勞 App 後，合資格消費一般每港幣 $1＝1 分，可用積分兌換產品或現金券。"
        "積分約於賺取後一年同月月底到期；App 另設每日／每週會員限定折扣，詳情以官方條款為準。"
    ),
    "moneyback": (
        "以 MoneyBack／易賞錢 App 於百佳、Taste、FUSION、屈臣氏等出示會員碼儲分及用分；"
        "合資格消費可累積積分兌換現金券或換購貨品，並可享會員日／專屬折扣。當期倍率以官方公告為準。"
    ),
    "muji_app": (
        "下載 MUJI app HK & Macao 註冊會員；於港、澳 MUJI／Café&Meal MUJI 合資格消費"
        "一般每港幣／澳門幣 $1＝1 積分，累積後可兌換電子現金券。詳情以官方條款為準。"
    ),
    "ok_stamp_it": (
        "下載 OK Stamp It App 登記會員，於 OK 便利店合資格消費可儲電子印花及換領獎賞；"
        "另可享用會員專屬電子券／組合優惠。印花門檻及換領清單以 App 公告為準。"
    ),
    "pacific_coffee_perfect_cup": (
        "經 Pacific Coffee Hong Kong App 登記 Perfect Cup Card：按會員等級消費賺分"
        "（一般每港幣 $1＝1／1.5／2 分），並可享迎新券、生日飲品禮遇及會員專屬折扣。詳情以官方計劃為準。"
    ),
    "pizza_hut_rewards": (
        "加入 Hut Rewards（Pizza Hut App）：堂食、自取或外送合資格消費可儲分換獎賞，"
        "並可下載會員專屬套餐／配料折扣券。賺分倍率及換領以 App／條款為準。"
    ),
    "pricerite_pcoin": (
        "經實惠網店或 App 登記 P-Coin 會員；於實惠／家匠 TMF 等參與品牌合資格購物"
        "一般每港幣 $2＝1 P-Coin，P-Coin 可兌換現金回贈或獎賞。詳情以官方會員條款為準。"
    ),
    "saint_honore_cake_easy": (
        "下載聖安娜 Cake Easy App 登記會員，出示會員條碼可享會員價／電子優惠券，"
        "並可網上訂購取貨。會籍持續營運；當期折扣及換領以 App 公告為準。"
    ),
    "samgor_spicy_club": (
        "下載譚仔三哥 App 登記三哥辛會員；香港分店合資格消費一般每港幣 $1＝1 分"
        "（亦可掃描機印收據補登），積分可兌換食品或現金券。詳情以官方條款為準。"
    ),
    "sasa_vip": (
        "下載 Sasa HK App 登記會員；門市及網店合資格消費一般每港幣 $1＝1 積分，"
        "積分可折現或換獎賞。達指定消費額可升級 VIP 享更高回贈或專屬折扣。"
    ),
    "starbucks_rewards": (
        "以已啟動的香港／澳門星巴克卡於參與分店消費，一般每滿港幣／澳門幣 $20 獲一粒星星；"
        "按星星晉升級別並換領免費飲品或其他獎賞。詳情以 Starbucks Rewards 條款為準。"
    ),
    "sushi_express_members": (
        "下載爭鮮會員 App 登記會籍，合資格堂食消費可累積積分換領獎賞或電子券，"
        "並可參與會員專屬活動。季節印花換購屬短期推廣；常態積分以會員專區為準。"
    ),
    "tamjai_club": (
        "下載譚仔雲南米線 App 登記 TamJai Club；合資格消費一般每港幣 $1＝1 分，"
        "積分可兌換獎賞，並可按累積消費解鎖 VIP 禮遇（如額外倍數或專屬券）。"
    ),
    "uniqlo_app": (
        "下載 UNIQLO Hong Kong & Macau App 註冊會員，可獲迎新／生日優惠券；"
        "線上或實體店掃描會員條碼享用 App 會員限定折扣價。折扣幅度以 App 當期公告為準。"
    ),
    "yata_app": (
        "下載一田 App 登記會員，於一田百貨／超市合資格消費可儲 The Point 或一田積分"
        "（視乎分店與會籍），並可享會員日多倍積分及電子現金券換領。詳情以一田／The Point 條款為準。"
    ),
    "yoshi_club": (
        "下載吉野家（香港）App 登記 YOSHI CLUB：可預先點餐、下載會員電子券、"
        "賺取及使用獎賞換領食品。會籍持續營運；當期折扣以 App 為準。"
    ),
    "yuu": (
        "於惠康、萬寧、7-Eleven、KFC 等 yuu 參與商戶出示 yuu 會員碼儲分；"
        "合資格消費一般可按商戶規則賺 yuu 分，並可用分兌換現金券或換購貨品。"
        "會員日／多倍積分以 yuu App 公告為準。"
    ),
}

NEW_CHAINS: list[dict] = [
    {
        "chain_id": "the_point",
        "store_name": "The Point",
        "title": "The Point 新地商場綜合會員計劃",
        "details": (
            "免費登記 The Point：於參與新地商場指定商戶以電子支付消費，一般每港幣 $1＝1 積分"
            "（The Point Gold 於參與商場可享約 1.5 倍）；積分可轉 Point Dollar 當現金用，"
            "或換泊車時數、電子券及獎賞。生日月另有約 1.5 倍積分；詳情以 The Point 官方條款為準。"
        ),
        "source_url": "https://www.thepoint.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "splus_rewards",
        "store_name": "S⁺ REWARDS",
        "title": "S⁺ REWARDS 信和商場會員計劃",
        "details": (
            "下載 S⁺ REWARDS App 免費登記：於屯門市廣場、奧海城、荃新天地等信和指定商場／商戶"
            "合資格電子消費，一般每港幣 $100＝1 分；積分可換免費泊車、禮品及電子獎賞。"
            "亦可完成任務／印花活動賺額外分；詳情以官方條款為準。"
        ),
        "source_url": "https://www.splusrewards.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "pacific_place_above",
        "store_name": "above",
        "title": "Pacific Place above 會員計劃",
        "details": (
            "經太古廣場 App 登記 above 會員：於太古廣場及指定商戶合資格消費一般每港幣 $1＝1 分；"
            "積分可按會籍級別兌換 above Dollar（約 60–250 分＝HK$1）於參與商戶當現金使用，"
            "並可享泊車及會員專屬禮遇。詳情以官方條款為準。"
        ),
        "source_url": "https://www.pacificplace.com.hk/tc/above",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "club_ic",
        "store_name": "CLUB ic",
        "title": "ifc mall CLUB ic 會員計劃",
        "details": (
            "登記 CLUB ic：於國際金融中心商場指定商戶合資格消費一般每港幣 $1＝1 ifc 積分；"
            "積分可換泊車、電子禮券或會員禮遇，並可按累積消費晉升會籍級別。詳情以 ifc／CLUB ic 條款為準。"
        ),
        "source_url": "https://ifc.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "my_festival",
        "store_name": "My FESTIVAL",
        "title": "又一城 My FESTIVAL 會員計劃",
        "details": (
            "免費登記 My FESTIVAL：於又一城以信用卡／扣賬卡／易辦事／銀聯／八達通等合資格消費可累積積分，"
            "換領購物禮券、免費泊車及會員專屬餐飲／購物禮遇；成功登記另有迎新積分。詳情以官方條款為準。"
        ),
        "source_url": "https://www.festivalwalk.com.hk/tc/my-festival",
        "is_evergreen": True,
        "phone": "2844 2222",
    },
    {
        "chain_id": "klub11",
        "store_name": "KLUB 11",
        "title": "KLUB 11／K Point 會員計劃",
        "details": (
            "經 K11 HK App 登記 KLUB 11 並綁定 K Dollar：於 K11 MUSEA／K11 購物藝術館等指定商戶"
            "合資格消費可賺 K Point 積分，並可兌換獎賞或轉成 K Dollar 於參與商戶當現金使用。"
            "亦可於結帳出示會員 QR 即時賺分；換領及積分規則以 KLUB 11 條款為準。"
        ),
        "source_url": "https://klub-11.com/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "harbour_cityzen",
        "store_name": "HARBOUR CITYZEN",
        "title": "海港城 HARBOUR CITYZEN 會員計劃",
        "details": (
            "免費登記 HARBOUR CITYZEN：可參與海港城常設及季節性消費換領（電子券、泊車、禮品等），"
            "並接收會員專屬推廣。受邀 VIC Club 另按級別於合資格消費一般每港幣 $1＝1／1.5／2 分。"
            "當期換領門檻以海港城 App／場內公告為準。"
        ),
        "source_url": "https://www.harbourcity.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "times_square_members",
        "store_name": "時代廣場會員",
        "title": "時代廣場會員消費獎賞",
        "details": (
            "經時代廣場官方 App／會員計劃登記後，可於指定商戶合資格消費換領泊車時數、電子現金券"
            "或季節性獎賞；會員亦可享用餐飲／零售商戶專屬禮遇。換領門檻及積分規則以官方公告為準。"
        ),
        "source_url": "https://www.timessquare.com.hk/",
        "is_evergreen": True,
        "phone": "請向商場查詢",
    },
    {
        "chain_id": "tsui_wah_members",
        "store_name": "翠華",
        "title": "翠華會員／App 優惠計劃",
        "details": (
            "下載翠華官方 App 或登記會員，可獲迎新電子券、生日禮遇及定期會員折扣／套餐優惠；"
            "合資格堂食消費可累積獎賞換領食品或現金券。當期折扣以 App 公告為準。"
        ),
        "source_url": "https://www.tsuiwah.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "hung_fook_tong_vip",
        "store_name": "鴻福堂",
        "title": "鴻福堂會員獎賞計劃",
        "details": (
            "登記鴻福堂會員／App：合資格門市消費一般可儲印花或積分換領湯品／飲品現金券，"
            "並可享會員專屬折扣或換購價。印花門檻及換領清單以官方 App／門市公告為準。"
        ),
        "source_url": "https://www.hungfooktong.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "hui_lau_shan_members",
        "store_name": "許留山",
        "title": "許留山會員計劃",
        "details": (
            "下載許留山官方 App 登記會員，可享迎新券、生日甜品禮遇及定期會員套餐折扣；"
            "合資格消費可累積積分換領指定甜品或現金券。詳情以 App／條款為準。"
        ),
        "source_url": "https://www.huilaushan.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "gong_cha_members",
        "store_name": "貢茶",
        "title": "貢茶會員積分計劃",
        "details": (
            "經貢茶香港官方 App／小程序登記會員：合資格飲品消費可儲分換領免費飲品或折扣券，"
            "並可獲生日及迎新禮遇。賺分倍率及換領所需積分以 App 公告為準。"
        ),
        "source_url": "https://www.gongcha.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "milksha_members",
        "store_name": "迷客夏",
        "title": "迷客夏會員計劃",
        "details": (
            "下載迷客夏官方 App 登記會員，合資格消費可累積積分換領飲品或折扣券，"
            "並可享會員日／生日優惠。積分規則及換領門檻以 App 條款為準。"
        ),
        "source_url": "https://www.milkshoptea.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "cha_tang_hui_members",
        "store_name": "茶湯會",
        "title": "茶湯會會員獎賞",
        "details": (
            "登記茶湯會會員／App：合資格飲品消費可儲分或集印花換領指定飲品，"
            "並可下載會員專屬折扣券。當期換領門檻以官方公告為準。"
        ),
        "source_url": "https://www.chatanghui.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "colourmix_vip",
        "store_name": "Colourmix",
        "title": "Colourmix 會員／VIP 計劃",
        "details": (
            "下載 Colourmix App 登記會員：門市合資格消費一般可按金額儲分，"
            "積分可兌換現金券或換購護膚彩妝；達指定消費可升級 VIP 享更高回贈。詳情以官方條款為準。"
        ),
        "source_url": "https://www.colourmix.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "wing_wah_members",
        "store_name": "榮華",
        "title": "榮華餅家會員計劃",
        "details": (
            "登記榮華會員／App：合資格門市或網購消費可儲分換領現金券或月餅／糕點禮品，"
            "並可享會員專屬折扣。積分倍數及換領以官方條款為準。"
        ),
        "source_url": "https://www.wingwah.com/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "genki_sushi_members",
        "store_name": "元氣壽司",
        "title": "元氣壽司會員計劃",
        "details": (
            "下載元氣壽司香港 App 登記會員：堂食合資格消費可儲分換領食品或現金券，"
            "並可享用會員限定套餐折扣。賺分及換領規則以 App 公告為準。"
        ),
        "source_url": "https://www.genkisushi.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "mx_eatizen",
        "store_name": "美心 MX",
        "title": "Eatizen 美心薈（美心 MX）",
        "details": (
            "經 Eatizen 美心薈登入後，於美心 MX 等參與品牌出示會員碼可儲分及使用電子券；"
            "合資格消費可累積積分兌換現金券或食品。當期積分倍數以 Eatizen／美心條款為準。"
        ),
        "source_url": "https://www.eatizen.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "fortress_club",
        "store_name": "豐澤",
        "title": "豐澤 Fortress Club 會員計劃",
        "details": (
            "登記 Fortress Club：於豐澤門市或網店合資格消費可儲分換領現金券或配件禮品，"
            "並可享會員專屬折扣及延保／換購優惠。賺分倍率以官方會員條款為準。"
        ),
        "source_url": "https://www.fortress.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
    {
        "chain_id": "broadway_club",
        "store_name": "百老匯",
        "title": "百老匯 Broadway Club 會員計劃",
        "details": (
            "登記 Broadway Club：於百老匯門市合資格消費可儲分換領現金回贈或電子券，"
            "並可享會員專屬機電產品折扣。積分及換領門檻以官方條款為準。"
        ),
        "source_url": "https://www.broadway.com.hk/",
        "is_evergreen": True,
        "phone": "請向分店查詢",
    },
]

# Brand presence: chain_id -> (shop_number label, mall list). Skip Hysan Place for QSR/fashion
# brands known not to trade there; keep drinks/bakery/personal care on MAJOR.
BRAND_PRESENCE: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "gong_cha_members": ("貢茶", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "milksha_members": ("迷客夏", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "cha_tang_hui_members": ("茶湯會", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "colourmix_vip": ("Colourmix", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "wing_wah_members": ("榮華餅家", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "hung_fook_tong_vip": ("鴻福堂", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "hui_lau_shan_members": ("許留山", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "genki_sushi_members": ("元氣壽司", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "mx_eatizen": ("美心 MX", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "tsui_wah_members": ("翠華餐廳", [m for m in MAJOR if m[1] != "Hysan Place"]),
    "fortress_club": (
        "豐澤",
        [
            ("九龍城區", "又一城"),
            ("元朗區", "YOHO MALL 形點"),
            ("南區", "THE SOUTHSIDE"),
            ("屯門區", "V city"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("灣仔區", "時代廣場"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "新都會廣場"),
            ("西貢區", "PopCorn"),
            ("觀塘區", "apm"),
            ("觀塘區", "MegaBox"),
            ("黃大仙區", "荷里活廣場"),
        ],
    ),
    "broadway_club": (
        "百老匯",
        [
            ("九龍城區", "又一城"),
            ("元朗區", "YOHO MALL 形點"),
            ("屯門區", "屯門市廣場"),
            ("東區", "太古城中心"),
            ("沙田區", "新城市廣場"),
            ("油尖旺區", "海港城"),
            ("油尖旺區", "朗豪坊"),
            ("灣仔區", "時代廣場"),
            ("荃灣區", "荃灣廣場"),
            ("葵青區", "青衣城"),
            ("西貢區", "東港城"),
            ("觀塘區", "apm"),
            ("觀塘區", "德福廣場"),
            ("黃大仙區", "黃大仙中心"),
        ],
    ),
}

# Same loyalty programme, distinct on-mall store labels.
AFFILIATE_PRESENCE: list[dict] = [
    {"chain_id": "moneyback", "mall_name": "又一城", "district": "九龍城區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "海港城", "district": "油尖旺區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "朗豪坊", "district": "油尖旺區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "新城市廣場", "district": "沙田區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "YOHO MALL 形點", "district": "元朗區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "V city", "district": "屯門區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "apm", "district": "觀塘區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "時代廣場", "district": "灣仔區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "太古城中心", "district": "東區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "moneyback", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": DEFAULT_FLOOR, "shop_number": "屈臣氏", "store_name": "屈臣氏"},
    {"chain_id": "yuu", "mall_name": "新城市廣場", "district": "沙田區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "YOHO MALL 形點", "district": "元朗區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "海港城", "district": "油尖旺區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "朗豪坊", "district": "油尖旺區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "V city", "district": "屯門區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "apm", "district": "觀塘區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "德福廣場", "district": "觀塘區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "荃灣廣場", "district": "荃灣區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "青衣城", "district": "葵青區", "floor": DEFAULT_FLOOR, "shop_number": "萬寧", "store_name": "萬寧"},
    {"chain_id": "yuu", "mall_name": "新都會廣場", "district": "葵青區", "floor": DEFAULT_FLOOR, "shop_number": "7-Eleven", "store_name": "7-Eleven"},
    {"chain_id": "yuu", "mall_name": "海港城", "district": "油尖旺區", "floor": DEFAULT_FLOOR, "shop_number": "7-Eleven", "store_name": "7-Eleven"},
    {"chain_id": "yuu", "mall_name": "國際金融中心商場", "district": "中西區", "floor": DEFAULT_FLOOR, "shop_number": "7-Eleven", "store_name": "7-Eleven"},
    {"chain_id": "yuu", "mall_name": "時代廣場", "district": "灣仔區", "floor": DEFAULT_FLOOR, "shop_number": "7-Eleven", "store_name": "7-Eleven"},
    {"chain_id": "yuu", "mall_name": "太古廣場", "district": "中西區", "floor": DEFAULT_FLOOR, "shop_number": "7-Eleven", "store_name": "7-Eleven"},
]

SUBSTANTIVE = re.compile(
    r"(港幣\s*\$?\s*\d|\$\s*\d|\d+\s*分|積分|印花|倍|折扣|回贈|現金券|電子券|Point Dollar|H COIN|P-Coin|星星)"
)


def presence_rows(
    chain_id: str,
    shop_number: str,
    malls: list[tuple[str, str]],
    *,
    floor: str = DEFAULT_FLOOR,
) -> list[dict]:
    return [
        {
            "chain_id": chain_id,
            "mall_name": mall_name,
            "district": district,
            "floor": floor,
            "shop_number": shop_number,
            "verification_status": VERIFICATION_PENDING,
        }
        for district, mall_name in malls
    ]


def merge_chains(existing: list[dict], new_chains: list[dict]) -> list[dict]:
    by_id = {str(c.get("chain_id")): dict(c) for c in existing if c.get("chain_id")}
    for chain in new_chains:
        cid = chain["chain_id"]
        if cid in by_id:
            # Keep phone if new one is generic and old is specific.
            merged = {**by_id[cid], **chain}
            by_id[cid] = merged
        else:
            by_id[cid] = dict(chain)
    for cid, details in DETAIL_UPDATES.items():
        if cid in by_id:
            by_id[cid]["details"] = details
    return sorted(by_id.values(), key=lambda c: str(c["chain_id"]))


def merge_presence(existing: list[dict], extra: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for row in existing + extra:
        chain_id = str(row.get("chain_id", ""))
        mall_name = str(row.get("mall_name", ""))
        shop_number = str(row.get("shop_number") or "").strip()
        key = (chain_id, mall_name, shop_number)
        if not chain_id or not mall_name or key in seen:
            continue
        seen.add(key)
        floor = str(row.get("floor") or "").strip()
        if floor in {"請向商場查詢", "商場指定層", "全場參與商戶"}:
            # Mall-wide / placeholder floors cannot be verified store units.
            floor = ""
        status = str(row.get("verification_status") or "").strip()
        if status not in {VERIFICATION_VERIFIED, VERIFICATION_PENDING}:
            status = VERIFICATION_PENDING
        item = {
            "chain_id": chain_id,
            "mall_name": mall_name,
            "district": str(row.get("district", "")),
            "floor": floor,
            "shop_number": shop_number,
            "verification_status": status,
        }
        store_name = str(row.get("store_name") or "").strip()
        if store_name:
            item["store_name"] = store_name
        phone = str(row.get("phone") or "").strip()
        if phone:
            item["phone"] = phone
        # Only keep verified if still precise; otherwise force pending.
        if status == VERIFICATION_VERIFIED:
            from store_authenticity import presence_is_verified

            if not presence_is_verified(item):
                item["verification_status"] = VERIFICATION_PENDING
        out.append(item)
    out.sort(key=lambda r: (r["chain_id"], r["district"], r["mall_name"], r["shop_number"]))
    return out


def assert_substantive(chains: list[dict]) -> None:
    weak = [
        c["chain_id"]
        for c in chains
        if c.get("is_evergreen") and not SUBSTANTIVE.search(str(c.get("details", "")))
    ]
    if weak:
        raise SystemExit(f"details too vague for: {', '.join(weak)}")


def rematerialize() -> None:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scraper import (
        load_chain_store_offers,
        load_json,
        load_mall_overrides,
        mall_from_json,
        merge_offers,
        offer_from_json,
        write_outputs,
    )

    discounts_path = ROOT / "discounts.json"
    malls_path = REGISTRY_PATH
    reference_time = datetime.now(timezone.utc).astimezone()
    existing = [
        o for raw in load_json(discounts_path).get("offers", []) if (o := offer_from_json(raw))
    ]
    base = [o for o in existing if o.source_name != "chain_store_offers"]
    malls = [m for raw in load_json(malls_path).get("malls", []) if (m := mall_from_json(raw))]
    known = {(m.district, m.mall_name) for m in malls}
    overrides = load_mall_overrides(ROOT / "data" / "mall_overrides.json", known, reference_time)
    chains = load_chain_store_offers(CHAIN_PATH, known, reference_time)
    offers = merge_offers(base, overrides + chains, reference_time)
    write_outputs(discounts_path, malls_path, offers, malls)
    print(f"rematerialized offers={len(offers)} chain_injected={len(chains)}")


def main() -> None:
    payload = json.loads(CHAIN_PATH.read_text(encoding="utf-8"))
    chains = merge_chains(payload.get("chains", []), NEW_CHAINS)
    assert_substantive(chains)

    extra: list[dict] = []
    for chain_id, malls in GROUP_MALLS.items():
        label = next(c["store_name"] for c in chains if c["chain_id"] == chain_id)
        extra.extend(presence_rows(chain_id, label, malls, floor=MALL_WIDE_FLOOR))
    for chain_id, (label, malls) in BRAND_PRESENCE.items():
        extra.extend(presence_rows(chain_id, label, malls))
    extra.extend(AFFILIATE_PRESENCE)

    presence = merge_presence(payload.get("presence", []), extra)
    # Drop false Hysan Place QSR/fashion if reintroduced by older scripts.
    ban = {
        "cafe_de_coral_club100",
        "fairwood_app",
        "kfc_app",
        "mcdonalds_app",
        "muji_app",
        "pacific_coffee_perfect_cup",
        "sasa_vip",
        "starbucks_rewards",
        "uniqlo_app",
        "tsui_wah_members",
        "mx_eatizen",
        "genki_sushi_members",
        "gong_cha_members",
        "hung_fook_tong_vip",
        "colourmix_vip",
        "hui_lau_shan_members",
        "milksha_members",
        "cha_tang_hui_members",
        "wing_wah_members",
    }
    presence = [
        r
        for r in presence
        if not (r["mall_name"] == "Hysan Place" and r["chain_id"] in ban)
    ]

    payload = {
        "_comment": (
            "連鎖商店／集團會員常態禮遇對照。presence 僅收錄已知駐場或全場適用商場；"
            "樓層僅在有核實資料或全場計劃時填寫，未知則留空；"
            "集團計劃用「全場參與商戶」。"
            "details 須含具體積分／折扣／回贈說明。"
        ),
        "chains": chains,
        "presence": presence,
    }
    CHAIN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"chains={len(chains)} presence={len(presence)}")

    rematerialize()


if __name__ == "__main__":
    main()
