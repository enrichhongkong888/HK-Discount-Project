# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import quote
from pathlib import Path

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.openrice.com/zh/hongkong/restaurants",
    "Origin": "https://www.openrice.com",
}

url = (
    "https://www.openrice.com/api/v2/search?"
    f"uiLang=zh&regionId=1&whatwhere={quote('葵涌廣場')}&rows=5&startAt=0"
)
with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
    r = client.get(url)
    data = r.json()

Path("data/cache/_openrice_sample.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2)[:20000] + "\n",
    encoding="utf-8",
)
print("keys", list(data.keys()))
# find restaurant-like lists
for k, v in data.items():
    if isinstance(v, list):
        print("list", k, "len", len(v))
        if v and isinstance(v[0], dict):
            print("  item keys", list(v[0].keys())[:40])
    elif isinstance(v, dict):
        print("dict", k, "keys", list(v.keys())[:30])

pagination = data.get("pagination") or data.get("searchResult") or {}
print("pagination-ish", type(pagination), str(pagination)[:200])

# Try to find pois
for key in ("paginationResult", "searchResult", "pois", "results", "pagination"):
    if key in data:
        print("found", key)

# dump first poi shallow
text = json.dumps(data, ensure_ascii=False)
for marker in ("phone", "tel", "shopNo", "floor", "address", "name", "promo", "offer", "discount"):
    print(marker, text.lower().count(marker.lower()))
