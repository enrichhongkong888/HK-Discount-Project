# -*- coding: utf-8 -*-
import httpx
import json
from pathlib import Path

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
headers = {
    "User-Agent": ua,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.linkhk.com/tc/",
    "Origin": "https://www.linkhk.com",
}

targets = ("樂富", "黃大仙", "T Town", "赤柱", "Stanley", "Temple", "Lok Fu", "天水圍")

with httpx.Client(headers=headers, follow_redirects=True, timeout=40.0) as client:
    found = []
    for i in range(1, 250):
        r = client.get(f"https://www.linkhk.com/linkweb/api/shopCentre/{i}")
        if r.status_code != 200:
            continue
        data = r.json().get("data") or {}
        title = (data.get("seoTitleTc") or data.get("seoTitleEn") or "").strip()
        if not title:
            continue
        hit = any(t.lower() in title.lower() for t in targets)
        if hit or i in (3, 4, 7):
            print(i, title)
            found.append((i, title, data))
            # inspect nested lists
            for key in ("promotions", "shop", "dine", "market", "mallInfo", "parkingVacancy"):
                val = data.get(key)
                if val:
                    print(" ", key, type(val).__name__, str(val)[:200].replace("\n", " "))

    # dump Lok Fu full
    lokfu = client.get("https://www.linkhk.com/linkweb/api/shopCentre/7").json()
    Path("data/cache/_link_lokfu.json").write_text(
        json.dumps(lokfu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    data = lokfu.get("data") or {}
    print("lokfu keys with data:")
    for k, v in data.items():
        if v not in (None, "", [], {}):
            print(" ", k, type(v).__name__, str(v)[:180].replace("\n", " "))

    # Try shop listing endpoints with numeric centre id 7
    for path in [
        "shop/7",
        "shops/7",
        "shopCentre/7/shop",
        "shopCentre/7/shops",
        "shopCentre/7/promotion",
        "shopCentre/7/promotions",
        "promotion/7",
        "promotions/7",
    ]:
        url = "https://www.linkhk.com/linkweb/api/" + path
        r = client.get(url)
        print("GET", path, r.status_code, r.text[:160].replace("\n", " "))
        r = client.post(url, json={"lang": "tc"})
        print("POST", path, r.status_code, r.text[:160].replace("\n", " "))
