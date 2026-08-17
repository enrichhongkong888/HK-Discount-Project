# -*- coding: utf-8 -*-
import httpx
import re

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.linkhk.com/tc/",
}

urls = [
    "https://www.linkhk.com/tc/",
    "https://www.linkhk.com/tc/promotion/",
    "https://www.linkhk.com/tc/shopCentre/",
    "https://www.lokfuplaza.com/tc/shopping",
    "https://www.linkhk.com/api/promotions",
    "https://www.linkhk.com/umbraco/api/promotion/GetPromotions",
    "https://www.linkhk.com/umbraco/surface/promotion/list",
    "https://www.linkreit.com/en/business/properties/",
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=25.0) as client:
    for url in urls:
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print("===", r.status_code, ct[:50], url)
            text = r.text
            print(text[:200].replace("\n", " "))
            apis = sorted(set(re.findall(r"https?://[^\"'\s<>]+(?:api|graphql|json)[^\"'\s<>]*", text, flags=re.I)))
            paths = sorted(set(re.findall(r"[\"'](/[^\"']*(?:api|promotion|shop|tenant|parking)[^\"']*)[\"']", text, flags=re.I)))
            if apis:
                print("  APIS:", apis[:12])
            if paths:
                print("  PATHS:", paths[:20])
        except Exception as exc:  # noqa: BLE001
            print("FAIL", url, type(exc).__name__, exc)
