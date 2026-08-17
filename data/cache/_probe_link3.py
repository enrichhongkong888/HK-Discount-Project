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

# Fetch require.js app config / shopping page scripts for Link mall sites
pages = [
    "https://www.lokfuplaza.com/tc/shopping",
    "https://www.stanleyplaza.com/tc/shopping",
    "https://www.linkhk.com/tc/promotion/",
    "https://www.linkhk.com/en/shopCentre/splxc2",
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
    for page in pages:
        try:
            r = client.get(page)
            print("===", r.status_code, page)
            html = r.text
            # Find data URLs / JSON endpoints / main.js
            hits = sorted(set(re.findall(r"[\"']([^\"']*(?:api|json|shop|tenant|directory|promo|parking|umbraco|graphql)[^\"']*)[\"']", html, flags=re.I)))
            print(" hits", hits[:30])
            # embedded JSON
            for m in re.finditer(r"window\.[A-Za-z0-9_]+\\s*=\\s*(\\{.*?\\});", html, flags=re.S):
                print(" window assign", m.group(0)[:120])
            for m in re.finditer(r"<script[^>]+type=[\"']application/ld\\+json[\"'][^>]*>([\\s\\S]*?)</script>", html, flags=re.I):
                print(" ld+json", m.group(1)[:120])
            # Look for data- attributes with mall ids
            for m in re.finditer(r"data-[a-z-]+=\"[^\"]+\"", html, flags=re.I):
                s = m.group(0)
                if any(k in s.lower() for k in ("mall", "shop", "api", "site")):
                    print(" ", s)
        except Exception as exc:  # noqa: BLE001
            print("FAIL", page, exc)

    # Try LinkHK shop centre pages that registry mentions
    for url in [
        "https://www.linkhk.com/tc/shopCentre/",
        "https://www.linkhk.com/en/shopCentre/",
        "https://www.linkhk.com/tc/malls/",
        "https://www.linkhk.com/api/v1/centres",
        "https://www.linkhk.com/ajax/getPromotions",
        "https://www.linkhk.com/ajax/promotion/list",
        "https://www.linkhk.com/tc/promotion/search",
    ]:
        try:
            r = client.get(url)
            print("TRY", r.status_code, r.headers.get("content-type","")[:30], url, r.text[:120].replace("\n"," "))
        except Exception as exc:
            print("TRY FAIL", url, exc)
