# -*- coding: utf-8 -*-
import httpx
import json
import re
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

with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    # get a HK poiId
    params = {"uiLang": "zh", "regionId": "0", "whatwhere": "朗豪坊", "rows": "5", "startAt": "0", "sortBy": "ORScoreDesc"}
    results = (client.get("https://www.openrice.com/api/v2/search?" + urlencode(params)).json().get("paginationResult") or {}).get("results") or []
    poi_id = results[0]["poiId"]
    print("poi", poi_id, results[0]["name"])

    endpoints = [
        f"https://www.openrice.com/api/v2/pois/{poi_id}?uiLang=zh&regionId=0",
        f"https://www.openrice.com/api/v2/poi/{poi_id}?uiLang=zh",
        f"https://www.openrice.com/api/v2/restaurant/get?poiId={poi_id}&uiLang=zh",
        f"https://www.openrice.com/api/v2/offers?poiId={poi_id}&uiLang=zh&regionId=0",
        f"https://www.openrice.com/api/v2/pois/{poi_id}/offers?uiLang=zh",
        f"https://www.openrice.com/api/v2/pois/{poi_id}/promotions?uiLang=zh",
        f"https://www.openrice.com/api/v2/search?uiLang=zh&regionId=0&poiId={poi_id}&rows=1&startAt=0",
        f"https://www.openrice.com/api/v2/search?uiLang=zh&regionId=0&whatwhere=朗豪坊&rows=20&startAt=0&offerFilter=true",
        f"https://www.openrice.com/api/v2/search?uiLang=zh&regionId=0&whatwhere=朗豪坊&rows=20&startAt=0&withOffer=1&offerFilter=1",
    ]
    for url in endpoints:
        r = client.get(url)
        ct = r.headers.get("content-type", "")
        print("===", r.status_code, ct[:35], url[-70:])
        text = r.text
        print(text[:180].replace("\n", " "))
        if "application/json" in ct:
            try:
                data = r.json()
            except Exception:
                continue
            blob = json.dumps(data, ensure_ascii=False)
            for key in ("promotion", "offer", "coupon", "voucher", "title", "discount"):
                if key in blob.lower():
                    print("  has", key)

# Link: extract script URLs and fetch them
with httpx.Client(headers={"User-Agent": headers["User-Agent"]}, follow_redirects=True, timeout=30.0) as client:
    html = client.get("https://www.linkreit.com/en/business/properties/").text
    scripts = re.findall(r'src="([^"]+\.js[^"]*)"', html)
    print("scripts", scripts[:20])
    for src in scripts:
        if src.startswith("/"):
            src = "https://www.linkreit.com" + src
        if "linkreit" not in src and not src.startswith("http"):
            continue
        try:
            js = client.get(src).text
        except Exception as exc:
            print("js fail", src, exc)
            continue
        if "PropertiesFilter" in js or "pageSize" in js:
            print("HIT", src, len(js))
            # extract nearby context
            for m in re.finditer(r".{0,80}PropertiesFilter.{0,120}", js):
                print(" ", m.group(0).replace("\n", " ")[:200])
            for m in re.finditer(r".{0,40}pageSize.{0,80}", js):
                print(" ps", m.group(0).replace("\n", " ")[:160])
                break
