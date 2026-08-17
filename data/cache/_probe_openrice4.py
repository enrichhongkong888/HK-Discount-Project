# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import quote, urlencode
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

variants = [
    {"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "10", "start": "0"},
    {"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "10", "startAt": "0"},
    {"uiLang": "zh", "regionId": "1", "whatWhere": "葵涌廣場", "rows": "10", "startAt": "0"},
    {"uiLang": "zh", "regionId": "1", "keywords": "葵涌廣場", "rows": "10", "startAt": "0"},
    {"uiLang": "zh", "regionId": "1", "districtId": "", "landmarkId": "", "rows": "5", "startAt": "0", "whatwhere": "Kwai Chung Plaza"},
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
    for params in variants:
        url = "https://www.openrice.com/api/v2/search?" + urlencode(params)
        r = client.get(url)
        data = r.json()
        pr = data.get("paginationResult") or {}
        results = pr.get("results") or []
        print("---", params)
        print("status", r.status_code, "count", pr.get("count"), "results", len(results), "totalReturn", pr.get("totalReturnCount"))
        if results:
            Path("data/cache/_openrice_poi.json").write_text(
                json.dumps(results[0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print("keys", sorted(results[0].keys())[:50])
            break
