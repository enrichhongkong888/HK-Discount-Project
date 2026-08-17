# -*- coding: utf-8 -*-
import httpx
import json
from pathlib import Path

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
headers = {
    "User-Agent": ua,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.linkhk.com/en/shopCentre/splxc2",
    "Origin": "https://www.linkhk.com",
    "Content-Type": "application/json",
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
    # Inspect shop centre page for numeric ids
    html = client.get("https://www.linkhk.com/en/shopCentre/splxc2", headers={**headers, "Accept": "text/html"}).text
    Path("data/cache/_link_splxc2.html").write_text(html, encoding="utf-8")
    import re
    nums = sorted(set(re.findall(r"shopCentre(?:Id)?[\"'=\s:]+(\d+)", html, flags=re.I)))
    print("ids in html", nums[:30])
    print("snippets", re.findall(r".{0,40}shopCentre.{0,60}", html, flags=re.I)[:20])
    apis = sorted(set(re.findall(r"/linkweb/api/[A-Za-z0-9_/\-?=&]+", html)))
    print("apis", apis)

    # Try GET/POST shopCentre/{id}
    for i in list(range(1, 25)) + [100, 200, 1000]:
        for method in ("GET", "POST"):
            url = f"https://www.linkhk.com/linkweb/api/shopCentre/{i}"
            if method == "GET":
                r = client.get(url)
            else:
                r = client.post(url, json={"lang": "tc"})
            if r.status_code == 404 and not r.text.strip():
                continue
            if '"error":"0000"' in r.text and '"data":null' not in r.text:
                print("FOUND", method, i, r.text[:300].replace("\n", " "))
                Path(f"data/cache/_link_centre_{i}.json").write_text(r.text, encoding="utf-8")
            elif '"error":"0000"' in r.text:
                # success but null - note once
                if i < 5:
                    print("nullok", method, i, r.text[:120].replace("\n", " "))
            elif i < 4:
                print(method, i, r.status_code, r.text[:140].replace("\n", " "))

    # Query-string style
    for url in [
        "https://www.linkhk.com/linkweb/api/shopCentre/list?lang=tc&code=splxc2",
        "https://www.linkhk.com/linkweb/api/shopCentre/getByCode?code=splxc2",
        "https://www.linkhk.com/linkweb/api/shopCentre/get?code=splxc2&lang=tc",
    ]:
        r = client.get(url)
        print("GET", r.status_code, url, r.text[:180].replace("\n", " "))
        r = client.post(url, json={"code": "splxc2", "lang": "tc"})
        print("POST", r.status_code, url, r.text[:180].replace("\n", " "))
