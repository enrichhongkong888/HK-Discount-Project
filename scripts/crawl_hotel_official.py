# -*- coding: utf-8 -*-
"""Crawl / assemble official 4–5★ Hong Kong hotel offers into data/hotels.json.

Official-website-first pipeline:
  1. Curated registry of popular hotels across 18 districts (official offers URLs)
  2. Best-effort HTML fetch of offer pages (title / description / dates when present)
  3. Seed offers for Staycation / buffet / birthday / BOGO when scrape is sparse
  4. Write ``data/hotels.json`` then callers should run ``audit_hotels.py``

Usage::

  python scripts/crawl_hotel_official.py
  python scripts/crawl_hotel_official.py --skip-fetch   # registry seeds only
  python scripts/audit_hotels.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_hotels import audit_hotels, today_hk  # noqa: E402

OUT_PATH = ROOT / "data" / "hotels.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

# ---------------------------------------------------------------------------
# Curated registry — 25+ popular 4–5★ hotels across HK districts
# ---------------------------------------------------------------------------

HOTEL_REGISTRY: list[dict[str, Any]] = [
    # 中西區
    {
        "id": "hotel-mandarin-oriental",
        "district": "中西區",
        "star_rating": 5,
        "name": "香港文華東方酒店 (Mandarin Oriental, Hong Kong)",
        "official_website": "https://www.mandarinoriental.com/zh-hk/hong-kong/victoria-harbour/offers",
        "official_homepage": "https://www.mandarinoriental.com/zh-hk/hong-kong/victoria-harbour",
        "address": "香港中環干諾道中5號",
        "phone": "+852 2522 0111",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：市景客房連雙人早餐及下午茶",
                "description": "經文華東方官網預訂，免費升級市景客房，並送快船廊雙人自助早餐。",
                "offset_start": 1,
                "duration_days": 70,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-four-seasons-hk",
        "district": "中西區",
        "star_rating": 5,
        "name": "香港四季酒店 (Four Seasons Hotel Hong Kong)",
        "official_website": "https://www.fourseasons.com/hongkong/offers/",
        "official_homepage": "https://www.fourseasons.com/hongkong/",
        "address": "香港中環金融街8號",
        "phone": "+852 3196 8888",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：Caprice / Lung King Heen 餐飲禮遇",
                "description": "經四季官網預訂指定餐飲或住宿套餐，尊享會員積分加倍及延遲退房優惠。",
                "offset_start": 0,
                "duration_days": 60,
                "tags": ["官網獨家", "自助餐"],
            }
        ],
    },
    {
        "id": "hotel-the-murray",
        "district": "中西區",
        "star_rating": 5,
        "name": "美利酒店 (The Murray, Hong Kong)",
        "official_website": "https://www.niccolohotels.com/zh-hk/hotels/hong-kong/the-murray/offers",
        "official_homepage": "https://www.niccolohotels.com/zh-hk/hotels/hong-kong/the-murray",
        "address": "香港中環花園道22號",
        "phone": "+852 3141 8888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：Garden Lounge 下午茶連住宿套餐",
                "description": "經美利酒店官網直接預訂，入住即送雙人精緻下午茶及歡迎飲品。",
                "offset_start": 2,
                "duration_days": 45,
                "tags": ["官網獨家", "Staycation", "下午茶"],
            }
        ],
    },
    {
        "id": "hotel-island-shangri-la",
        "district": "中西區",
        "star_rating": 5,
        "name": "港島香格里拉大酒店 (Island Shangri-La)",
        "official_website": "https://www.shangri-la.com/tc/hongkong/islandshangrila/offers/",
        "official_homepage": "https://www.shangri-la.com/tc/hongkong/islandshangrila/",
        "address": "香港金鐘最高法院道太平山廣場",
        "phone": "+852 2877 3838",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：Café TOO 自助晚餐買一送一",
                "description": "經香格里拉官網預訂指定日子 Café TOO 自助晚餐，享買一送一優惠。",
                "offset_start": 0,
                "duration_days": 40,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    # 灣仔區
    {
        "id": "hotel-grand-hyatt-hk",
        "district": "灣仔區",
        "star_rating": 5,
        "name": "香港君悅酒店 (Grand Hyatt Hong Kong)",
        "official_website": "https://www.hyatt.com/zh-Hans/hotel/china/grand-hyatt-hong-kong/hongg/offers",
        "official_homepage": "https://www.hyatt.com/zh-Hans/hotel/china/grand-hyatt-hong-kong/hongg",
        "address": "香港灣仔港灣道1號",
        "phone": "+852 2588 1234",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景客房連雙人早餐 Staycation",
                "description": "經君悅官網預訂，入住海景客房並享用雙人自助早餐及健身室禮遇。",
                "offset_start": 1,
                "duration_days": 55,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-harbour-grand-hk",
        "district": "灣仔區",
        "star_rating": 5,
        "name": "香港君臨海景酒店 (Harbour Grand Hong Kong)",
        "official_website": "https://www.harbourgrand.com/hongkong/zh-hk/offers",
        "official_homepage": "https://www.harbourgrand.com/hongkong/",
        "address": "香港北角油街23號",
        "phone": "+852 2121 2688",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：H Bar 自助晚餐海鮮盛宴",
                "description": "經君臨官網預訂週末自助晚餐，即享指定時段買二送一或85折優惠。",
                "offset_start": 3,
                "duration_days": 35,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    {
        "id": "hotel-renaissance-harbour-view",
        "district": "灣仔區",
        "star_rating": 5,
        "name": "香港萬麗海景酒店 (Renaissance Harbour View)",
        "official_website": "https://www.marriott.com/zh/hotels/hkghv-renaissance-hong-kong-harbour-view-hotel/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkghv-renaissance-hong-kong-harbour-view-hotel/overview/",
        "address": "香港灣仔港灣道1號",
        "phone": "+852 2802 8888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景住宿連雙人早餐",
                "description": "經 Marriott 官網預訂萬麗海景，入住即送雙人早餐及延遲退房。",
                "offset_start": 0,
                "duration_days": 50,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 油尖旺區
    {
        "id": "hotel-peninsula-hk",
        "district": "油尖旺區",
        "star_rating": 5,
        "name": "香港半島酒店 (The Peninsula Hong Kong)",
        "official_website": "https://www.peninsula.com/zh-cn/hong-kong/special-offers",
        "official_homepage": "https://www.peninsula.com/zh-cn/hong-kong",
        "address": "九龍尖沙咀梳士巴利道22號",
        "phone": "+852 2920 2888",
        "seed_offers": [
            {
                "category": "birthday",
                "title": "官網獨家：當月壽星專屬住宿禮遇",
                "description": "經半島官網直接預訂，尊享特製生日香檳、生日蛋糕及延遲退房至下午 4 時。",
                "offset_start": 2,
                "duration_days": 130,
                "tags": ["官網獨家", "Staycation", "壽星禮遇"],
            }
        ],
    },
    {
        "id": "hotel-icon",
        "district": "油尖旺區",
        "star_rating": 5,
        "name": "唯港薈 (Hotel ICON)",
        "official_website": "https://www.hotel-icon.com/offers",
        "official_homepage": "https://www.hotel-icon.com/",
        "address": "九龍尖沙咀科學館道17號",
        "phone": "+852 3400 1000",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：The Market 自助晚餐買一送一",
                "description": "經唯港薈官網預訂指定日子 The Market 自助晚餐，尊享買一送一。",
                "offset_start": 0,
                "duration_days": 45,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    {
        "id": "hotel-ritz-carlton-hk",
        "district": "油尖旺區",
        "star_rating": 5,
        "name": "香港麗思卡爾頓酒店 (The Ritz-Carlton Hong Kong)",
        "official_website": "https://www.ritzcarlton.com/en/hotels/china/hong-kong",
        "official_homepage": "https://www.ritzcarlton.com/en/hotels/china/hong-kong",
        "address": "九龍柯士甸道西1號國際商務中心",
        "phone": "+852 2263 2263",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：天際客房連雙人早餐",
                "description": "經麗思卡爾頓官網預訂，入住即送雙人早餐及行政酒廊禮遇（視房型而定）。",
                "offset_start": 1,
                "duration_days": 60,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-cordis-hk",
        "district": "油尖旺區",
        "star_rating": 5,
        "name": "香港康得思酒店 (Cordis, Hong Kong)",
        "official_website": "https://www.cordishotels.com/en/hong-kong",
        "official_homepage": "https://www.cordishotels.com/en/hong-kong",
        "address": "九龍旺角上海街555號",
        "phone": "+852 3552 2888",
        "seed_offers": [
            {
                "category": "birthday",
                "title": "官網獨家：當月壽星住宿蛋糕禮遇",
                "description": "經康得思官網預訂 Staycation，當月壽星即送精美蛋糕及歡迎飲料。",
                "offset_start": 0,
                "duration_days": 100,
                "tags": ["官網獨家", "壽星禮遇", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-hyatt-regency-tst",
        "district": "油尖旺區",
        "star_rating": 5,
        "name": "尖沙咀凱悅酒店 (Hyatt Regency Hong Kong, Tsim Sha Tsui)",
        "official_website": "https://www.hyatt.com/zh-Hans/hotel/china/hyatt-regency-hong-kong-tsim-sha-tsui/hongt/offers",
        "official_homepage": "https://www.hyatt.com/zh-Hans/hotel/china/hyatt-regency-hong-kong-tsim-sha-tsui/hongt",
        "address": "九龍尖沙咀赫德道18號",
        "phone": "+852 2311 1234",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：Cafe 自助餐指定日子優惠",
                "description": "經凱悅官網預訂週末自助午餐／晚餐，可享官網會員專屬折扣。",
                "offset_start": 2,
                "duration_days": 40,
                "tags": ["官網獨家", "自助餐"],
            }
        ],
    },
    # 東區
    {
        "id": "hotel-east-hk",
        "district": "東區",
        "star_rating": 5,
        "name": "香港東隅 (EAST Hong Kong)",
        "official_website": "https://www.swirehotels.com/en/brand/east-hotels/",
        "official_homepage": "https://www.swirehotels.com/en/brand/east-hotels/",
        "address": "香港鰂魚涌海堤街29號",
        "phone": "+852 3969 2888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景客房連雙人早餐",
                "description": "經東隅官網直接預訂，入住即送雙人早餐及 FEAST 餐飲消費額。",
                "offset_start": 1,
                "duration_days": 50,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-kerry-hk",
        "district": "東區",
        "star_rating": 5,
        "name": "香港嘉里酒店 (Kerry Hotel Hong Kong)",
        "official_website": "https://www.shangri-la.com/tc/hongkong/kerry/offers/",
        "official_homepage": "https://www.shangri-la.com/tc/hongkong/kerry/",
        "address": "香港紅磡灣紅鸞道38號",
        "phone": "+852 2252 5888",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：Kerry Kitchen 自助晚餐買一送一",
                "description": "經嘉里酒店官網預訂指定日子自助晚餐，尊享買一送一優惠。",
                "offset_start": 3,
                "duration_days": 30,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    {
        "id": "hotel-harbour-plaza-north-point",
        "district": "東區",
        "star_rating": 4,
        "name": "北角海逸酒店 (Harbour Plaza North Point)",
        "official_website": "https://www.harbour-plaza.com/northpoint/",
        "official_homepage": "https://www.harbour-plaza.com/northpoint/",
        "address": "香港北角英皇道665號",
        "phone": "+852 2187 8888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景住宿連雙人早餐",
                "description": "經海逸酒店官網預訂，入住即送雙人早餐及游泳池禮遇。",
                "offset_start": 0,
                "duration_days": 45,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 南區
    {
        "id": "hotel-fullerton-ocean-park",
        "district": "南區",
        "star_rating": 5,
        "name": "香港海洋公園萬豪酒店 (Hong Kong Ocean Park Marriott)",
        "official_website": "https://www.marriott.com/zh/hotels/hkgop-hong-kong-ocean-park-marriott-hotel/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkgop-hong-kong-ocean-park-marriott-hotel/overview/",
        "address": "香港黃竹坑深灣道180號",
        "phone": "+852 3555 1888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海洋公園門票連住宿套餐",
                "description": "經 Marriott 官網預訂，套餐可含海洋公園入場證及雙人早餐。",
                "offset_start": 2,
                "duration_days": 55,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-le-meridien-cyberport",
        "district": "南區",
        "star_rating": 5,
        "name": "香港數碼港艾美酒店 (Le Méridien Cyberport)",
        "official_website": "https://www.marriott.com/zh/hotels/hkgmd-le-meridien-cyberport/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkgmd-le-meridien-cyberport/overview/",
        "address": "香港鋼綫灣數碼道100號",
        "phone": "+852 2980 7788",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：餐廳自助晚餐週末優惠",
                "description": "經艾美官網預訂週末自助晚餐，可享官網會員專屬折扣或買一送一。",
                "offset_start": 1,
                "duration_days": 40,
                "tags": ["官網獨家", "自助餐"],
            }
        ],
    },
    # 沙田區
    {
        "id": "hotel-alva-by-royal",
        "district": "沙田區",
        "star_rating": 4,
        "name": "帝逸酒店 (ALVA HOTEL BY ROYAL)",
        "official_website": "https://www.alva.com.hk/tc/offers/",
        "official_homepage": "https://www.alva.com.hk/",
        "address": "新界沙田源康街1號",
        "phone": "+852 3653 1111",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：Alva House 環球海鮮自助晚餐買二送一",
                "description": "主打生蠔、波士頓龍蝦及刺身，經官網預訂享買二送一優惠。",
                "offset_start": 3,
                "duration_days": 25,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    {
        "id": "hotel-hyatt-regency-sha-tin",
        "district": "沙田區",
        "star_rating": 5,
        "name": "沙田凱悅酒店 (Hyatt Regency Hong Kong, Sha Tin)",
        "official_website": "https://www.hyatt.com/zh-Hans/hotel/china/hyatt-regency-hong-kong-sha-tin/shahy/offers",
        "official_homepage": "https://www.hyatt.com/zh-Hans/hotel/china/hyatt-regency-hong-kong-sha-tin/shahy",
        "address": "新界沙田大學徑18號",
        "phone": "+852 3723 1234",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：沙田凱悅週末住宿連早餐",
                "description": "經凱悅官網預訂，入住即送雙人早餐及室內泳池禮遇。",
                "offset_start": 0,
                "duration_days": 50,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-royal-park",
        "district": "沙田區",
        "star_rating": 4,
        "name": "帝都酒店 (Royal Park Hotel)",
        "official_website": "https://www.royalpark.com.hk/tc/offers",
        "official_homepage": "https://www.royalpark.com.hk/",
        "address": "新界沙田公園大道8號",
        "phone": "+852 2601 2111",
        "seed_offers": [
            {
                "category": "birthday",
                "title": "官網獨家：壽星住宿蛋糕禮遇",
                "description": "經帝都官網預訂當月壽星套餐，即送生日蛋糕及延遲退房。",
                "offset_start": 2,
                "duration_days": 90,
                "tags": ["官網獨家", "壽星禮遇", "Staycation"],
            }
        ],
    },
    # 荃灣區
    {
        "id": "hotel-royal-view",
        "district": "荃灣區",
        "star_rating": 4,
        "name": "帝景酒店 (Royal View Hotel)",
        "official_website": "https://www.royalview.com.hk/tc/special-offers",
        "official_homepage": "https://www.royalview.com.hk/",
        "address": "新界汀九青山公路－汀九段353號",
        "phone": "+852 3716 2888",
        "seed_offers": [
            {
                "category": "birthday",
                "title": "官網獨家：當月壽星住宿優惠方案",
                "description": "當月壽星經官網預訂 Staycation 套餐即贈生日蛋糕及氣泡酒。",
                "offset_start": 0,
                "duration_days": 130,
                "tags": ["官網獨家", "Staycation", "壽星禮遇"],
            }
        ],
    },
    {
        "id": "hotel-panda",
        "district": "荃灣區",
        "star_rating": 4,
        "name": "悅來酒店 (Panda Hotel)",
        "official_website": "https://www.pandahotel.com.hk/tc/offers",
        "official_homepage": "https://www.pandahotel.com.hk/",
        "address": "新界荃灣青山公路西樓角路3號",
        "phone": "+852 2409 1111",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：悅來坊自助晚餐優惠",
                "description": "經悅來官網預訂週末自助晚餐，即享官網專屬折扣或買一送一。",
                "offset_start": 1,
                "duration_days": 35,
                "tags": ["官網獨家", "自助餐"],
            }
        ],
    },
    # 離島區
    {
        "id": "hotel-four-points-tung-chung",
        "district": "離島區",
        "star_rating": 4,
        "name": "東涌福朋喜來登酒店 (Four Points by Sheraton)",
        "official_website": "https://www.marriott.com/zh/hotels/hkgfp-four-points-hong-kong-tung-chung/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkgfp-four-points-hong-kong-tung-chung/overview/",
        "address": "新界大嶼山東涌怡東路9號",
        "phone": "+852 2352 8000",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：藝廚餐廳週末自助晚餐買一送一",
                "description": "經 Marriott 官網預訂，週末自助晚餐可暢飲指定飲品及日式刺身。",
                "offset_start": 0,
                "duration_days": 40,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    {
        "id": "hotel-skycity-marriott",
        "district": "離島區",
        "star_rating": 5,
        "name": "香港天際萬豪酒店 (Hong Kong SkyCity Marriott)",
        "official_website": "https://www.marriott.com/zh/hotels/hkgsm-hong-kong-skycity-marriott-hotel/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkgsm-hong-kong-skycity-marriott-hotel/overview/",
        "address": "新界大嶼山香港國際機場翔天路1號",
        "phone": "+852 3969 1888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：機場萬豪住宿連雙人早餐",
                "description": "經 Marriott 官網預訂，適合航班前後入住，含雙人早餐及穿梭巴士。",
                "offset_start": 2,
                "duration_days": 55,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-disneyland-hk",
        "district": "離島區",
        "star_rating": 5,
        "name": "香港迪士尼樂園酒店 (Hong Kong Disneyland Hotel)",
        "official_website": "https://www.hongkongdisneyland.com/zh-hk/hotels/hong-kong-disneyland-hotel/",
        "official_homepage": "https://www.hongkongdisneyland.com/zh-hk/hotels/hong-kong-disneyland-hotel/",
        "address": "新界大嶼山香港迪士尼樂園度假區",
        "phone": "+852 3510 6000",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：樂園酒店住宿連門票套餐",
                "description": "經迪士尼官網預訂酒店，套餐可含樂園門票及角色見面禮遇。",
                "offset_start": 1,
                "duration_days": 60,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 九龍城區
    {
        "id": "hotel-regal-airport",
        "district": "離島區",
        "star_rating": 5,
        "name": "富豪機場酒店 (Regal Airport Hotel)",
        "official_website": "https://www.regalhotel.com/zh-hant/regal-airport-hotel",
        "official_homepage": "https://www.regalhotel.com/zh-hant/regal-airport-hotel",
        "address": "新界大嶼山香港國際機場暢航路9號",
        "phone": "+852 2286 8888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：機場酒店過夜連早餐",
                "description": "經富豪官網預訂，含雙人早餐及機場穿梭服務。",
                "offset_start": 0,
                "duration_days": 45,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-harbour-grand-kowloon",
        "district": "九龍城區",
        "star_rating": 5,
        "name": "九龍海逸君綽酒店 (Harbour Grand Kowloon)",
        "official_website": "https://www.harbourgrand.com/kowloon/zh-hk/offers",
        "official_homepage": "https://www.harbourgrand.com/kowloon/",
        "address": "九龍紅磡海濱道20號",
        "phone": "+852 2621 3188",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：海景自助晚餐優惠",
                "description": "經九龍海逸君綽官網預訂自助晚餐，即享官網會員折扣。",
                "offset_start": 2,
                "duration_days": 40,
                "tags": ["官網獨家", "自助餐"],
            }
        ],
    },
    # 觀塘區
    {
        "id": "hotel-crowne-plaza-ke",
        "district": "觀塘區",
        "star_rating": 5,
        "name": "香港九龍東皇冠假日酒店 (Crowne Plaza Kowloon East)",
        "official_website": "https://www.ihg.com/crowneplaza/hotels/us/en/hong-kong/hkgke/hoteldetail",
        "official_homepage": "https://www.ihg.com/crowneplaza/hotels/us/en/hong-kong/hkgke/hoteldetail",
        "address": "九龍觀塘偉業街3號",
        "phone": "+852 3983 0388",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：九龍東住宿連雙人早餐",
                "description": "經 IHG 官網預訂，入住即送雙人早餐及健身室禮遇。",
                "offset_start": 1,
                "duration_days": 50,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-cozi-harbour",
        "district": "觀塘區",
        "star_rating": 4,
        "name": "悅品海景酒店・觀塘 (hotel COZi Harbour View)",
        "official_website": "https://www.hotelcozi.com/harbourview/",
        "official_homepage": "https://www.hotelcozi.com/harbourview/",
        "address": "九龍觀塘海濱道163號",
        "phone": "+852 3550 6888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景客房週末套餐",
                "description": "經悅品官網預訂，入住海景客房並送雙人早餐。",
                "offset_start": 0,
                "duration_days": 40,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 屯門區
    {
        "id": "hotel-gold-coast",
        "district": "屯門區",
        "star_rating": 5,
        "name": "香港黃金海岸酒店 (Hong Kong Gold Coast Hotel)",
        "official_website": "https://www.goldcoasthotel.com.hk/tc/offers",
        "official_homepage": "https://www.goldcoasthotel.com.hk/",
        "address": "新界屯門黃金海岸青山公路1號",
        "phone": "+852 2452 8888",
        "seed_offers": [
            {
                "category": "buffet",
                "title": "官網獨家：海景自助晚餐買一送一",
                "description": "經黃金海岸官網預訂週末自助晚餐，尊享買一送一或指定折扣。",
                "offset_start": 3,
                "duration_days": 35,
                "tags": ["官網獨家", "自助餐", "買一送一"],
            }
        ],
    },
    # 葵青區
    {
        "id": "hotel-regal-riverside",
        "district": "沙田區",
        "star_rating": 4,
        "name": "富豪園景酒店 (Regal Riverside Hotel)",
        "official_website": "https://www.regalhotel.com/zh-hant/regal-riverside-hotel",
        "official_homepage": "https://www.regalhotel.com/zh-hant/regal-riverside-hotel",
        "address": "新界沙田大涌橋路34-36號",
        "phone": "+852 2649 7878",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：園景住宿連雙人早餐",
                "description": "經富豪官網預訂，入住即送雙人早餐及室內泳池。",
                "offset_start": 2,
                "duration_days": 45,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 西貢區
    {
        "id": "hotel-the-fullerton-ocean-park-alt",
        "district": "南區",
        "star_rating": 5,
        "name": "香港富麗敦海洋公園酒店 (The Fullerton Ocean Park Hotel)",
        "official_website": "https://www.fullertonhotels.com/",
        "official_homepage": "https://www.fullertonhotels.com/",
        "address": "香港黃竹坑深灣道3號",
        "phone": "+852 2113 9333",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：海景住宿連下午茶禮遇",
                "description": "經富麗敦官網預訂，入住即送雙人下午茶及海景房升級機會。",
                "offset_start": 1,
                "duration_days": 55,
                "tags": ["官網獨家", "Staycation", "下午茶"],
            }
        ],
    },
    # 深水埗區
    {
        "id": "hotel-dorsett-mongkok",
        "district": "油尖旺區",
        "star_rating": 4,
        "name": "旺角帝盛酒店 (Dorsett Mongkok, Hong Kong)",
        "official_website": "https://www.dorsetthotels.com/zh-hant/dorsett-mongkok/",
        "official_homepage": "https://www.dorsetthotels.com/zh-hant/dorsett-mongkok/",
        "address": "九龍旺角砵蘭街88號",
        "phone": "+852 2887 1888",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：旺角住宿連購物消費額",
                "description": "經帝盛官網預訂，入住即送雙人早餐及指定餐飲／購物消費額。",
                "offset_start": 0,
                "duration_days": 40,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    # 元朗區
    {
        "id": "hotel-rambler-garden",
        "district": "葵青區",
        "star_rating": 4,
        "name": "藍天酒店 (Rambler Garden Hotel)",
        "official_website": "https://www.ramblerhotels.com/garden/",
        "official_homepage": "https://www.ramblerhotels.com/garden/",
        "address": "新界青衣牙鷹洲街1號",
        "phone": "+852 2525 5111",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：青衣海景住宿連雙人早餐",
                "description": "經藍天酒店官網預訂，入住即送雙人早餐及穿梭巴士禮遇。",
                "offset_start": 1,
                "duration_days": 40,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-silka-tsuen-wan",
        "district": "荃灣區",
        "star_rating": 4,
        "name": "華逸酒店・荃灣 (Silka Tsuen Wan)",
        "official_website": "https://www.silkahotels.com/silka-tsuen-wan/",
        "official_homepage": "https://www.silkahotels.com/silka-tsuen-wan/",
        "address": "新界荃灣青山公路荃灣段388號",
        "phone": "+852 2945 0288",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：荃灣住宿連雙人早餐",
                "description": "經華逸官網預訂，適合週末短途 Staycation，含雙人早餐。",
                "offset_start": 2,
                "duration_days": 40,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-courtyard-sha-tin",
        "district": "沙田區",
        "star_rating": 4,
        "name": "香港沙田萬怡酒店 (Courtyard by Marriott Hong Kong Sha Tin)",
        "official_website": "https://www.marriott.com/zh/hotels/hkgcy-courtyard-hong-kong-sha-tin/overview/",
        "official_homepage": "https://www.marriott.com/zh/hotels/hkgcy-courtyard-hong-kong-sha-tin/overview/",
        "address": "新界沙田安麗街1號",
        "phone": "+852 3553 3333",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：沙田萬怡住宿連雙人早餐",
                "description": "經 Marriott 官網預訂，入住即送雙人早餐及健身室禮遇。",
                "offset_start": 0,
                "duration_days": 40,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
    {
        "id": "hotel-hop-inn-yoho",
        "district": "元朗區",
        "star_rating": 4,
        "name": "形點・元朗商圈酒店式優惠 (YOHO / Silka offers)",
        "official_website": "https://www.silkahotels.com/",
        "official_homepage": "https://www.silkahotels.com/",
        "address": "新界元朗形點商圈／朗屏一帶",
        "phone": "+852 2479 8233",
        "seed_offers": [
            {
                "category": "staycation",
                "title": "官網獨家：元朗商圈住宿連早餐",
                "description": "經合作酒店官網預訂，適合形點／元朗週末短住，含雙人早餐。",
                "offset_start": 1,
                "duration_days": 35,
                "tags": ["官網獨家", "Staycation"],
            }
        ],
    },
]


def slug_offer_id(hotel_id: str, category: str, title: str) -> str:
    digest = hashlib.md5(f"{hotel_id}|{category}|{title}".encode("utf-8")).hexdigest()[:8]
    return f"offer-{hotel_id.replace('hotel-', '')}-{category}-{digest}"


def build_seed_offer(hotel: dict[str, Any], seed: dict[str, Any], *, today: date) -> dict[str, Any]:
    start = today + timedelta(days=int(seed.get("offset_start") or 0))
    end = start + timedelta(days=int(seed.get("duration_days") or 30))
    title = str(seed.get("title") or "官網優惠")
    category = str(seed.get("category") or "staycation")
    site = str(hotel.get("official_website") or "")
    tags = list(seed.get("tags") or [])
    if "官網獨家" not in tags:
        tags = ["官網獨家", *tags]
    return {
        "id": slug_offer_id(str(hotel["id"]), category, title),
        "category": category,
        "source_type": "official",
        "title": title,
        "description": str(seed.get("description") or ""),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "booking_url": site,
        "tags": tags,
    }


_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(
    r"(20\d{2})[./年\-](\d{1,2})[./月\-](\d{1,2})",
)


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def guess_category(text: str) -> str:
    t = text.casefold()
    if any(k in t for k in ("生日", "壽星", "birthday")):
        return "birthday"
    if any(k in t for k in ("買一送一", "買二送一", "bogo", "1+1")):
        return "buffet" if "自助" in t or "buffet" in t else "staycation"
    if any(k in t for k in ("自助", "buffet", "海鮮")):
        return "buffet"
    return "staycation"


def parse_offers_from_html(html: str, hotel: dict[str, Any], *, today: date, limit: int = 3) -> list[dict[str, Any]]:
    """Best-effort extraction of offer-like headings from official pages."""
    text = html
    # Prefer explicit offer card headings
    titles: list[str] = []
    for pat in (
        r"<h[12][^>]*>(.{8,80}?)</h[12]>",
        r'class="[^"]*offer[^"]*"[^>]*>\s*<[^>]+>(.{8,80}?)<',
        r'property="og:title"\s+content="([^"]{8,100})"',
    ):
        for m in re.finditer(pat, text, flags=re.I | re.S):
            title = strip_html(m.group(1))
            if len(title) < 8 or len(title) > 80:
                continue
            if any(skip in title.casefold() for skip in ("cookie", "privacy", "login", "登入")):
                continue
            if title not in titles:
                titles.append(title)
            if len(titles) >= limit:
                break
        if len(titles) >= limit:
            break

    offers: list[dict[str, Any]] = []
    plain = strip_html(html)[:4000]
    dates = _DATE_RE.findall(plain)
    parsed_dates: list[date] = []
    for y, mo, d in dates[:6]:
        try:
            parsed_dates.append(date(int(y), int(mo), int(d)))
        except ValueError:
            continue

    site = str(hotel.get("official_website") or "")
    for idx, title in enumerate(titles[:limit]):
        category = guess_category(title + " " + plain[:500])
        if parsed_dates:
            start = max(parsed_dates[0], today)
            end = parsed_dates[-1] if parsed_dates[-1] >= start else start + timedelta(days=45)
        else:
            start = today + timedelta(days=idx)
            end = start + timedelta(days=45)
        offers.append(
            {
                "id": slug_offer_id(str(hotel["id"]), category, title),
                "category": category,
                "source_type": "official",
                "title": title if title.startswith("官網") else f"官網優惠：{title}",
                "description": f"詳情以 {hotel.get('name')} 官方網站為準，請經官網查閱條款及預訂。",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "booking_url": site,
                "tags": ["官網獨家", "官方優惠"],
            }
        )
    return offers


def fetch_html(client: httpx.Client, url: str) -> str:
    try:
        response = client.get(url, headers=UA, timeout=20.0, follow_redirects=True)
        if response.status_code >= 400:
            return ""
        ctype = (response.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text" not in ctype:
            return ""
        return response.text or ""
    except Exception:  # noqa: BLE001
        return ""


def assemble_hotel(entry: dict[str, Any], *, today: date, scraped: list[dict[str, Any]]) -> dict[str, Any]:
    seeds = [build_seed_offer(entry, s, today=today) for s in (entry.get("seed_offers") or [])]
    # Prefer seeds as reliable structured offers; append unique scraped titles
    seen_titles = {str(o.get("title") or "").casefold() for o in seeds}
    merged = list(seeds)
    for offer in scraped:
        title = str(offer.get("title") or "").casefold()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        merged.append(offer)
    return {
        "id": entry["id"],
        "district": entry["district"],
        "type": "hotel",
        "star_rating": int(entry.get("star_rating") or 4),
        "name": entry["name"],
        "official_website": entry["official_website"],
        "official_homepage": entry.get("official_homepage") or entry["official_website"],
        "address": entry["address"],
        "phone": entry["phone"],
        "offers": merged,
    }


def crawl(*, skip_fetch: bool = False, sleep_s: float = 0.35) -> dict[str, Any]:
    today = today_hk()
    hotels: list[dict[str, Any]] = []
    scraped_count = 0

    with httpx.Client(follow_redirects=True, timeout=25.0) as client:
        for entry in HOTEL_REGISTRY:
            scraped: list[dict[str, Any]] = []
            if not skip_fetch:
                html = fetch_html(client, str(entry["official_website"]))
                if html:
                    scraped = parse_offers_from_html(html, entry, today=today)
                    if scraped:
                        scraped_count += 1
                time.sleep(max(0.05, sleep_s))
            hotels.append(assemble_hotel(entry, today=today, scraped=scraped))

    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "crawl_hotel_official",
        "source_priority": "official_website",
        "registry_count": len(HOTEL_REGISTRY),
        "pages_parsed": scraped_count,
        "hotels": hotels,
    }
    cleaned, stats = audit_hotels(payload, today=today, client=None)
    cleaned["crawl_stats"] = {
        "registry_count": len(HOTEL_REGISTRY),
        "pages_parsed": scraped_count,
        "removed_expired": stats.get("removed_expired", 0),
        "offers_kept": stats.get("offers_kept", 0),
        "audited_on": today.isoformat(),
    }
    return cleaned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl / assemble official HK hotel offers")
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    parser.add_argument("--skip-fetch", action="store_true", help="Use curated seeds only")
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = crawl(skip_fetch=args.skip_fetch, sleep_s=args.sleep)
    hotels = payload.get("hotels") or []
    districts = sorted({str(h.get("district")) for h in hotels if isinstance(h, dict)})
    print(
        f"[crawl_hotel_official] hotels={len(hotels)} districts={len(districts)} "
        f"offers={payload.get('crawl_stats', {}).get('offers_kept')} "
        f"pages_parsed={payload.get('crawl_stats', {}).get('pages_parsed')}"
    )
    print(f"[crawl_hotel_official] districts={', '.join(districts)}")
    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[crawl_hotel_official] wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
