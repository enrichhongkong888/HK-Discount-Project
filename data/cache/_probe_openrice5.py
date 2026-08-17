# -*- coding: utf-8 -*-
import httpx
import json
from urllib.parse import quote, urlencode
from pathlib import Path

ua = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

with httpx.Client(follow_redirects=True, timeout=25.0) as client:
    # Warm session via HTML listing page
    html_url = f"https://www.openrice.com/zh/hongkong/restaurants?whatwhere={quote('葵涌廣場')}"
    html_headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    }
    hr = client.get(html_url, headers=html_headers)
    print("html", hr.status_code, "cookies", dict(client.cookies), "len", len(hr.text))
    # Look for API call patterns embedded
    for needle in ("api/v2/search", "startAt", "pageToken", "ORScoreDesc", "isIndexRequired"):
        print(needle, hr.text.count(needle))

    api_headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
        "Referer": html_url,
        "Origin": "https://www.openrice.com",
        "X-Requested-With": "XMLHttpRequest",
    }
    params_list = [
        {"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "15", "startAt": "0", "sortBy": "ORScoreDesc", "poiType": "1"},
        {"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "15", "startAt": "0", "sortBy": "ORScoreDesc"},
        {"uiLang": "zh", "regionId": "1", "whatwhere": "麦当劳", "rows": "10", "startAt": "0", "sortBy": "ORScoreDesc"},
        {"uiLang": "zh", "regionId": "1", "districtId": "1003", "rows": "10", "startAt": "0", "sortBy": "ORScoreDesc"},
    ]
    for params in params_list:
        url = "https://www.openrice.com/api/v2/search?" + urlencode(params)
        r = client.get(url, headers=api_headers)
        data = r.json()
        pr = data.get("paginationResult") or {}
        results = pr.get("results") or []
        print("API", params.get("whatwhere") or params.get("districtId"), "count", pr.get("count"), "n", len(results), "indexReq", pr.get("isIndexRequired"))
        if results:
            Path("data/cache/_openrice_poi.json").write_text(
                json.dumps(results[0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print("sample keys", sorted(results[0].keys())[:60])
            break

    # Try mobile API host
    mobile_hosts = [
        "https://api-hk.openrice.com/api/v2/search?" + urlencode({"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "10", "startAt": "0"}),
        "https://m.openrice.com/api/v2/search?" + urlencode({"uiLang": "zh", "regionId": "1", "whatwhere": "葵涌廣場", "rows": "10", "startAt": "0"}),
    ]
    for url in mobile_hosts:
        try:
            r = client.get(url, headers=api_headers)
            print("MOBILE", r.status_code, url[:70], r.text[:120].replace("\n", " "))
        except Exception as exc:
            print("MOBILE FAIL", url[:60], exc)
