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

# Discover by probing patterns under /linkweb/api/
bases = [
    "https://www.linkhk.com/linkweb/api/shop",
    "https://www.linkhk.com/linkweb/api/shops",
    "https://www.linkhk.com/linkweb/api/shopCentre",
    "https://www.linkhk.com/linkweb/api/shopcentre",
    "https://www.linkhk.com/linkweb/api/centre",
    "https://www.linkhk.com/linkweb/api/centres",
    "https://www.linkhk.com/linkweb/api/promotion",
    "https://www.linkhk.com/linkweb/api/promotions",
    "https://www.linkhk.com/linkweb/api/offer",
    "https://www.linkhk.com/linkweb/api/offers",
    "https://www.linkhk.com/linkweb/api/parkingOffer",
    "https://www.linkhk.com/linkweb/api/parking",
]

queries = [
    "",
    "?lang=tc",
    "?language=zh",
    "?shopCentreId=1",
    "?centreId=1",
    "?id=1",
    "?code=splxc2",
    "?centreCode=splxc2",
    "?mallCode=splxc2",
    "?page=1&size=20",
    "?pageNo=1&pageSize=20",
]

# Known centre codes from URLs
ids = list(range(0, 30))
codes = ["splxc2", "lokfu", "ttown", "t-town", "templemall", "wts", "wkc", "lfp"]

with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    # shop/{n}
    for n in [1, 2, 10, 100, 1000]:
        url = f"https://www.linkhk.com/linkweb/api/shop/{n}"
        r = client.get(url)
        print("shop/id", n, r.status_code, r.text[:180].replace("\n", " "))

    for base in bases:
        for q in ["", "?lang=tc", "?shopCentreId=1", "?centreId=1", "?code=splxc2"]:
            url = base + q
            r = client.get(url)
            if r.status_code == 404 and not r.text.strip():
                continue
            ct = r.headers.get("content-type", "")
            if "json" in ct or r.text.strip().startswith("{") or r.text.strip().startswith("["):
                print("HIT", r.status_code, url)
                print(" ", r.text[:300].replace("\n", " "))
            elif r.status_code not in (404,):
                print("OTHER", r.status_code, url, r.text[:120].replace("\n", " "))

    # POST variants
    for url, body in [
        ("https://www.linkhk.com/linkweb/api/shop/list", {"shopCentreId": 1, "lang": "tc"}),
        ("https://www.linkhk.com/linkweb/api/shop/list", {"centreId": 1}),
        ("https://www.linkhk.com/linkweb/api/shop/search", {"keyword": "AEON"}),
        ("https://www.linkhk.com/linkweb/api/promotion/list", {"lang": "tc"}),
        ("https://www.linkhk.com/linkweb/api/promotion/search", {"lang": "tc", "page": 1}),
        ("https://www.linkhk.com/linkweb/api/shopCentre/list", {"lang": "tc"}),
    ]:
        r = client.post(url, json=body)
        print("POST", r.status_code, url, body, r.text[:220].replace("\n", " "))
