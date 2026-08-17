"""Scrape Sino Land mall public shop directories (S⁺ REWARDS malls).

Supported sites share the same CMS shape as Olympian City:
  - index: /tc/Shop embeds #globalSearchData JSON (HTML-escaped)
  - detail: /tc/Shop/{id} or /tc/Dining/{id} lists floor, unit, phone
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import re
from typing import Any

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

from .brand_aliases import match_brand
from .http_util import afetch_text, normalize_phone, shared_http

PHONE_RE = re.compile(r"(?:\+?852[-\s]?)?(?:\d{4}[\s-]?\d{4}|\d{8})")


SINO_MALLS: list[dict[str, str]] = [
    {
        "group": "splus_rewards",
        "mall_name": "奧海城",
        "district": "油尖旺區",
        "shop_index": "https://www.olympiancity.com.hk/tc/Shop",
        "dining_index": "https://www.olympiancity.com.hk/tc/Dining",
    },
    {
        "group": "splus_rewards",
        "mall_name": "屯門市廣場",
        "district": "屯門區",
        "shop_index": "https://www.tmtp.com.hk/tc/Shop",
        "dining_index": "https://www.tmtp.com.hk/tc/Dining",
    },
    {
        "group": "splus_rewards",
        "mall_name": "荃新天地",
        "district": "荃灣區",
        "shop_index": "https://www.citywalk.com.hk/tc/Shop",
        "dining_index": "https://www.citywalk.com.hk/tc/Dining",
    },
]


async def fetch(url: str, *, timeout: int = 45) -> str:
    return await afetch_text(url, timeout=timeout)


def parse_global_search_data(page: str) -> dict[str, Any]:
    m = re.search(
        r"id=['\"]globalSearchData['\"][^>]*>(\{.*?\})</div>",
        page,
        re.S,
    )
    if not m:
        raise ValueError("globalSearchData not found")
    raw = html_lib.unescape(m.group(1))
    return json.loads(raw)


def parse_detail_fields(detail_html: str, store_name: str) -> dict[str, str]:
    text = re.sub(r"<script[\s\S]*?</script>", " ", detail_html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [html_lib.unescape(x).strip() for x in text.splitlines()]
    lines = [x for x in lines if x]

    location_line = ""
    phone = ""
    short_name = store_name.split("(")[0].strip()
    try:
        idx = next(i for i, line in enumerate(lines) if short_name and short_name in line)
    except StopIteration:
        idx = 0
    window = lines[idx : idx + 16]

    mall_markers = ("奧海城", "屯門市廣場", "荃新天地", "Citywalk", "CITYWALK")
    for line in window:
        if not phone:
            m = PHONE_RE.search(line)
            if m and not re.search(r"(am|pm|星期一|星期|營業)", line, re.I):
                phone = normalize_phone(m.group(0))

        if location_line:
            continue
        if any(marker in line for marker in mall_markers) and re.search(r"\d", line):
            location_line = line
            continue
        if (
            re.search(r"(G/F|UG/F|\d/F|G樓|UG樓|\d樓)", line)
            and re.search(r"\d", line)
            and short_name not in line
            and not re.search(r"(星期一|星期|am|pm|http)", line, re.I)
        ):
            location_line = line

    floor = ""
    shop_number = ""
    if location_line:
        parts = [p.strip() for p in re.split(r"[,，]", location_line) if p.strip()]
        if len(parts) >= 3:
            floor = f"{parts[0]} {parts[1]}".strip()
            shop_number = parts[-1]
        elif len(parts) == 2:
            floor = parts[0]
            shop_number = parts[1]
        else:
            tokens = re.split(r"\s+", location_line)
            shop_number = next((t for t in reversed(tokens) if re.search(r"\d", t)), location_line)
            floor = location_line.replace(shop_number, "").strip(" ,，")

    if (not shop_number or not re.search(r"\d", shop_number)) and short_name:
        for line in window[:4]:
            embedded = re.search(
                r"\(([A-Za-z]?\d+[A-Za-z]?(?:-[A-Za-z]?\d+[A-Za-z]?)?)\s*[,，]\s*([^)]+)\)",
                line,
            )
            if embedded:
                shop_number = embedded.group(1)
                if not floor:
                    floor = embedded.group(2).strip()
                break

    return {
        "floor": floor,
        "shop_number": shop_number,
        "phone": phone,
        "location_line": location_line,
    }


def collect_brand_candidates(search_data: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in search_data.values():
        if not isinstance(row, dict):
            continue
        names = row.get("name") or {}
        zh = str(names.get("zh-Hant") or "").strip()
        en = str(names.get("en") or "").strip()
        label = zh or en
        matched = match_brand(label) or match_brand(en)
        if not matched:
            continue
        chain_id, store_name = matched
        link = str(row.get("link") or "").strip()
        if not link:
            continue
        out.append(
            {
                "chain_id": chain_id,
                "store_name": store_name,
                "directory_name": label,
                "link": link,
            }
        )
    return out


async def _detail_pin(cand: dict[str, str], cfg: dict[str, str]) -> dict[str, str] | None:
    link = cand["link"]
    try:
        detail = await fetch(link)
    except Exception as exc:  # noqa: BLE001
        print(f"[sino] detail fail {link}: {exc}")
        return None
    fields = parse_detail_fields(detail, cand["directory_name"])
    pin = {
        "chain_id": cand["chain_id"],
        "mall_name": cfg["mall_name"],
        "district": cfg["district"],
        "floor": fields["floor"],
        "shop_number": fields["shop_number"],
        "phone": fields["phone"],
        "store_name": cand["store_name"],
        "verification_status": VERIFICATION_VERIFIED,
        "source": f"sino_directory:{cfg['group']}",
        "source_url": link,
    }
    if presence_is_verified(pin):
        return pin
    print(
        f"[sino] reject {cand['store_name']}@{cfg['mall_name']} "
        f"floor={fields['floor']!r} shop={fields['shop_number']!r} phone={fields['phone']!r}"
    )
    return None


async def scrape_sino_mall(cfg: dict[str, str]) -> list[dict[str, str]]:
    pins: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for index_url in (cfg["shop_index"], cfg.get("dining_index", "")):
        if not index_url:
            continue
        try:
            page = await fetch(index_url)
            data = parse_global_search_data(page)
        except Exception as exc:  # noqa: BLE001
            print(f"[sino] skip index {index_url}: {exc}")
            continue
        candidates = collect_brand_candidates(data)
        print(f"[sino] {cfg['mall_name']} {index_url} candidates={len(candidates)}")
        fresh = []
        for cand in candidates:
            link = cand["link"]
            if link in seen_links:
                continue
            seen_links.add(link)
            fresh.append(cand)
        results = await asyncio.gather(*[_detail_pin(c, cfg) for c in fresh])
        pins.extend(p for p in results if p)
    return pins


async def scrape_all_sino_directories() -> list[dict[str, str]]:
    groups = await asyncio.gather(*(scrape_sino_mall(cfg) for cfg in SINO_MALLS))
    all_pins: list[dict[str, str]] = []
    for group in groups:
        all_pins.extend(group)
    return all_pins


def scrape_all_sino_directories_sync() -> list[dict[str, str]]:
    async def _run() -> list[dict[str, str]]:
        async with shared_http():
            return await scrape_all_sino_directories()

    return asyncio.run(_run())
