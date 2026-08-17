# -*- coding: utf-8 -*-
import json
import re
from html import unescape
from pathlib import Path

import httpx

html = httpx.get(
    "https://www.olympiancity.com.hk/tc/Promotion",
    headers={"User-Agent": "Mozilla/5.0"},
    follow_redirects=True,
    timeout=40.0,
).text
m = re.search(r"id=['\"]globalSearchData['\"][^>]*>(\{.*?\})</div>", html, re.S)
data = json.loads(unescape(m.group(1)))
Path("data/cache/_sino_promo_raw.json").write_text(
    json.dumps(data, ensure_ascii=False)[:20000], encoding="utf-8"
)
for k, v in data.items():
    if isinstance(v, list) and v and isinstance(v[0], dict):
        keys = set()
        for x in v[:10]:
            keys |= set(x.keys())
        print("LIST", k, len(v), sorted(keys)[:25])
        print(json.dumps(v[0], ensure_ascii=False)[:350])
    elif isinstance(v, dict):
        print("DICT", k, list(v.keys())[:12])
