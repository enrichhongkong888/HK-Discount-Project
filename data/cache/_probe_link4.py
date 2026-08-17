# -*- coding: utf-8 -*-
import httpx
import re
import json
from pathlib import Path

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

# Deeper Link REIT properties API body from site JS
# Also try consumer LinkHK mobile endpoints often used by apps.
urls = [
    ("POST", "https://www.linkreit.com/api/PropertiesFilter/Filter", {
        "Language": "en",
        "Region": "",
        "PropertyType": "",
        "Keyword": "",
        "PageIndex": 1,
        "PageSize": 50,
    }),
    ("POST", "https://www.linkreit.com/api/PropertiesFilter/Filter", {
        "language": "en",
        "pageIndex": 0,
        "pageSize": 50,
    }),
    ("GET", "https://www.linkreit.com/api/PropertiesFilter/GetRegions", None),
    ("GET", "https://www.linkreit.com/api/PropertiesFilter/GetPropertyTypes", None),
    ("GET", "https://www.linkhk.com/tc/promotion/ajax", None),
    ("GET", "https://www.linkhk.com/data/promotions.json", None),
    ("GET", "https://www.linkhk.com/assets/data/promotions.json", None),
    ("GET", "https://www.linkhk.com/App_Data/promotions.json", None),
]

with httpx.Client(headers={**headers, "Content-Type": "application/json", "Referer": "https://www.linkreit.com/en/business/properties/", "Origin": "https://www.linkreit.com"}, follow_redirects=True, timeout=30.0) as client:
    # scrape properties page scripts for API payload shape
    page = client.get("https://www.linkreit.com/en/business/properties/", headers={**headers, "Accept": "text/html"}).text
    Path("data/cache/_linkreit_props.html").write_text(page[:80000], encoding="utf-8")
    for pat in [r"PropertiesFilter[^\"']*", r"/api/[^\"']+", r"pageSize[^,]{0,40}", r"Filter\([^)]*\)"]:
        hits = re.findall(pat, page, flags=re.I)
        if hits:
            print(pat, hits[:10])

    for method, url, body in urls:
        try:
            if method == "GET":
                r = client.get(url)
            else:
                r = client.post(url, json=body)
            print("===", method, r.status_code, r.headers.get("content-type","")[:40], url)
            print(r.text[:220].replace("\n", " "))
        except Exception as exc:
            print("FAIL", url, exc)

# Try mall microsites for JSON endpoints via require.js config
with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
    for base in ["https://www.lokfuplaza.com", "https://www.stanleyplaza.com"]:
        for path in [
            "/js/main.js",
            "/js/config.js",
            "/scripts/main.js",
            "/tc/shopping/js/main.js",
            "/App_Plugins/Directory/directory.js",
        ]:
            try:
                r = client.get(base + path)
                if r.status_code == 200 and "html" not in r.headers.get("content-type",""):
                    print("JS", r.status_code, base+path, len(r.text))
                    apis = re.findall(r"[\"'](/[^\"']*(?:api|shop|directory|promo)[^\"']*)[\"']", r.text, flags=re.I)
                    print("  apis", sorted(set(apis))[:20])
            except Exception as exc:
                print("js fail", base+path, exc)
