# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import quote
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

url = (
    "https://www.openrice.com/api/v2/search?"
    f"uiLang=zh&regionId=1&whatwhere={quote('葵涌廣場')}&rows=3&startAt=0"
)
with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
    data = client.get(url).json()
    results = (data.get("paginationResult") or {}).get("results") or []
    print("results", len(results))
    if results:
        Path("data/cache/_openrice_poi.json").write_text(
            json.dumps(results[0], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("keys", sorted(results[0].keys()))
        # try nested
        for k, v in results[0].items():
            if isinstance(v, (dict, list)):
                print(k, type(v).__name__, str(v)[:160].replace("\n", " "))
            else:
                print(k, "=", v)

    # try withOffer
    url2 = url + "&withOffer=1"
    data2 = client.get(url2).json()
    results2 = (data2.get("paginationResult") or {}).get("results") or []
    print("withOffer results", len(results2), "count", (data2.get("paginationResult") or {}).get("count"))

    # detail endpoints
    if results:
        poi_id = results[0].get("poiId") or results[0].get("id") or results[0].get("doorSillId")
        print("poi_id", poi_id)
        for detail in [
            f"https://www.openrice.com/api/v2/pois/{poi_id}?uiLang=zh",
            f"https://www.openrice.com/api/v2/poi/{poi_id}?uiLang=zh",
            f"https://www.openrice.com/api/v2/restaurant/{poi_id}?uiLang=zh",
            f"https://www.openrice.com/api/v2/offers?poiId={poi_id}&uiLang=zh",
        ]:
            r = client.get(detail)
            print("DETAIL", r.status_code, detail, r.text[:180].replace("\n", " "))
