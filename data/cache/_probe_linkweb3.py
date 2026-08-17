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
    "Content-Type": "application/json",
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=40.0) as client:
    r = client.post("https://www.linkhk.com/linkweb/api/shopCentre/list", json={"lang": "tc"})
    data = r.json()
    Path("data/cache/_link_shopcentres.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("keys", data.keys())
    payload = data.get("data")
    print("data type", type(payload))
    if isinstance(payload, dict):
        print("data keys", payload.keys())
        for k, v in payload.items():
            if isinstance(v, list):
                print(" list", k, len(v))
                if v:
                    print("  item keys", list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]))
                    print("  sample", json.dumps(v[0], ensure_ascii=False)[:400])
            elif isinstance(v, dict):
                print(" dict", k, list(v.keys())[:20])
            else:
                print(" ", k, "=", str(v)[:80])

    # Try related endpoints with empty or lang body
    endpoints = [
        ("shopCentre/list", {"lang": "tc"}),
        ("shopCentre/list", {"lang": "en"}),
        ("shop/listByCentre", {"shopCentreId": 1, "lang": "tc"}),
        ("shop/listByShopCentre", {"shopCentreId": 1, "lang": "tc"}),
        ("shop/getList", {"shopCentreId": 1}),
        ("promotion/list", {"lang": "tc"}),
        ("promotion/listByCentre", {"shopCentreId": 1, "lang": "tc"}),
        ("offer/list", {"lang": "tc"}),
        ("parkingOffer/list", {"lang": "tc"}),
        ("parking/list", {"lang": "tc"}),
        ("home/promotions", {"lang": "tc"}),
        ("cms/promotion/list", {"lang": "tc"}),
    ]
    for path, body in endpoints:
        url = "https://www.linkhk.com/linkweb/api/" + path
        resp = client.post(url, json=body)
        text = resp.text
        ok = '"error":"0000"' in text or '"error":"0"' in text
        print("POST", path, resp.status_code, "OK" if ok else text[:160].replace("\n", " "))
