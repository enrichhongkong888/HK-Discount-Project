# -*- coding: utf-8 -*-
import httpx
import json
import re
from pathlib import Path

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.linkreit.com/en/business/properties/",
    "Origin": "https://www.linkreit.com",
    "Content-Type": "application/json",
}

candidates = [
    ("GET", "https://www.linkreit.com/api/PropertiesFilter/Filter"),
    ("POST", "https://www.linkreit.com/api/PropertiesFilter/Filter"),
    ("GET", "https://www.linkreit.com/api/ContentSearch/AutoComplete?lang=en&term=T%20Town"),
    ("GET", "https://www.linkhk.com/tc/promotion/?format=json"),
    ("GET", "https://www.lokfuplaza.com/api/shops"),
    ("GET", "https://www.lokfuplaza.com/tc/api/shops"),
    ("GET", "https://www.lokfuplaza.com/umbraco/api/ShopApi/GetShops"),
    ("GET", "https://www.lokfuplaza.com/umbraco/api/Directory/Get"),
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    # Inspect lokfu HTML for API hints
    html = client.get("https://www.lokfuplaza.com/tc/shopping", headers={**headers, "Accept": "text/html"}).text
    Path("data/cache/_lokfu_snip.html").write_text(html[:50000], encoding="utf-8")
    paths = sorted(set(re.findall(r"[\"'](/[^\"']*(?:api|shop|tenant|directory|promo|parking|ajax)[^\"']*)[\"']", html, flags=re.I)))
    print("lokfu paths", paths[:40])
    scripts = re.findall(r"src=[\"']([^\"']+\.js)[\"']", html, flags=re.I)
    print("scripts", scripts[:15])

    for method, url in candidates:
        try:
            if method == "GET":
                r = client.get(url)
            else:
                r = client.post(url, json={"lang": "en", "page": 1, "pageSize": 20})
            ct = r.headers.get("content-type", "")
            print("===", method, r.status_code, ct[:40], url)
            print(r.text[:250].replace("\n", " "))
        except Exception as exc:  # noqa: BLE001
            print("FAIL", method, url, type(exc).__name__, exc)

    # Try PropertiesFilter with form body variations
    for payload in (
        {"Language": "en"},
        {"lang": "tc"},
        {"region": "HK", "lang": "en"},
        {},
    ):
        try:
            r = client.post(
                "https://www.linkreit.com/api/PropertiesFilter/Filter",
                json=payload,
            )
            print("POST Filter", payload, r.status_code, r.text[:180].replace("\n", " "))
        except Exception as exc:  # noqa: BLE001
            print("POST fail", payload, exc)
