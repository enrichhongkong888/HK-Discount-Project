# -*- coding: utf-8 -*-
import httpx
import re
import json
from pathlib import Path

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
headers = {"User-Agent": ua, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"}

pages = [
    "https://www.linkhk.com/tc/promotion/",
    "https://www.linkreit.com/en/business/properties/t-town/",
    "https://www.linkreit.com/zh-hant/business/properties/",
    "https://www.lokfuplaza.com/tc/shopping",
    "https://www.stanleyplaza.com/tc/offers",
    "https://www.stanleyplaza.com/tc/shopping",
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=35.0) as client:
    for url in pages:
        try:
            r = client.get(url, headers={**headers, "Accept": "text/html,application/xhtml+xml"})
        except Exception as exc:
            print("FAIL", url, exc)
            continue
        html = r.text
        print("===", r.status_code, len(html), url)
        # JSON-LD / __NEXT_DATA__ / sitecore
        for pat, name in [
            (r'<script[^>]+type="application/ld\+json"[^>]*>([\s\S]*?)</script>', "ldjson"),
            (r'<script[^>]+id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', "next"),
            (r'window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]*?\});', "initial"),
            (r'window\.pageData\s*=\s*(\{[\s\S]*?\});', "pageData"),
            (r'"@type"\s*:\s*"ShoppingCenter"', "shoppingCenter"),
        ]:
            ms = list(re.finditer(pat, html, flags=re.I))
            if ms:
                print(" ", name, len(ms), ms[0].group(0)[:140].replace("\n"," "))
        apis = sorted(set(re.findall(r"https?://[^\"'\s<>]+(?:api|graphql|json)[^\"'\s<>]*", html, flags=re.I)))
        paths = sorted(set(re.findall(r"[\"'](/[^\"']*(?:api|promo|offer|shop|tenant|directory|parking)[^\"']*)[\"']", html, flags=re.I)))
        print("  apis", apis[:15])
        print("  paths", paths[:20])

    # Try Sitecore layout service style endpoints commonly used
    candidates = [
        "https://www.linkhk.com/sitecore/api/layout/render/jss?item=/tc/promotion&sc_lang=zh-HK",
        "https://www.linkhk.com/-/media/data/promotions.json",
        "https://www.stanleyplaza.com/api/offers",
        "https://www.stanleyplaza.com/tc/api/offers",
        "https://www.stanleyplaza.com/umbraco/api/offers",
        "https://www.stanleyplaza.com/umbraco/api/OfferApi/GetOffers",
        "https://www.stanleyplaza.com/umbraco/api/ShopApi/GetAll",
        "https://www.lokfuplaza.com/umbraco/api/ShopApi/GetAll",
        "https://www.lokfuplaza.com/umbraco/api/OfferApi/GetOffers",
    ]
    for url in candidates:
        try:
            r = client.get(url, headers={**headers, "Accept": "application/json, text/plain, */*"})
            print("TRY", r.status_code, r.headers.get("content-type","")[:40], url)
            print(" ", r.text[:160].replace("\n"," "))
        except Exception as exc:
            print("TRY FAIL", url, exc)
