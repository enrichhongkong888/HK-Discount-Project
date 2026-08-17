# -*- coding: utf-8 -*-
import json
import re
from html import unescape
from pathlib import Path

import httpx

ua = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json"}

with httpx.Client(headers=ua, follow_redirects=True, timeout=40.0) as c:
    # YOHO all events starts
    starts = []
    for page in range(1, 4):
        r = c.get(
            "https://cms.yohomall.hk/api/events",
            params={
                "pagination[pageSize]": 50,
                "pagination[page]": page,
                "sort": "event_start:asc",
            },
        )
        for row in r.json().get("data") or []:
            a = row.get("attributes") or {}
            starts.append((str(a.get("event_start") or "")[:10], a.get("name")))
    print("yoho start dates sample", starts[:5], "...", starts[-5:])
    print("unique starts around Aug", [s for s in starts if s[0].startswith("2026-08")])

    # YOHO shops sample with phone
    r = c.get(
        "https://cms.yohomall.hk/api/shops",
        params={"pagination[pageSize]": 5, "populate": "mall_shop_number"},
    )
    for row in (r.json().get("data") or [])[:3]:
        a = row.get("attributes") or row
        print("shop", a.get("display_name") or a.get("name_zh"), a.get("phone"), a.get("mall_shop_number"))

    # Sino Promotion globalSearchData
    html = c.get("https://www.olympiancity.com.hk/tc/Promotion").text
    m = re.search(r"id=['\"]globalSearchData['\"][^>]*>(\{.*?\})</div>", html, re.S)
    if m:
        data = json.loads(unescape(m.group(1)))
        Path("data/cache/_sino_promo_gsd.json").write_text(
            json.dumps({k: (type(v).__name__, len(v) if isinstance(v, list) else list(v)[:8] if isinstance(v, dict) else str(v)[:80]) for k, v in data.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("sino promo keys", list(data.keys())[:20])
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print(" list", k, len(v), list(v[0].keys())[:15])
                print("  sample", json.dumps(v[0], ensure_ascii=False)[:250])
