# -*- coding: utf-8 -*-
"""Update pet_friendly metadata for SPA malls.json and data/hotels.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

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
TIMEOUT = 12.0
POLICY_FETCH_MIN_SCORE = 50

DEFAULT_PET: dict[str, Any] = {
    "is_allowed": None,
    "details": "待官網確認；請參閱官方網站最新寵物進出規範。",
    "official_url": "",
}

CURATED_MALLS: dict[str, dict[str, Any]] = {
    "新城市廣場": {
        "is_allowed": True,
        "details": "設 Pets Park／寵物同樂園；一期 L1 可牽繩步行，其他室內須手抱或置於寵物車／袋內。條款以官網為準。",
        "official_url": "https://www.newtownplaza.com.hk/zh-hant/pet-friendly/",
    },
    "YOHO MALL 形點": {
        "is_allowed": True,
        "details": "官網提供寵物手推車、寵物袋、牽引繩等借用服務；須遵守商場寵物進出規範。條款以官網為準。",
        "official_url": "https://www.yohomall.hk/zh-hk/about",
    },
    "K11 MUSEA": {
        "is_allowed": True,
        "details": "KLUB 11 寵物友善商場；B1 禮賓處提供嬰兒及寵物推車借用，寵物須置於袋／推車內。條款以官網為準。",
        "official_url": "https://www.k11musea.com/zh-hk/visit/facilities-and-services/",
    },
    "K11 Art Mall": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車；不可落地。禮賓處設寵物推車借用。條款以 K11 官網為準。",
        "official_url": "https://hk.k11.com/zh-hk/visit/facilities-and-services",
    },
    "K11購物藝術館": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車；不可落地。禮賓處設寵物推車借用。條款以 K11 官網為準。",
        "official_url": "https://hk.k11.com/zh-hk/visit/facilities-and-services",
    },
    "apm": {
        "is_allowed": True,
        "details": "新地商場寵物政策：寵物須全程置於寵物袋或推車，不可落地。條款以新地顧客服務頁為準。",
        "official_url": "https://www.shkp.com/zh-HK/our-business/hong-kong-properties/shopping-mall/customer-care-service",
    },
    "MOKO 新世紀廣場": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車內，不可落地；禮賓處提供寵物車借用。條款以 MOKO 官網為準。",
        "official_url": "https://www.moko.com.hk/about-moko/services/",
    },
    "MegaBox": {
        "is_allowed": True,
        "details": "歡迎貓狗進場；室內及室外（L4 寵物樂園除外）須置於寵物車或寵物袋並扣好布篷。條款以官網為準。",
        "official_url": "https://www.megabox.com.hk/page.php?lang=tchi&page_id=256",
    },
    "圍方 The Wai": {
        "is_allowed": True,
        "details": "設寵物車借用、寵物友善升降機及寵物專用廁所等；須遵守商場設施使用規範。條款以官網為準。",
        "official_url": "https://www.thewaimall.com/tch/facilities-and-services",
    },
    "D·PARK 愉景新城": {
        "is_allowed": True,
        "details": "設寵物友善設施；室內須以寵物袋或推車載運。詳情請向禮賓處查詢。條款以官網為準。",
        "official_url": "https://www.dpark.com.hk/services?lang=en",
    },
    "太古城中心": {
        "is_allowed": True,
        "details": "LIVE+ 寵物政策：寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.cityplaza.com/zh-hk/about-cityplaza/services",
    },
    "康怡廣場": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.hanglungmalls.com/kornhill-plaza/zh-hk/about-kornhill-plaza/services",
    },
    "太古廣場": {
        "is_allowed": True,
        "details": "L1／L2 禮賓處提供寵物車借用（按金 HK$500）；寵物須置於寵物袋或推車，不可落地。條款以官網為準。",
        "official_url": "https://www.pacificplace.com.hk/zh-hk/services",
    },
    "ELEMENTS 圓方": {
        "is_allowed": True,
        "details": "室內須以寵物車、寵物袋或手抱方式；平台範圍可牽繩散步（≤1.5 米）。條款以 ELEMENTS 官網為準。",
        "official_url": "https://www.elementshk.com/tch/elements/promotions/petfriendly2024",
    },
    "AIRSIDE": {
        "is_allowed": True,
        "details": "設寵物共融區及借用服務；室內須以寵物袋或推車載運、不落地。條款以官網「寵物友善」專頁為準。",
        "official_url": "https://www.airside.com.hk/zh-hk/visit/pet-friendly-paradise",
    },
    "新都城中心": {
        "is_allowed": True,
        "details": "戶外平台歡迎寵物；室內須以寵物袋或推車載運。條款以官網服務頁及現場告示為準。",
        "official_url": "https://www.metrocity1.com/services/",
    },
    "將軍澳中心 Park Central": {
        "is_allowed": True,
        "details": "寵物須置於寵物袋或推車。條款以官網政策頁為準。",
        "official_url": "https://www.park-central.com.hk/tc-policy/",
    },
    "The Mills 南豐紗廠": {
        "is_allowed": True,
        "details": "室內及戶外均歡迎寵物；犬隻須全程佩戴牽引繩並妥善管控。條款以官網 Pet-Friendly 專頁為準。",
        "official_url": "https://www.themills.com.hk/pet-friendly/",
    },
    "PopCorn": {
        "is_allowed": False,
        "details": "PopCorn 1 允許符合規範的寵物進入；PopCorn 2 不允許攜帶寵物（導盲犬除外）。條款以 MTR 商場守則為準。",
        "official_url": "https://www.popcorntko.com.hk/tch/facilities-and-services",
    },
    "國際金融中心商場": {
        "is_allowed": True,
        "details": "家養貓狗可進入；室內須手抱或置於寵物手推車／攜帶包內。條款以 ifc mall 寵物政策頁為準。",
        "official_url": "https://ifc.com.hk/tc/mall/pet-policy/",
    },
    "海港城": {
        "is_allowed": False,
        "details": "商場活動守則一般禁止攜帶寵物（導盲犬除外）；請向顧客服務處查詢最新規定。條款以官網為準。",
        "official_url": "https://www.harbourcity.com.hk/tc/explore-hc/services-facilities/concierge/",
    },
    "朗豪坊": {
        "is_allowed": False,
        "details": "禮賓處提供寵物車借用；一般室內商場規定請向商場查詢。條款以官網服務頁為準。",
        "official_url": "https://www.langhamplace.com.hk/visit-us/lp-services",
    },
    "時代廣場": {
        "is_allowed": False,
        "details": "室內商場不允許寵物（導盲犬除外）。條款以官網服務及設施頁為準。",
        "official_url": "https://timessquare.com.hk/service-and-facilities/",
    },
    "又一城": {
        "is_allowed": True,
        "details": "歡迎攜同毛孩到訪；LG2 顧客服務處提供寵物車及寵物墊借用。條款以官網 Welcome Pets 頁為準。",
        "official_url": "https://www.festivalwalk.com.hk/zh-hk/happenings/welcome-pets",
    },
}

CURATED_HOTELS: dict[str, dict[str, Any]] = {
    "海洋公園萬豪": {
        "is_allowed": True,
        "details": "酒店設寵物友善住宿計劃（需預約及附加費）；條款以 Marriott 官網最新公告為準。",
        "official_url": "https://www.marriott.com/en-us/destinations/china/hong-kong/pet-friendly-hotels.mi",
    },
}

POLICY_LINK_PATTERNS: list[tuple[int, str]] = [
    (120, r"pet[-_]?friendly|pet[-_]?policy|pets?[-_]?park|petfriendly|welcome[-_]?pets|寵物友善|寵物友好|寵物同樂|寵物政策|寵物進場|歡迎寵物|毛孩|pet-friendly-paradise"),
    (90, r"/faq|frequently-asked|常見問題|守則|terms|條款|guidelines|指引|/policy"),
    (70, r"/services|/facilities|facilities-and-services|/visit/|服務及設施|customer-care|concierge"),
    (50, r"\bpet\b|寵物|dog|犬"),
]

POSITIVE_KEYWORDS = (
    "寵物友好", "寵物友善", "pet-friendly", "pet friendly", "歡迎寵物", "歡迎毛孩",
    "寵物進場", "寵物推車", "寵物袋", "pets park", "毛孩", "pet policy", "welcome pets",
)
NEGATIVE_KEYWORDS = (
    "禁止攜帶寵物", "不可帶寵物", "不可攜帶寵物", "不允許攜帶寵物", "不得攜帶寵物",
    "no pets", "pets are not allowed", "not permitted to bring pets", "導盲犬除外",
)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).lower()


def merge_policy(base_url: str, curated: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_PET)
    if curated:
        out.update(curated)
        if not out.get("official_url"):
            out["official_url"] = base_url or ""
    else:
        out["official_url"] = base_url or ""
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


def score_policy_link(href: str, label: str, page_url: str) -> int:
    combined = f"{label} {href}"
    score = 0
    for points, pattern in POLICY_LINK_PATTERNS:
        if re.search(pattern, combined, re.I):
            score += points
    path = urlparse(urljoin(page_url, href)).path.lower()
    if path.count("/") >= 2 and path not in ("/", "/zh-hk", "/zh-hant", "/tch", "/tc", "/en", "/index"):
        score += 12
    if re.search(r"login|signup|/shop|/store|/event|promotion|/media/|\.pdf|privacy", combined, re.I):
        score -= 30
    return score


def discover_policy_url(soup: BeautifulSoup, page_url: str) -> tuple[str, int]:
    base_netloc = urlparse(page_url).netloc.lower()
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = urljoin(page_url, href).split("#")[0]
        if urlparse(abs_url).netloc.lower() != base_netloc:
            continue
        label = anchor.get_text(" ", strip=True) or ""
        score = score_policy_link(href, label, page_url)
        if score > 0:
            candidates.append((score, abs_url))
    if not candidates:
        return page_url, 0
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1], candidates[0][0]


def parse_html(html: str) -> tuple[BeautifulSoup, str]:
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup required")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return soup, text


def analyze_html(html: str, page_url: str, *, policy_url: str | None = None) -> dict[str, Any]:
    if BeautifulSoup is None:
        return merge_policy(policy_url or page_url, None)
    soup, text = parse_html(html)
    discovered_url, discovered_score = discover_policy_url(soup, page_url)
    best_url = policy_url or discovered_url
    if not policy_url and discovered_score >= POLICY_FETCH_MIN_SCORE:
        best_url = discovered_url
    lowered = text.lower()
    negative_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in lowered)
    positive_hits = [kw for kw in POSITIVE_KEYWORDS if kw.lower() in lowered]
    if positive_hits and negative_hits <= len(positive_hits):
        snippet = extract_snippet(text, positive_hits[0]) or "官網提及寵物友善規範，詳情請參閱連結。"
        return {
            "is_allowed": True,
            "details": f"{snippet}（條款以官網為準）",
            "official_url": best_url,
        }
    if negative_hits and not positive_hits:
        return {
            "is_allowed": False,
            "details": "官網提及禁止或限制攜帶寵物（導盲犬除外）。條款以官網為準。",
            "official_url": best_url,
        }
    return merge_policy(best_url, None)


def http_get(client: httpx.Client, url: str) -> httpx.Response | None:
    try:
        response = client.get(url)
        if response.status_code >= 400:
            return None
        return response
    except Exception:
        return None


def fetch_policy(url: str) -> dict[str, Any]:
    if not url or not httpx:
        return merge_policy(url, None)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=TIMEOUT,
            headers=headers,
            verify=False,
        ) as client:
            response = http_get(client, url)
            if response is None:
                return merge_policy(url, None)
            landing_url = str(response.url)
            soup, _ = parse_html(response.text)
            policy_url, policy_score = discover_policy_url(soup, landing_url)
            if policy_score >= POLICY_FETCH_MIN_SCORE and policy_url != landing_url:
                nested = http_get(client, policy_url)
                if nested is not None:
                    return analyze_html(nested.text, str(nested.url), policy_url=str(nested.url))
            return analyze_html(response.text, landing_url, policy_url=policy_url if policy_score >= POLICY_FETCH_MIN_SCORE else None)
    except Exception:
        return merge_policy(url, None)


def policy_for_mall(mall: dict[str, Any], *, scrape: bool, force: bool) -> tuple[dict[str, Any], str]:
    if mall.get("pet_friendly") and not force:
        return mall["pet_friendly"], "skip"
    name = str(mall.get("mall_name") or "")
    base_url = str(mall.get("mall_url") or mall.get("official_home") or "")
    curated = resolve_curated(name, CURATED_MALLS)
    if curated:
        return merge_policy(base_url, curated), "curated"
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
        return merge_policy(base_url, curated), "curated"
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

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

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
