# -*- coding: utf-8 -*-
"""Update pet_friendly metadata for SPA malls.json and data/hotels.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

ROOT = Path(__file__).resolve().parents[1]
SPA_MALLS_PATH = ROOT / "malls.json"
HOTELS_PATH = ROOT / "data" / "hotels.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 8.0

DEFAULT_PET: dict[str, Any] = {
    "is_allowed": None,
    "details": "待官網確認；請參閱官方網站最新寵物進出規範。",
    "official_url": "",
}

CURATED_MALLS: dict[str, dict[str, Any]] = {
    "新城市廣場": {
        "is_allowed": True,
        "details": "設戶外 Pets Park／毛孩活動區；室內須以寵物袋或推車載運、不落地。條款以官網為準。",
        "official_url": "https://www.newtownplaza.com.hk/",
    },
    "YOHO MALL 形點": {
        "is_allowed": True,
        "details": "歡迎寵物進場；須使用寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.yohomall.com/",
    },
    "K11 MUSEA": {
        "is_allowed": True,
        "details": "KLUB 11 寵物友善商場；寵物須置於袋／推車內。條款以官網為準。",
        "official_url": "https://www.k11musea.com/",
    },
    "K11 Art Mall": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車；不可落地。條款以 K11 官網為準。",
        "official_url": "https://www.k11musea.com/",
    },
    "apm": {
        "is_allowed": True,
        "details": "新地商場寵物政策：寵物須全程置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.hkmalls.com/",
    },
    "MOKO 新世紀廣場": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車內，不可落地。條款以 MOKO 官網為準。",
        "official_url": "https://www.moko.com.hk/",
    },
    "MegaBox": {
        "is_allowed": True,
        "details": "歡迎寵物進場；須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.megabox.com.hk/",
    },
    "圍方 The Wai": {
        "is_allowed": True,
        "details": "寵物友善商場；寵物須置於袋／推車。條款以官網為準。",
        "official_url": "https://www.the-wai.com/",
    },
    "D·PARK 愉景新城": {
        "is_allowed": True,
        "details": "設寵物友善設施；室內須以寵物袋或推車載運。條款以官網為準。",
        "official_url": "https://www.dpark.com.hk/",
    },
    "The LOHAS 康城": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車。條款以官網為準。",
        "official_url": "https://www.thelohas.com.hk/",
    },
    "太古城中心": {
        "is_allowed": True,
        "details": "LIVE+ 寵物政策：寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.cityplaza.com/zh-hk",
    },
    "康怡廣場": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.cityplaza.com/zh-hk",
    },
    "太古廣場": {
        "is_allowed": True,
        "details": "above 會員商場：寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.pacificplace.com.hk/zh-hk",
    },
    "ELEMENTS 圓方": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車，不可落地。條款以 ELEMENTS 官網為準。",
        "official_url": "https://www.elementshk.com/",
    },
    "AIRSIDE": {
        "is_allowed": True,
        "details": "寵物友善商場；寵物須置於袋／推車。條款以官網為準。",
        "official_url": "https://www.airside.com.hk/",
    },
    "新都城中心": {
        "is_allowed": True,
        "details": "戶外平台歡迎寵物；室內須以寵物袋或推車載運。條款以官網為準。",
        "official_url": "https://www.metrocity.com.hk/",
    },
    "將軍澳中心 Park Central": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車。條款以官網為準。",
        "official_url": "https://www.parkcentral.com.hk/",
    },
    "PopCorn": {
        "is_allowed": False,
        "details": "一般情況下不歡迎寵物（導盲犬除外）。條款以 MTR 商場守則為準。",
        "official_url": "https://www.popcornmall.com.hk/",
    },
    "國際金融中心商場": {
        "is_allowed": False,
        "details": "商場內不允許攜帶寵物（導盲犬除外）。條款以 ifc mall 官網為準。",
        "official_url": "https://www.ifcmall.com.hk/",
    },
    "海港城": {
        "is_allowed": False,
        "details": "商場內不允許攜帶寵物（導盲犬除外）。條款以海港城官網為準。",
        "official_url": "https://www.harbourcity.com.hk/",
    },
    "朗豪坊": {
        "is_allowed": False,
        "details": "商場內不允許攜帶寵物（導盲犬除外）。條款以朗豪坊官網為準。",
        "official_url": "https://www.langhamplace.com.hk/",
    },
    "時代廣場": {
        "is_allowed": False,
        "details": "室內商場不允許寵物（導盲犬除外）。條款以官網為準。",
        "official_url": "https://www.timessquare.com.hk/",
    },
    "又一城": {
        "is_allowed": False,
        "details": "商場內不允許攜帶寵物（導盲犬除外）。條款以又一城官網為準。",
        "official_url": "https://www.festivalwalk.com.hk/",
    },
}

CURATED_HOTELS: dict[str, dict[str, Any]] = {
    "海洋公園萬豪": {
        "is_allowed": True,
        "details": "酒店設寵物友善住宿計劃（需預約及附加費）；條款以官網最新公告為準。",
        "official_url": "https://www.marriott.com/zh/hotels/hkgop-hong-kong-ocean-park-marriott-hotel/overview/",
    },
}

POSITIVE_KEYWORDS = (
    "寵物友好", "寵物友善", "pet-friendly", "pet friendly", "歡迎寵物", "歡迎毛孩",
    "寵物進場", "寵物推車", "寵物袋", "pets park", "毛孩", "pet policy",
)
NEGATIVE_KEYWORDS = (
    "禁止攜帶寵物", "不可帶寵物", "不可攜帶寵物", "no pets", "pets are not allowed", "導盲犬除外",
)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).lower()


def merge_policy(base_url: str, curated: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_PET)
    out["official_url"] = base_url or ""
    if curated:
        out.update(curated)
        if base_url and not out.get("official_url"):
            out["official_url"] = base_url
    return out


def resolve_curated(name: str, table: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if name in table:
        return dict(table[name])
    normalized = normalize_name(name)
    for key, value in table.items():
        nk = normalize_name(key)
        if nk in normalized or normalized in nk:
            return dict(value)
    return None


def extract_snippet(text: str, keyword: str, radius: int = 90) -> str:
    lowered = text.lower()
    idx = lowered.find(keyword.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(keyword) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()[:240]


def analyze_html(html: str, page_url: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return merge_policy(page_url, None)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lowered = text.lower()
    negative_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in lowered)
    positive_hits = [kw for kw in POSITIVE_KEYWORDS if kw.lower() in lowered]
    policy_url = page_url
    for a in soup.find_all("a", href=True):
        label = (a.get_text(" ", strip=True) or "") + " " + str(a.get("href", ""))
        if re.search(r"寵物|pet|毛孩", label, re.I):
            policy_url = urljoin(page_url, a["href"])
            break
    if positive_hits and negative_hits <= len(positive_hits):
        snippet = extract_snippet(text, positive_hits[0]) or "官網提及寵物友善規範，詳情請參閱連結。"
        return {
            "is_allowed": True,
            "details": f"{snippet}（條款以官網為準）",
            "official_url": policy_url,
        }
    if negative_hits and not positive_hits:
        return {
            "is_allowed": False,
            "details": "官網提及禁止或限制攜帶寵物（導盲犬除外）。條款以官網為準。",
            "official_url": policy_url,
        }
    return merge_policy(page_url, None)


def fetch_policy(url: str) -> dict[str, Any]:
    if not url or not httpx:
        return merge_policy(url, None)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
        ) as client:
            response = client.get(url)
            if response.status_code >= 400:
                return merge_policy(str(response.url), None)
            return analyze_html(response.text, str(response.url))
    except Exception:
        return merge_policy(url, None)


def policy_for_mall(mall: dict[str, Any], *, scrape: bool, force: bool) -> tuple[dict[str, Any], str]:
    if mall.get("pet_friendly") and not force:
        return mall["pet_friendly"], "skip"
    name = str(mall.get("mall_name") or "")
    base_url = str(mall.get("mall_url") or mall.get("official_home") or "")
    curated = resolve_curated(name, CURATED_MALLS)
    if curated:
        return merge_policy(base_url or str(curated.get("official_url") or ""), curated), "curated"
    if scrape and base_url:
        return fetch_policy(base_url), "scraped"
    return merge_policy(base_url, None), "default"


def policy_for_hotel(hotel: dict[str, Any], *, scrape: bool, force: bool) -> tuple[dict[str, Any], str]:
    if hotel.get("pet_friendly") and not force:
        return hotel["pet_friendly"], "skip"
    name = str(hotel.get("name") or "")
    base_url = str(hotel.get("official_homepage") or hotel.get("official_website") or "")
    curated = resolve_curated(name, CURATED_HOTELS)
    if curated:
        return merge_policy(base_url or str(curated.get("official_url") or ""), curated), "curated"
    if scrape and base_url:
        scraped = fetch_policy(base_url)
        if scraped.get("is_allowed") is not None:
            return scraped, "scraped"
    return {
        "is_allowed": False,
        "details": "一般客房不接待寵物（導盲犬除外）；如需攜同寵物請先向酒店查詢。條款以官網為準。",
        "official_url": base_url,
    }, "default-hotel"


def enrich_spa_malls(payload: dict[str, Any], *, scrape: bool, force: bool, workers: int) -> tuple[list[str], dict[str, int]]:
    stats: dict[str, int] = {"curated": 0, "scraped": 0, "default": 0, "skip": 0, "true": 0, "false": 0, "null": 0}
    updated: list[str] = []
    tasks: list[tuple[str, dict[str, Any]]] = []
    for district in payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if isinstance(mall, dict):
                tasks.append((str(district.get("district") or ""), mall))

    def work(item: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any], dict[str, Any], str]:
        district_name, mall = item
        policy, source = policy_for_mall(mall, scrape=scrape, force=force)
        return district_name, mall, policy, source

    if scrape and workers > 1:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, item) for item in tasks]
            for fut in as_completed(futures):
                results.append(fut.result())
    else:
        results = [work(item) for item in tasks]

    for district_name, mall, policy, source in results:
        mall["pet_friendly"] = policy
        stats[source if source in stats else "default"] += 1
        allowed = policy.get("is_allowed")
        stats["true" if allowed is True else "false" if allowed is False else "null"] += 1
        if source != "skip":
            updated.append(f"{mall.get('mall_name')} ({district_name})")
    return updated, stats


def enrich_hotels(payload: dict[str, Any], *, scrape: bool, force: bool, workers: int) -> tuple[list[str], dict[str, int]]:
    stats: dict[str, int] = {"curated": 0, "scraped": 0, "default": 0, "default-hotel": 0, "skip": 0, "true": 0, "false": 0, "null": 0}
    updated: list[str] = []
    hotels = [h for h in (payload.get("hotels") or []) if isinstance(h, dict)]

    def work(hotel: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        policy, source = policy_for_hotel(hotel, scrape=scrape, force=force)
        return hotel, policy, source

    if scrape and workers > 1:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, h) for h in hotels]
            for fut in as_completed(futures):
                results.append(fut.result())
    else:
        results = [work(h) for h in hotels]

    for hotel, policy, source in results:
        hotel["pet_friendly"] = policy
        key = "default" if source.startswith("default") else source
        stats[key if key in stats else "default"] += 1
        allowed = policy.get("is_allowed")
        stats["true" if allowed is True else "false" if allowed is False else "null"] += 1
        if source != "skip":
            updated.append(str(hotel.get("name") or hotel.get("id")))
    return updated, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update pet_friendly on malls.json and data/hotels.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--scrape", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args(argv)

    if args.scrape and httpx is None:
        print("[update_pet_policy] pip install httpx beautifulsoup4", file=sys.stderr)
        return 1

    malls_payload = json.loads(SPA_MALLS_PATH.read_text(encoding="utf-8"))
    hotels_payload = json.loads(HOTELS_PATH.read_text(encoding="utf-8"))
    mall_updated, mall_stats = enrich_spa_malls(malls_payload, scrape=args.scrape, force=args.force, workers=args.workers)
    hotel_updated, hotel_stats = enrich_hotels(hotels_payload, scrape=args.scrape, force=args.force, workers=args.workers)

    print("========== PET POLICY UPDATE ==========")
    print(f"Mode     : {'DRY-RUN' if args.dry_run else 'WRITE'} | scrape={args.scrape}")
    print(f"Malls    : {len(mall_updated)} updated | {mall_stats}")
    print(f"Hotels   : {len(hotel_updated)} updated | {hotel_stats}")
    print("=======================================\n")

    if not args.dry_run:
        SPA_MALLS_PATH.write_text(json.dumps(malls_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        HOTELS_PATH.write_text(json.dumps(hotels_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
