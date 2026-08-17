# -*- coding: utf-8 -*-
import httpx
import re
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

candidates = [
    "https://www.linkhk.com/linkweb/api/",
    "https://www.linkhk.com/linkweb/api/shopCentre",
    "https://www.linkhk.com/linkweb/api/ShopCentre",
    "https://www.linkhk.com/linkweb/api/shopCentres",
    "https://www.linkhk.com/linkweb/api/promotion",
    "https://www.linkhk.com/linkweb/api/promotions",
    "https://www.linkhk.com/linkweb/api/Promotion/List",
    "https://www.linkhk.com/linkweb/api/Promotion/GetList",
    "https://www.linkhk.com/linkweb/api/shop/list",
    "https://www.linkhk.com/linkweb/api/Shop/List",
    "https://www.linkhk.com/linkweb/api/ShopCentre/GetList",
    "https://www.linkhk.com/linkweb/api/ShopCentre/List",
    "https://www.linkhk.com/linkweb/api/ShopCentre/Get?code=splxc2",
    "https://www.linkhk.com/linkweb/api/ShopCentre/Detail?code=splxc2",
    "https://www.linkhk.com/linkweb/api/file/_T/ShopCentrePhoto/splxc2/",
    "https://www.linkhk.com/linkweb/api/offer/list",
    "https://www.linkhk.com/linkweb/api/Offer/List",
    "https://www.linkhk.com/linkweb/api/parking",
    "https://www.linkhk.com/linkweb/api/Parking/Get",
    # common codes from registry
    "https://www.linkhk.com/linkweb/api/ShopCentre/GetShops?code=lokfu",
    "https://www.linkhk.com/linkweb/api/ShopCentre/GetShops?centreCode=splxc2",
    "https://www.linkhk.com/linkweb/api/v1/centres",
    "https://www.linkhk.com/linkweb/api/v1/promotions",
]

# Also scrape stanley/link pages for more linkweb paths
with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
    for page in [
        "https://www.stanleyplaza.com/tc/shopping",
        "https://www.linkhk.com/en/shopCentre/splxc2",
        "https://www.linkhk.com/tc/",
    ]:
        html = client.get(page, headers={**headers, "Accept": "text/html"}).text
        hits = sorted(set(re.findall(r"https?://www\.linkhk\.com/linkweb/api/[^\"'\s<>#]+", html)))
        print("page", page, "linkweb", hits[:30])
        # also relative
        rel = sorted(set(re.findall(r"/linkweb/api/[^\"'\s<>#]+", html)))
        print(" rel", rel[:30])

    for url in candidates:
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print("===", r.status_code, ct[:45], url)
            print(" ", r.text[:200].replace("\n", " "))
        except Exception as exc:
            print("FAIL", url, exc)
