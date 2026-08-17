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
    shops = ((lokfu.get("shop") or {}).get("shopList") or [])[:5]
    dine = ((lokfu.get("dine") or {}).get("shopList") or ((lokfu.get("dine") or {}).get("dineList") or []))[:5]
    print("shopList", len((lokfu.get("shop") or {}).get("shopList") or []))
    print("dine keys", (lokfu.get("dine") or {}).keys())
    print("dine sample", json.dumps(lokfu.get("dine"), ensure_ascii=False)[:500])

    for s in shops:
        sid = s["shopId"]
        r = client.get(f"https://www.linkhk.com/linkweb/api/shop/{sid}")
        print("shop", sid, s.get("shopNameTc"), r.status_code)
        data = r.json()
        Path(f"data/cache/_link_shop_{sid}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(data, ensure_ascii=False)[:500])
        break

    # promotion detail
    r = client.get("https://www.linkhk.com/linkweb/api/promotion/806")
    Path("data/cache/_link_promo_806.json").write_text(
        json.dumps(r.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("promo806 keys", (r.json().get("data") or {}).keys())
