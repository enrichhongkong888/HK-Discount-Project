# -*- coding: utf-8 -*-
import json
from datetime import date, timedelta
from pathlib import Path

import httpx

ua = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/html"}
today = date.today()
preview = today + timedelta(days=3)

with httpx.Client(headers=ua, follow_redirects=True, timeout=30.0) as c:
    # YOHO events
    r = c.get(
        "https://cms.yohomall.hk/api/events",
        params={"pagination[pageSize]": 50, "pagination[page]": 1, "sort": "event_start:desc"},
    )
    data = r.json()
    rows = data.get("data") or []
    print("yoho events", len(rows), "total", (data.get("meta") or {}).get("pagination"))
    upcoming = 0
    for row in rows[:20]:
        a = row.get("attributes") or row
        start = str(a.get("event_start") or "")[:10]
        end = str(a.get("event_end") or "")[:10]
        name = a.get("name")
        try:
            sd = date.fromisoformat(start)
        except ValueError:
            continue
        flag = ""
        if today <= sd <= preview:
            upcoming += 1
            flag = "UPCOMING"
        elif sd <= today <= date.fromisoformat(end) if end else False:
            flag = "ACTIVE"
        if flag:
            print(flag, start, end, name)
    print("yoho upcoming-in-window (page1 sample)", upcoming)

    # Sino promotion pages
    for u in (
        "https://www.olympiancity.com.hk/tc/Promotion",
        "https://www.olympiancity.com.hk/tc/Shop",
        "https://www.pacificplace.com.hk/zh-hk/whats-on",
        "https://www.newtownplaza.com.hk/zh-hant/promotions",
    ):
        rr = c.get(u)
        text = rr.text
        print(rr.status_code, len(text), "gsd" in text.lower() or "globalSearchData" in text, u)
        if "globalSearchData" in text:
            print("  has globalSearchData")
        # look for date patterns near 2026
        import re

        dates = re.findall(r"2026[-年/]\d{1,2}[-月/]\d{1,2}", text[:50000])
        print("  date-like", len(dates), dates[:5])
