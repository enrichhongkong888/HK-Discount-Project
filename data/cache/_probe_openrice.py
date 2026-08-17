# -*- coding: utf-8 -*-
import httpx
from urllib.parse import quote

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
    "Origin": "https://www.openrice.com",
    "X-Requested-With": "XMLHttpRequest",
}

mall = quote("葵涌廣場")
candidates = [
    f"https://www.openrice.com/api/v2/search?uiLang=zh&regionId=1&whatwhere={mall}&rows=10&start=0",
    f"https://www.openrice.com/api/v2/search?uiLang=zh&region=1&where={mall}&rows=5",
    f"https://www.openrice.com/api/v1/search?whatwhere={mall}&uiLang=zh&regionId=1",
    f"https://www.openrice.com/zh/hongkong/api/search?whatwhere={mall}",
    f"https://api.openrice.com/api/v2/search?uiLang=zh&regionId=1&whatwhere={mall}",
    "https://www.openrice.com/api/v2/geo/regions",
    "https://www.openrice.com/api/poi/search?keyword=%E8%91%B5%E6%B6%8C%E5%BB%A3%E5%A0%B4",
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
    for url in candidates:
        try:
            r = client.get(url)
            ct = r.headers.get("content-type", "")
            print("===", r.status_code, ct[:48], url[:100])
            print(r.text[:280].replace("\n", " "))
        except Exception as exc:  # noqa: BLE001
            print("FAIL", url[:90], type(exc).__name__, exc)
