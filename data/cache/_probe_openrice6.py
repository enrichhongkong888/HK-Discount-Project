# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import urlencode
from pathlib import Path

ua = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
headers = {
    "User-Agent": ua,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
    "Origin": "https://www.openrice.com",
}

malls = ["葵涌廣場", "大埔廣場", "西九龍中心", "太古城中心", "朗豪坊", "Kwai Chung Plaza", "Festival Walk"]

with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    for mall in malls:
        params = {
            "uiLang": "zh",
            "regionId": "1",
            "whatwhere": mall,
            "rows": "20",
            "startAt": "0",
            "sortBy": "ORScoreDesc",
        }
        url = "https://www.openrice.com/api/v2/search?" + urlencode(params)
        data = client.get(url).json()
        pr = data.get("paginationResult") or {}
        results = pr.get("results") or []
        with_promo = sum(1 for r in results if r.get("promotions") or r.get("coupons") or r.get("bizCoupons"))
        phones = sum(1 for r in results if r.get("phones"))
        floors = sum(1 for r in results if r.get("floor"))
        print(f"{mall!r}: count={pr.get('count')} n={len(results)} phones={phones} floors={floors} promoish={with_promo}")
        if results:
            Path("data/cache/_openrice_poi.json").write_text(
                json.dumps(results[0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            # show one promotions structure
            for r in results:
                if r.get("promotions"):
                    print("  promo sample", json.dumps(r.get("promotions"), ensure_ascii=False)[:300])
                    print("  phones", r.get("phones"), "floor", r.get("floor"), "mall", r.get("mallName"), "addr", r.get("address"))
                    break
