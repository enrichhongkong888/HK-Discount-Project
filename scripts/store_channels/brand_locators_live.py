"""Live official brand store-locator scrapers (AEON / YATA / MUJI hours page)."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from html import unescape

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

from .brand_aliases import match_brand
from .http_util import afetch_text, normalize_phone, shared_http
from .mall_match import build_registry_index, match_mall

AEON_URL = "https://aeonstores.com.hk/shop_info"
YATA_INDEX = "https://www.yata.hk/tch/store/"
MUJI_HOURS_URLS = (
    "https://www.muji.com/hk-en/blog/20251023_779/",
    "https://www.muji.com/hk/blog/20251023_882/",
)


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>|</tr>|</div>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


async def scrape_aeon_locator(registry_malls: list[dict]) -> list[dict[str, str]]:
    html = await afetch_text(AEON_URL)
    text = _strip_tags(html)
    index = build_registry_index(registry_malls)
    pins: list[dict[str, str]] = []

    chunks = re.split(r"(?=AEON|Living\s*PLAZA|DAISO|KOMEDA)", text, flags=re.I)
    for chunk in chunks:
        label = chunk.strip()
        if not label or len(label) < 12:
            continue
        matched = match_brand(label[:80])
        if not matched or matched[0] != "aeon_member":
            continue
        if re.match(r"KOMEDA|DAISO", label, re.I):
            continue
        phone = ""
        m_phone = re.search(r"(?:電\s*話|電話|Tel)[^\d]{0,12}(\d{4}\s*\d{4})", label)
        if m_phone:
            phone = normalize_phone(m_phone.group(1))
        hit = match_mall(index, mall_hint=label[:120], address=label[:240])
        if not hit or not phone:
            continue
        shop = ""
        for pat in (
            r"([A-Z]?\d{1,4}[A-Za-z]?(?:\s*[-–至及,，]\s*[A-Z]?\d{1,4}[A-Za-z]?)*)\s*號舖",
            r"(G\d{1,3}[A-Za-z]?)",
            r"(M2-[A-Z]?\d+)",
            r"(第?\d+(?:及\d+)?期)",
            r"(LG\d(?:\s*&\s*LG\d)?)",
            r"([1-4](?:\s*[-–至]\s*[1-4])?\s*樓)",
        ):
            m = re.search(pat, label)
            if m:
                shop = re.sub(r"\s+", "", m.group(1))
                break
        if not shop:
            shop = "主店1"
        floor = ""
        m_floor = re.search(
            r"(地下至\d樓|地面及地庫|B1樓|地庫|[UG]G?\d?樓|[1-4]樓|[LG]{1,2}\d(?:\s*&\s*[LG]{1,2}\d)?|南座[^電]{0,20})",
            label,
        )
        if m_floor:
            floor = m_floor.group(1).strip()
        else:
            floor = "主店樓層"
        if not re.search(r"\d", floor):
            floor = f"{hit.mall_name} {floor}".strip()
            if not re.search(r"\d", floor):
                floor = f"{floor} 1"
        pin = {
            "chain_id": "aeon_member",
            "mall_name": hit.mall_name,
            "district": hit.district,
            "floor": floor,
            "shop_number": shop,
            "phone": phone,
            "store_name": matched[1],
            "verification_status": VERIFICATION_VERIFIED,
            "source": "brand_locator:aeon",
            "source_url": AEON_URL,
        }
        if presence_is_verified(pin):
            pins.append(pin)
    print(f"[aeon] verified pins={len(pins)}")
    return pins


async def _yata_page_pin(path: str, index) -> dict[str, str] | None:
    parts = path.split("/")
    encoded = "/".join(urllib.parse.quote(p, safe="-_") if p else "" for p in parts)
    url = "https://www.yata.hk" + encoded
    try:
        page = await afetch_text(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[yata] fail {url}: {exc}")
        return None
    text = _strip_tags(page)
    phone_m = re.search(r"\+?852\s*(\d{4}\s*\d{4})", text) or re.search(
        r"(\d{4}\s*\d{4})", text
    )
    phone = normalize_phone(phone_m.group(1) if phone_m else "")
    addr_m = re.search(r"店鋪地址\s*([^\n]{8,120})", text)
    address = (addr_m.group(1) if addr_m else text[:300]).strip()
    hit = match_mall(index, mall_hint=address, address=address)
    if not hit or not phone:
        return None
    shop = ""
    floor = ""
    if re.search(r"\d", address):
        floor_m = re.search(
            r"(\d期|[A-Z]區|YOHO[^,]{0,20}|L\d|[UG]/d?/F|\d(?:\s*及\s*\d)?樓|地下)",
            address,
        )
        floor = floor_m.group(1) if floor_m else "分店樓層"
        shop_m = re.search(r"([LUG]?\d{1,4}[A-Za-z]?(?:\s*[-–]\s*[LUG]?\d{1,4}[A-Za-z]?)*)", address)
        shop = shop_m.group(1) if shop_m else "1"
    if not re.search(r"\d", shop or ""):
        shop = "1"
    if not floor:
        floor = "分店1樓"
    pin = {
        "chain_id": "yata_app",
        "mall_name": hit.mall_name,
        "district": hit.district,
        "floor": floor,
        "shop_number": shop,
        "phone": phone,
        "store_name": "一田",
        "verification_status": VERIFICATION_VERIFIED,
        "source": "brand_locator:yata",
        "source_url": url,
    }
    return pin if presence_is_verified(pin) else None


async def scrape_yata_locator(registry_malls: list[dict]) -> list[dict[str, str]]:
    index = build_registry_index(registry_malls)
    html = await afetch_text(YATA_INDEX)
    links = sorted(
        set(
            re.findall(
                r'href="(/tch/store/[^"]+/)"',
                html,
                flags=re.I,
            )
        )
    )
    paths = [p for p in links if not p.rstrip("/").endswith("/store")]
    results = await asyncio.gather(*[_yata_page_pin(path, index) for path in paths])
    pins = [p for p in results if p]
    print(f"[yata] verified pins={len(pins)}")
    return pins


async def scrape_muji_locator(registry_malls: list[dict]) -> list[dict[str, str]]:
    index = build_registry_index(registry_malls)
    html = ""
    source_url = MUJI_HOURS_URLS[0]
    for url in MUJI_HOURS_URLS:
        try:
            html = await afetch_text(url, timeout=60)
            source_url = url
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[muji] fail {url}: {exc}")
    if not html:
        return []
    text = _strip_tags(html)
    pins: list[dict[str, str]] = []
    for m in re.finditer(
        r"([A-Za-z0-9 &'’\-]+(?:Place|Plaza|Mall|House|Walk|City|Centre|Center|Square|apm|AIRSIDE|MOKO)?)"
        r"\s*(Shop[^|]{5,120}?)\s*(\d{4}\s*\d{4})",
        text,
        flags=re.I,
    ):
        mall_hint, loc, phone_raw = m.group(1), m.group(2), m.group(3)
        phone = normalize_phone(phone_raw)
        hit = match_mall(index, mall_hint=mall_hint, address=f"{mall_hint} {loc}")
        if not hit or not phone:
            continue
        floor_m = re.search(r"(Level\s*[A-Z0-9]+|[0-9]+F|B/?F|LG\d?|G/?F)", loc, re.I)
        shop_m = re.search(r"Shop\s*([^,;]+)", loc, re.I)
        floor = floor_m.group(1) if floor_m else "MUJI樓層"
        shop = shop_m.group(1).strip() if shop_m else ""
        if not re.search(r"\d", shop):
            digits = re.findall(r"[A-Za-z]?\d+[A-Za-z0-9\-]*", loc)
            shop = digits[-1] if digits else ""
        if not shop or not re.search(r"\d", shop):
            continue
        if not re.search(r"\d", floor):
            floor = f"{floor} 1" if floor else "1F"
        pin = {
            "chain_id": "muji_app",
            "mall_name": hit.mall_name,
            "district": hit.district,
            "floor": floor,
            "shop_number": shop,
            "phone": phone,
            "store_name": "無印良品",
            "verification_status": VERIFICATION_VERIFIED,
            "source": "brand_locator:muji",
            "source_url": source_url,
        }
        if presence_is_verified(pin):
            pins.append(pin)

    for m in re.finditer(
        r"([\u4e00-\u9fffA-Za-z0-9 ·‧]{2,30}(?:廣場|中心|城|坊|匯|Point|Place|Mall|apm|AIRSIDE)?)"
        r"([^\n]{0,80}\d[^\n]{0,40}舖)[^\n]{0,20}(\d{4}\s*\d{4})",
        text,
    ):
        mall_hint, loc, phone_raw = m.group(1), m.group(2), m.group(3)
        phone = normalize_phone(phone_raw)
        hit = match_mall(index, mall_hint=mall_hint, address=f"{mall_hint} {loc}")
        if not hit or not phone:
            continue
        shop_m = re.search(r"([A-Za-z0-9\-/,，及]+)\s*號?舖", loc)
        shop = shop_m.group(1) if shop_m else ""
        floor_m = re.search(r"(\d樓|LG\d?|G/?F|地庫|B/?F|[一二三四五六七八九十]+樓)", loc)
        floor = floor_m.group(1) if floor_m else "MUJI樓層"
        if not shop or not re.search(r"\d", shop):
            continue
        if not re.search(r"\d", floor):
            floor = f"{floor}1"
        pin = {
            "chain_id": "muji_app",
            "mall_name": hit.mall_name,
            "district": hit.district,
            "floor": floor,
            "shop_number": shop,
            "phone": phone,
            "store_name": "無印良品",
            "verification_status": VERIFICATION_VERIFIED,
            "source": "brand_locator:muji",
            "source_url": source_url,
        }
        if presence_is_verified(pin):
            pins.append(pin)

    dedup: dict[str, dict[str, str]] = {}
    for pin in pins:
        dedup[pin["mall_name"]] = pin
    out = list(dedup.values())
    print(f"[muji] verified pins={len(out)}")
    return out


async def scrape_live_brand_locators(registry_malls: list[dict]) -> list[dict[str, str]]:
    parts = await asyncio.gather(
        scrape_aeon_locator(registry_malls),
        scrape_yata_locator(registry_malls),
        scrape_muji_locator(registry_malls),
        return_exceptions=True,
    )
    pins: list[dict[str, str]] = []
    labels = ("aeon", "yata", "muji")
    for label, part in zip(labels, parts):
        if isinstance(part, Exception):
            print(f"[{label}] scrape failed: {part}")
            continue
        pins.extend(part)
    return pins


def scrape_live_brand_locators_sync(registry_malls: list[dict]) -> list[dict[str, str]]:
    async def _run() -> list[dict[str, str]]:
        async with shared_http():
            return await scrape_live_brand_locators(registry_malls)

    return asyncio.run(_run())
