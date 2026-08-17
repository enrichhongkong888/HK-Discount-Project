# -*- coding: utf-8 -*-
import httpx
import json
from pathlib import Path

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
headers = {
    "User-Agent": ua,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.linkhk.com/tc/",
    "Origin": "https://www.linkhk.com",
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
    lokfu = client.get("https://www.linkhk.com/linkweb/api/shopCentre/7").json()["data"]
    promos = lokfu.get("promotions") or []
    Path("data/cache/_link_promos.json").write_text(
        json.dumps(promos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("promo count", len(promos))
    if promos:
        print("promo keys", promos[0].keys())
        print(json.dumps(promos[0], ensure_ascii=False, indent=2)[:1200])

    for pid in [806, 792] + [p.get("id") for p in promos[:3]]:
        if not pid:
            continue
        for path in [f"promotion/{pid}", f"promotions/{pid}", f"promotion/detail/{pid}", f"promotion/get/{pid}"]:
            r = client.get("https://www.linkhk.com/linkweb/api/" + path)
            if r.status_code == 404 and not r.text.strip():
                continue
            print("DETAIL", path, r.status_code, r.text[:250].replace("\n", " "))

    # Try tenant/shop directory endpoints with centre id query
    for path in [
        "shop?shopCentreId=7",
        "shop/list?shopCentreId=7",
        "tenant?shopCentreId=7",
        "directory?shopCentreId=7",
        "shopCentreShop?shopCentreId=7",
        "shopCentre/shopList?shopCentreId=7",
    ]:
        url = "https://www.linkhk.com/linkweb/api/" + path
        r = client.get(url)
        print("TRY", path, r.status_code, r.text[:160].replace("\n", " "))
