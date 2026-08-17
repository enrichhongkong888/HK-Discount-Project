"""SHKP The Point mall directories (YOHO Strapi + New Town Plaza WordPress map)."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

from .brand_aliases import match_brand
from .http_util import afetch_json, afetch_text, normalize_phone, shared_http

CMS_YOHO = "https://cms.yohomall.hk"
NTP_SHOPPING = "https://www.newtownplaza.com.hk/zh-hant/shopping"

YOHO_MALL = {"mall_name": "YOHO MALL 形點", "district": "元朗區"}
NTP_MALL = {"mall_name": "新城市廣場", "district": "沙田區"}


def _attrs(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    if "attributes" in node and isinstance(node["attributes"], dict):
        return node["attributes"]
    return node


def _name(attrs: dict[str, Any]) -> str:
    for key in ("display_name", "name_zh", "name_tc", "name", "name_en"):
        val = attrs.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _phone(attrs: dict[str, Any]) -> str:
    for key in ("phone", "tel", "telephone"):
        val = attrs.get(key)
        if val:
            phone = normalize_phone(str(val))
            if phone:
                return phone
    return ""


def _yoho_location(attrs: dict[str, Any]) -> tuple[str, str]:
    rel = attrs.get("mall_shop_number") or {}
    data = rel.get("data") if isinstance(rel, dict) else None
    loc = _attrs(data) if data else {}
    floor = str(loc.get("floor") or attrs.get("floor") or "").strip()
    shop = str(loc.get("shop_number") or attrs.get("shop_number") or "").strip()
    mall_code = str(loc.get("mall") or "").strip()
    if mall_code:
        label = {
            "mall-1": "YOHO MALL I",
            "mall-2": "YOHO MALL II",
            "mall-mix": "YOHO MIX",
        }.get(mall_code, mall_code)
        floor = f"{label} {floor}".strip()
    return floor, shop


async def scrape_yoho_brand_pins(*, page_size: int = 100) -> list[dict[str, str]]:
    pins: list[dict[str, str]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "pagination[page]": page,
                "pagination[pageSize]": page_size,
                "populate": "mall_shop_number",
            }
        )
        payload = await afetch_json(f"{CMS_YOHO}/api/shops?{query}")
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            attrs = _attrs(row)
            label = _name(attrs)
            matched = match_brand(label)
            if not matched:
                continue
            chain_id, store_name = matched
            floor, shop_number = _yoho_location(attrs)
            phone = _phone(attrs)
            pin = {
                "chain_id": chain_id,
                "mall_name": YOHO_MALL["mall_name"],
                "district": YOHO_MALL["district"],
                "floor": floor,
                "shop_number": shop_number,
                "phone": phone,
                "store_name": store_name,
                "verification_status": VERIFICATION_VERIFIED,
                "source": "shkp_directory:the_point:yoho",
                "source_url": f"{CMS_YOHO}/api/shops/{row.get('id')}",
            }
            if presence_is_verified(pin):
                pins.append(pin)
        meta = (payload.get("meta") or {}).get("pagination") or {}
        page_count = int(meta.get("pageCount") or page)
        if page >= page_count:
            break
        page += 1
    print(f"[yoho] verified brand pins={len(pins)}")
    return pins


def _parse_ntp_shop_map(html: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'"([^"]+)"\s*:\s*\{\s*"url"\s*:\s*"(?P<url>[^"]+)"\s*,\s*"description"\s*:\s*"(?P<desc>[^"]*)"'
        r'\s*,\s*"floor"\s*:\s*"(?P<floor>[^"]*)"[^}]*?"name"\s*:\s*"(?P<name>[^"]+)"',
        re.S,
    )
    rows: list[dict[str, str]] = []
    for m in pattern.finditer(html):
        url = m.group("url").replace("\\/", "/")
        desc = m.group("desc").replace("\\/", "/").replace('\\"', '"')
        name = m.group("name").replace("\\/", "/").replace('\\"', '"')
        try:
            name = bytes(name, "utf-8").decode("unicode_escape")
        except Exception:  # noqa: BLE001
            pass
        try:
            desc = bytes(desc, "utf-8").decode("unicode_escape")
        except Exception:  # noqa: BLE001
            pass
        rows.append(
            {
                "unit": m.group(1),
                "url": url,
                "description": desc,
                "floor_code": m.group("floor"),
                "name": name,
            }
        )
    return rows


def _ntp_floor_shop(description: str, unit: str, floor_code: str) -> tuple[str, str]:
    desc = description.upper()
    phase = ""
    if "PHASE III" in desc or "PHASE 3" in desc:
        phase = "三期"
    elif "PHASE I" in desc or "PHASE 1" in desc:
        phase = "一期"
    floor = ""
    m = re.search(r"\b(L\d|LG|G|UG|B\d?)\b", description, re.I)
    if m:
        floor = m.group(1).upper()
    elif "_" in floor_code:
        floor = floor_code.split("_", 1)[-1]
    else:
        floor = floor_code or "L?"
    if phase:
        floor = f"{phase} {floor}".strip()
    shop = unit
    m2 = re.search(r"SHOP\s+([A-Z0-9\-]+)", description, re.I)
    if m2:
        shop = m2.group(1)
    return floor, shop


async def _ntp_detail_phone(url: str) -> str:
    if url.startswith("/"):
        url = "https://www.newtownplaza.com.hk" + url
    html = await afetch_text(url)
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    for line in text.splitlines():
        line = line.strip()
        if not line or "http" in line.lower():
            continue
        if re.fullmatch(r"\d{4}\s*\d{4}", line) or re.fullmatch(r"\+?852\s*\d{4}\s*\d{4}", line):
            phone = normalize_phone(line)
            if phone:
                return phone
        m = re.search(r"(?:電話|Tel)[^\d]{0,8}(\d{4}\s*\d{4})", line, re.I)
        if m:
            return normalize_phone(m.group(1))
    for m in re.finditer(r"\b(\d{4}\s*\d{4})\b", text):
        phone = normalize_phone(m.group(1))
        if phone and phone.startswith(("2", "3", "5", "6", "9")):
            return phone
    return ""


async def _ntp_brand_pin(row: dict[str, str]) -> dict[str, str] | None:
    matched = match_brand(row["name"])
    if not matched:
        return None
    chain_id, store_name = matched
    floor, shop = _ntp_floor_shop(row["description"], row["unit"], row["floor_code"])
    url = row["url"]
    try:
        phone = await _ntp_detail_phone(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[ntp] detail fail {url}: {exc}")
        phone = ""
    pin = {
        "chain_id": chain_id,
        "mall_name": NTP_MALL["mall_name"],
        "district": NTP_MALL["district"],
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "store_name": store_name,
        "verification_status": VERIFICATION_VERIFIED,
        "source": "shkp_directory:the_point:ntp",
        "source_url": url if url.startswith("http") else f"https://www.newtownplaza.com.hk{url}",
    }
    if presence_is_verified(pin):
        return pin
    print(f"[ntp] reject {store_name} floor={floor!r} shop={shop!r} phone={phone!r}")
    return None


async def scrape_ntp_brand_pins() -> list[dict[str, str]]:
    html = await afetch_text(NTP_SHOPPING)
    rows = _parse_ntp_shop_map(html)
    seen_urls: set[str] = set()
    work: list[dict[str, str]] = []
    for row in rows:
        if not match_brand(row["name"]):
            continue
        url = row["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        work.append(row)
    results = await asyncio.gather(*[_ntp_brand_pin(row) for row in work])
    pins = [p for p in results if p]
    print(f"[ntp] verified brand pins={len(pins)}")
    return pins


async def scrape_all_shkp_directories() -> list[dict[str, str]]:
    yoho_task = scrape_yoho_brand_pins()
    ntp_task = scrape_ntp_brand_pins()
    yoho, ntp = await asyncio.gather(yoho_task, ntp_task, return_exceptions=True)
    pins: list[dict[str, str]] = []
    if isinstance(yoho, Exception):
        print(f"[yoho] scrape failed: {yoho}")
    else:
        pins.extend(yoho)
    if isinstance(ntp, Exception):
        print(f"[ntp] scrape failed: {ntp}")
    else:
        pins.extend(ntp)
    return pins


def scrape_all_shkp_directories_sync() -> list[dict[str, str]]:
    async def _run() -> list[dict[str, str]]:
        async with shared_http():
            return await scrape_all_shkp_directories()

    return asyncio.run(_run())
