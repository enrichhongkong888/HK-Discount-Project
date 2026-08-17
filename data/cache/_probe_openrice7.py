# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import urlencode
from pathlib import Path

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
    "Origin": "https://www.openrice.com",
}

params = {
    "uiLang": "zh",
    "regionId": "0",
    "whatwhere": "朗豪坊",
    "rows": "20",
    "startAt": "0",
    "sortBy": "ORScoreDesc",
}
with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    data = client.get("https://www.openrice.com/api/v2/search?" + urlencode(params)).json()
    results = (data.get("paginationResult") or {}).get("results") or []
    Path("data/cache/_openrice_poi.json").write_text(
        json.dumps(results[:3], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("n", len(results), "count", (data.get("paginationResult") or {}).get("count"))
    for r in results[:5]:
        print("---", r.get("name"), "|", r.get("floor"), "|", r.get("mallName"), "|", r.get("mallPhase"))
        print(" addr", r.get("address"))
        print(" phones", r.get("phones"), "promo", bool(r.get("promotions")), "coupons", bool(r.get("coupons")), "biz", bool(r.get("bizCoupons")))
        if r.get("promotions"):
            print(" promotions", json.dumps(r["promotions"], ensure_ascii=False)[:400])
        if r.get("coupons"):
            print(" coupons", json.dumps(r["coupons"], ensure_ascii=False)[:400])
        if r.get("bizCoupons"):
            print(" bizCoupons", json.dumps(r["bizCoupons"], ensure_ascii=False)[:400])

    # withOffer filter
    params2 = dict(params)
    params2["withOffer"] = "true"
    data2 = client.get("https://www.openrice.com/api/v2/search?" + urlencode(params2)).json()
    results2 = (data2.get("paginationResult") or {}).get("results") or []
    print("withOffer n", len(results2), "count", (data2.get("paginationResult") or {}).get("count"))
    for r in results2[:3]:
        print("O", r.get("name"), "promotions", json.dumps(r.get("promotions") or [], ensure_ascii=False)[:250])
