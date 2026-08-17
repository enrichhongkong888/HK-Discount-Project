"""Mark chain presence as verified/pending and keep only precise directory pins.

Verified rows must include precise floor + shop unit + real phone.
Everything else is kept as verification_status=pending and never injected.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from store_authenticity import (  # noqa: E402
    VERIFICATION_PENDING,
    VERIFICATION_VERIFIED,
    presence_is_verified,
)

CHAIN_PATH = ROOT / "data" / "chain_store_offers.json"

# Precise directory pins only (official mall / brand directories). Includes phone.
# Content + validity dates come from the matching evergreen chain programme at inject time.
# Prefer scripts/expand_store_channels.py to merge these pins with brand locators +
# Sino/SHKP public directories; this list remains the hand-verified baseline.
VERIFIED_PINS: list[dict[str, str]] = [
    # ----- 灣仔區 -----
    {
        "chain_id": "samgor_spicy_club",
        "mall_name": "Hysan Place",
        "district": "灣仔區",
        "floor": "11樓",
        "shop_number": "1109",
        "phone": "8200 1880",
        "store_name": "譚仔三哥米線",
    },
    # ----- 沙田區：新城市廣場 / HomeSquare / 圍方 -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "新城市廣場",
        "district": "沙田區",
        "floor": "一期 L2",
        "shop_number": "225",
        "phone": "2606 1126",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "gu_app",
        "mall_name": "新城市廣場",
        "district": "沙田區",
        "floor": "三期 L3",
        "shop_number": "A307",
        "phone": "2205 0388",
        "store_name": "GU",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "新城市廣場",
        "district": "沙田區",
        "floor": "三期 L2",
        "shop_number": "A221",
        "phone": "3971 3130",
        "store_name": "無印良品",
    },
    {
        "chain_id": "sasa_vip",
        "mall_name": "新城市廣場",
        "district": "沙田區",
        "floor": "三期 L3",
        "shop_number": "A335",
        "phone": "2736 8019",
        "store_name": "莎莎",
    },
    {
        "chain_id": "mcdonalds_app",
        "mall_name": "新城市廣場",
        "district": "沙田區",
        "floor": "一期 L2",
        "shop_number": "221-223",
        "phone": "2633 9282",
        "store_name": "麥當勞",
    },
    {
        "chain_id": "yuu",
        "mall_name": "HomeSquare",
        "district": "沙田區",
        "floor": "G/F",
        "shop_number": "G01",
        "phone": "2299 1133",
        "store_name": "惠康",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "圍方 The Wai",
        "district": "沙田區",
        "floor": "2樓",
        "shop_number": "237",
        "phone": "3971 3138",
        "store_name": "無印良品",
    },
    # ----- 元朗區：YOHO MALL -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "YOHO MALL 形點",
        "district": "元朗區",
        "floor": "YOHO MALL I L1",
        "shop_number": "1156-1157",
        "phone": "2440 3668",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "YOHO MALL 形點",
        "district": "元朗區",
        "floor": "YOHO MALL I L1",
        "shop_number": "1061-1062",
        "phone": "3973 8360",
        "store_name": "無印良品",
    },
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "YOHO MALL 形點",
        "district": "元朗區",
        "floor": "YOHO MALL II L3",
        "shop_number": "A335",
        "phone": "2976 0893",
        "store_name": "星巴克",
    },
    {
        "chain_id": "mcdonalds_app",
        "mall_name": "YOHO MALL 形點",
        "district": "元朗區",
        "floor": "YOHO MALL II L3",
        "shop_number": "A312",
        "phone": "2520 5377",
        "store_name": "麥當勞",
    },
    # ----- 中西區：IFC / 太古廣場 / 置地廣場 -----
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "國際金融中心商場",
        "district": "中西區",
        "floor": "2樓",
        "shop_number": "2097-98",
        "phone": "2234 7871",
        "store_name": "星巴克",
    },
    {
        "chain_id": "yuu",
        "mall_name": "國際金融中心商場",
        "district": "中西區",
        "floor": "2樓",
        "shop_number": "2004",
        "phone": "2523 9672",
        "store_name": "萬寧",
    },
    {
        "chain_id": "citysuper_super_e",
        "mall_name": "國際金融中心商場",
        "district": "中西區",
        "floor": "1樓",
        "shop_number": "1041-1049",
        "phone": "2736 3866",
        "store_name": "city'super",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "太古廣場",
        "district": "中西區",
        "floor": "1樓",
        "shop_number": "100",
        "phone": "3973 8370",
        "store_name": "無印良品",
    },
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "太古廣場",
        "district": "中西區",
        "floor": "L1",
        "shop_number": "128-129",
        "phone": "2802 9822",
        "store_name": "星巴克",
    },
    # ----- 東區：太古城中心 -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "太古城中心",
        "district": "東區",
        "floor": "4樓",
        "shop_number": "401",
        "phone": "2907 0302",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "太古城中心",
        "district": "東區",
        "floor": "2-3樓",
        "shop_number": "245,301",
        "phone": "3971 3170",
        "store_name": "無印良品",
    },
    # ----- 油尖旺區：海港城 / 朗豪坊 / 奧海城 -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "海港城",
        "district": "油尖旺區",
        "floor": "港威商場 3樓",
        "shop_number": "3231-3232",
        "phone": "2175 0810",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "朗豪坊",
        "district": "油尖旺區",
        "floor": "7樓",
        "shop_number": "08-12",
        "phone": "3971 3140",
        "store_name": "無印良品",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "奧海城",
        "district": "油尖旺區",
        "floor": "2期 G/F",
        "shop_number": "G78,K01-03,K05-10",
        "phone": "3971 3230",
        "store_name": "無印良品",
    },
    # ----- 觀塘區：apm / 德福廣場 -----
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "apm",
        "district": "觀塘區",
        "floor": "L2",
        "shop_number": "L2-15",
        "phone": "3542 5191",
        "store_name": "星巴克",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "apm",
        "district": "觀塘區",
        "floor": "L1",
        "shop_number": "1a-1c",
        "phone": "3971 3150",
        "store_name": "無印良品",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "德福廣場",
        "district": "觀塘區",
        "floor": "二期 4樓",
        "shop_number": "401-402,431",
        "phone": "3973 8380",
        "store_name": "無印良品",
    },
    # ----- 九龍城區：又一城 / AIRSIDE / 黃埔天地 -----
    {
        "chain_id": "muji_app",
        "mall_name": "又一城",
        "district": "九龍城區",
        "floor": "LG1",
        "shop_number": "LG1-30",
        "phone": "3971 3208",
        "store_name": "無印良品",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "又一城",
        "district": "九龍城區",
        "floor": "L1",
        "shop_number": "L1-01",
        "phone": "2265 8586",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "又一城",
        "district": "九龍城區",
        "floor": "UG",
        "shop_number": "UG-20A",
        "phone": "2265 8589",
        "store_name": "星巴克",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "AIRSIDE",
        "district": "九龍城區",
        "floor": "4樓",
        "shop_number": "408-410",
        "phone": "3971 3158",
        "store_name": "無印良品",
    },
    # ----- 黃大仙區：荷里活廣場 -----
    {
        "chain_id": "muji_app",
        "mall_name": "荷里活廣場",
        "district": "黃大仙區",
        "floor": "1樓",
        "shop_number": "125-127",
        "phone": "3971 3220",
        "store_name": "無印良品",
    },
    # ----- 屯門區：V city -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "V city",
        "district": "屯門區",
        "floor": "MTR",
        "shop_number": "M-89",
        "phone": "2673 4408",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "屯門市廣場",
        "district": "屯門區",
        "floor": "1期 1樓",
        "shop_number": "1140",
        "phone": "3971 3180",
        "store_name": "無印良品",
    },
    # ----- 西貢區：PopCorn -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "PopCorn",
        "district": "西貢區",
        "floor": "PopCorn 2 1樓",
        "shop_number": "F99-102",
        "phone": "2752 1457",
        "store_name": "UNIQLO",
    },
    # ----- 葵青區：新都會廣場 / 青衣城 -----
    {
        "chain_id": "uniqlo_app",
        "mall_name": "新都會廣場",
        "district": "葵青區",
        "floor": "3樓",
        "shop_number": "336",
        "phone": "2661 0618",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "新都會廣場",
        "district": "葵青區",
        "floor": "3樓",
        "shop_number": "346-347",
        "phone": "3973 8350",
        "store_name": "無印良品",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "青衣城",
        "district": "葵青區",
        "floor": "1樓",
        "shop_number": "108C",
        "phone": "2495 6271",
        "store_name": "UNIQLO",
    },
    # ----- 空商場補強：旗艦 / 連鎖定位 -----
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "ELEMENTS 圓方",
        "district": "油尖旺區",
        "floor": "木區 L2",
        "shop_number": "2100B",
        "phone": "2697 0533",
        "store_name": "星巴克",
    },
    {
        "chain_id": "fortress_club",
        "mall_name": "ELEMENTS 圓方",
        "district": "油尖旺區",
        "floor": "水區 L1",
        "shop_number": "1050B",
        "phone": "2196 8252",
        "store_name": "豐澤",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "時代廣場",
        "district": "灣仔區",
        "floor": "9樓",
        "shop_number": "927-928",
        "phone": "3468 7632",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "THE SOUTHSIDE",
        "district": "南區",
        "floor": "L2",
        "shop_number": "214-221",
        "phone": "2512 8698",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "THE SOUTHSIDE",
        "district": "南區",
        "floor": "GF",
        "shop_number": "G13",
        "phone": "2893 7311",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "元朗廣場",
        "district": "元朗區",
        "floor": "2樓",
        "shop_number": "201-220A",
        "phone": "2777 5380",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "T Town",
        "district": "元朗區",
        "floor": "1樓",
        "shop_number": "S122-124",
        "phone": "2816 1468",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "V Walk",
        "district": "深水埗區",
        "floor": "2樓",
        "shop_number": "35-36",
        "phone": "2878 8773",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "東薈城名店倉",
        "district": "離島區",
        "floor": "1樓",
        "shop_number": "117",
        "phone": "2868 0077",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "新都城中心",
        "district": "西貢區",
        "floor": "1樓",
        "shop_number": "1055-1062",
        "phone": "2311 2823",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "muji_app",
        "mall_name": "新都城中心",
        "district": "西貢區",
        "floor": "1樓",
        "shop_number": "1050-53",
        "phone": "3971 3261",
        "store_name": "無印良品",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "新港城中心 MOSTown",
        "district": "沙田區",
        "floor": "3樓",
        "shop_number": "3025-29",
        "phone": "2146 6658",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "yuu",
        "mall_name": "新港城中心 MOSTown",
        "district": "沙田區",
        "floor": "2樓",
        "shop_number": "2108",
        "phone": "2633 6674",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "信德中心",
        "district": "中西區",
        "floor": "2樓",
        "shop_number": "223",
        "phone": "2858 6672",
        "store_name": "萬寧",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "樂富廣場",
        "district": "九龍城區",
        "floor": "1樓",
        "shop_number": "1151-1156",
        "phone": "2337 3837",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "荷里活廣場",
        "district": "黃大仙區",
        "floor": "地下",
        "shop_number": "G101",
        "phone": "2955 4100",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "uniqlo_app",
        "mall_name": "北角匯",
        "district": "東區",
        "floor": "1-2樓",
        "shop_number": "121-123,201,221-223",
        "phone": "2907 8806",
        "store_name": "UNIQLO",
    },
    {
        "chain_id": "yuu",
        "mall_name": "杏花新城",
        "district": "東區",
        "floor": "L1",
        "shop_number": "157-159",
        "phone": "2976 5694",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "黃大仙中心",
        "district": "黃大仙區",
        "floor": "UG",
        "shop_number": "UG23",
        "phone": "2350 1453",
        "store_name": "萬寧",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "黃大仙中心",
        "district": "黃大仙區",
        "floor": "LG",
        "shop_number": "LG2",
        "phone": "2320 3251",
        "store_name": "屈臣氏",
    },
    # ----- 診斷補全：原空商店商場 -----
    {
        "chain_id": "yuu",
        "mall_name": "上水中心購物商場",
        "district": "北區",
        "floor": "2樓",
        "shop_number": "2077D-H",
        "phone": "2787 7202",
        "store_name": "萬寧",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "上水匯 spot",
        "district": "北區",
        "floor": "1樓",
        "shop_number": "103B,104",
        "phone": "2603 1378",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "yuu",
        "mall_name": "上水廣場",
        "district": "北區",
        "floor": "4樓",
        "shop_number": "419-423",
        "phone": "2480 0034",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "粉嶺名都商場",
        "district": "北區",
        "floor": "2樓",
        "shop_number": "5",
        "phone": "2947 5278",
        "store_name": "萬寧",
    },
    {
        "chain_id": "fortress_club",
        "mall_name": "粉嶺名都商場",
        "district": "北區",
        "floor": "2樓",
        "shop_number": "28C-28D",
        "phone": "2675 0656",
        "store_name": "豐澤",
    },
    {
        "chain_id": "yuu",
        "mall_name": "西九龍中心",
        "district": "深水埗區",
        "floor": "5樓",
        "shop_number": "501B",
        "phone": "2387 8262",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "昇悅商場",
        "district": "深水埗區",
        "floor": "1樓",
        "shop_number": "130,132",
        "phone": "2204 4930",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "將軍澳中心 Park Central",
        "district": "西貢區",
        "floor": "地下",
        "shop_number": "G33",
        "phone": "3417 4813",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "K11購物藝術館",
        "district": "油尖旺區",
        "floor": "地庫1層",
        "shop_number": "B109-B110",
        "phone": "3122 4037",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "海怡廣場",
        "district": "南區",
        "floor": "東翼 地下",
        "shop_number": "G05",
        "phone": "2518 7767",
        "store_name": "萬寧",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "海怡廣場",
        "district": "南區",
        "floor": "1樓",
        "shop_number": "112-113",
        "phone": "2871 0782",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "yuu",
        "mall_name": "綠楊坊",
        "district": "荃灣區",
        "floor": "平台",
        "shop_number": "P11A-P11B",
        "phone": "2492 3224",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "D·PARK 愉景新城",
        "district": "荃灣區",
        "floor": "2樓",
        "shop_number": "2050",
        "phone": "2889 4608",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "屯門時代廣場",
        "district": "屯門區",
        "floor": "南翼 3樓",
        "shop_number": "8,39",
        "phone": "2441 7153",
        "store_name": "萬寧",
    },
    {
        "chain_id": "yuu",
        "mall_name": "錦薈坊",
        "district": "屯門區",
        "floor": "3樓",
        "shop_number": "353",
        "phone": "2761 0298",
        "store_name": "萬寧",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "合和中心",
        "district": "灣仔區",
        "floor": "3樓",
        "shop_number": "301-306",
        "phone": "2866 2526",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "+WOO 嘉湖",
        "district": "元朗區",
        "floor": "一期 地下",
        "shop_number": "G73A,G74,G75",
        "phone": "2796 8003",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "沙田中心",
        "district": "沙田區",
        "floor": "L3",
        "shop_number": "52A,52B1",
        "phone": "2670 9733",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "愉景灣廣場 DB Plaza",
        "district": "離島區",
        "floor": "1樓",
        "shop_number": "135",
        "phone": "2987 4089",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "香港仔中心商場",
        "district": "南區",
        "floor": "地下",
        "shop_number": "6C",
        "phone": "2814 8319",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "西九龍中心",
        "district": "深水埗區",
        "floor": "2樓",
        "shop_number": "205-206",
        "phone": "2360 0923",
        "store_name": "屈臣氏",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "D·PARK 愉景新城",
        "district": "荃灣區",
        "floor": "1樓",
        "shop_number": "1014-1015",
        "phone": "2661 5510",
        "store_name": "屈臣氏",
    },
    # ----- 補齊最後 12 個空白商場（官方目錄／QTS／品牌官網核實） -----
    # 置地廣場
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "置地廣場",
        "district": "中西區",
        "floor": "3樓",
        "shop_number": "305-306",
        "phone": "3596 7836",
        "store_name": "星巴克",
    },
    # K11 MUSEA
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "K11 MUSEA",
        "district": "油尖旺區",
        "floor": "B1",
        "shop_number": "B107A",
        "phone": "2782 3928",
        "store_name": "星巴克",
    },
    {
        "chain_id": "yuu",
        "mall_name": "K11 MUSEA",
        "district": "油尖旺區",
        "floor": "B2",
        "shop_number": "B201-01B",
        "phone": "2793 1047",
        "store_name": "萬寧",
    },
    # OP Mall 海之戀商場
    {
        "chain_id": "fairwood_app",
        "mall_name": "OP Mall 海之戀商場",
        "district": "荃灣區",
        "floor": "3樓",
        "shop_number": "3001,3006",
        "phone": "2856 4020",
        "store_name": "大快活",
    },
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "OP Mall 海之戀商場",
        "district": "荃灣區",
        "floor": "地下",
        "shop_number": "G17",
        "phone": "2675 6388",
        "store_name": "星巴克",
    },
    # 中環街市
    {
        "chain_id": "pizza_hut_rewards",
        "mall_name": "中環街市",
        "district": "中西區",
        "floor": "地下",
        "shop_number": "G20-G21",
        "phone": "6161 9882",
        "store_name": "必勝客",
    },
    # 赤柱廣場
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "赤柱廣場",
        "district": "南區",
        "floor": "地下",
        "shop_number": "G01",
        "phone": "2871 3321",
        "store_name": "星巴克",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "赤柱廣場",
        "district": "南區",
        "floor": "2樓",
        "shop_number": "201-203",
        "phone": "2813 8520",
        "store_name": "百佳",
    },
    {
        "chain_id": "pizza_hut_rewards",
        "mall_name": "赤柱廣場",
        "district": "南區",
        "floor": "1樓",
        "shop_number": "101",
        "phone": "2538 7138",
        "store_name": "必勝客",
    },
    # 數碼港商場
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "數碼港商場",
        "district": "南區",
        "floor": "3樓",
        "shop_number": "316",
        "phone": "2989 9592",
        "store_name": "星巴克",
    },
    {
        "chain_id": "moneyback",
        "mall_name": "數碼港商場",
        "district": "南區",
        "floor": "1樓",
        "shop_number": "3",
        "phone": "2989 6030",
        "store_name": "百佳",
    },
    # 大埔廣場
    {
        "chain_id": "yuu",
        "mall_name": "大埔廣場",
        "district": "大埔區",
        "floor": "2樓",
        "shop_number": "32",
        "phone": "2667 7951",
        "store_name": "惠康",
    },
    # 葵涌廣場
    {
        "chain_id": "cafe_de_coral_club100",
        "mall_name": "葵涌廣場",
        "district": "葵青區",
        "floor": "1樓",
        "shop_number": "B13-B18",
        "phone": "2410 0313",
        "store_name": "大家樂",
    },
    {
        "chain_id": "samgor_spicy_club",
        "mall_name": "葵涌廣場",
        "district": "葵青區",
        "floor": "1樓",
        "shop_number": "93",
        "phone": "2669 3623",
        "store_name": "譚仔三哥米線",
    },
    # 碧海藍天商場
    {
        "chain_id": "aeon_member",
        "mall_name": "碧海藍天商場",
        "district": "深水埗區",
        "floor": "地下至2樓",
        "shop_number": "G-2",
        "phone": "3120 7188",
        "store_name": "AEON",
    },
    # 愉景灣北商場 DB North Plaza
    {
        "chain_id": "yuu",
        "mall_name": "愉景灣北商場 DB North Plaza",
        "district": "離島區",
        "floor": "地下",
        "shop_number": "G11",
        "phone": "2947 9092",
        "store_name": "Market Place",
    },
    {
        "chain_id": "yuu",
        "mall_name": "愉景灣北商場 DB North Plaza",
        "district": "離島區",
        "floor": "LG",
        "shop_number": "LG21",
        "phone": "2608 2712",
        "store_name": "7-Eleven",
    },
    # 合和商場（Hopewell Hotel．Mall；QTS 列合和中心同址 3 樓）
    {
        "chain_id": "starbucks_rewards",
        "mall_name": "合和商場",
        "district": "灣仔區",
        "floor": "3樓",
        "shop_number": "317-319",
        "phone": "3527 3900",
        "store_name": "星巴克",
    },
]


def rematerialize() -> None:
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
    malls_path = ROOT / "data" / "malls-registry.json"
    reference_time = datetime.now(timezone.utc).astimezone()
    existing = [
        o for raw in load_json(discounts_path).get("offers", []) if (o := offer_from_json(raw))
    ]
    # Drop previous chain expansions and any non-authentic store rows that may
    # still linger from older JSON (offer_from_json already filters via validate).
    base = [o for o in existing if o.source_name != "chain_store_offers"]
    malls = [m for raw in load_json(malls_path).get("malls", []) if (m := mall_from_json(raw))]
    known = {(m.district, m.mall_name) for m in malls}
    overrides = load_mall_overrides(ROOT / "data" / "mall_overrides.json", known, reference_time)
    chains = load_chain_store_offers(CHAIN_PATH, known, reference_time)
    offers = merge_offers(base, overrides + chains, reference_time)
    write_outputs(discounts_path, malls_path, offers, malls)
    print(f"rematerialized offers={len(offers)} verified_chain={len(chains)}")


def main() -> None:
    payload = json.loads(CHAIN_PATH.read_text(encoding="utf-8"))
    chains = payload.get("chains", [])
    presence_in = payload.get("presence", [])

    verified_by_mall = {(row["chain_id"], row["mall_name"]): row for row in VERIFIED_PINS}

    pending: list[dict] = []
    seen_pending: set[tuple[str, str, str]] = set()
    for row in presence_in:
        chain_id = str(row.get("chain_id", "")).strip()
        mall = str(row.get("mall_name", "")).strip()
        shop = str(row.get("shop_number", "")).strip()
        if not chain_id or not mall:
            continue
        # Verified pins fully replace any legacy row for the same chain+mall.
        if (chain_id, mall) in verified_by_mall:
            continue
        key = (chain_id, mall, shop)
        if key in seen_pending:
            continue
        seen_pending.add(key)
        item = {
            "chain_id": chain_id,
            "mall_name": mall,
            "district": str(row.get("district", "")).strip(),
            "floor": str(row.get("floor") or "").strip(),
            "shop_number": shop,
            "verification_status": VERIFICATION_PENDING,
        }
        phone = str(row.get("phone") or "").strip()
        if phone:
            item["phone"] = phone
        store_name = str(row.get("store_name") or "").strip()
        if store_name:
            item["store_name"] = store_name
        pending.append(item)

    verified_rows = [
        {**pin, "verification_status": VERIFICATION_VERIFIED} for pin in VERIFIED_PINS
    ]
    cleaned = verified_rows + pending
    cleaned.sort(
        key=lambda r: (
            0 if r.get("verification_status") == VERIFICATION_VERIFIED else 1,
            r.get("chain_id", ""),
            r.get("district", ""),
            r.get("mall_name", ""),
            r.get("shop_number", ""),
        )
    )

    verified_n = sum(1 for r in cleaned if presence_is_verified(r))
    pending_n = len(cleaned) - verified_n
    payload["presence"] = cleaned
    payload["_comment"] = (
        "連鎖商店／集團會員常態禮遇對照。"
        "僅 verification_status=verified 且樓層／鋪號／電話齊全者會注入 discounts／前端；"
        "其餘列標記為 pending（待核實）並被系統過濾。"
    )
    payload["_authenticity_policy"] = (
        "store offers require store_name + floor + shop_number + phone + "
        "offer content + validity dates; placeholders are forbidden"
    )
    CHAIN_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"chains={len(chains)} presence={len(cleaned)} "
        f"verified={verified_n} pending={pending_n}"
    )
    rematerialize()


if __name__ == "__main__":
    main()
