"""
HK-Deal 多來源優惠資料抓取器。

所有來源均以 Playwright 載入，並由 sources.json 設定來源網址、CSS selector、
分類與地區；這是因為規劃筆記沒有提供商場及自助餐平台的固定網址或 DOM 結構。

建立設定檔：
    python scraper.py --write-example-config

執行全部來源：
    python scraper.py --config data/sources.json

只執行指定群組：
    python scraper.py --config data/sources.json --targets malls,buffets,theme-parks
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


USER_AGENT = "HK-Deal-Research-Bot/2.1"
CATEGORIES = frozenset({"商場優惠", "機票", "自助餐", "主題樂園"})
TARGET_GROUPS = frozenset({"malls", "flights", "buffets", "theme-parks"})
HK_DISTRICTS = (
    "中西區", "灣仔區", "東區", "南區", "油尖旺區", "深水埗區", "九龍城區", "黃大仙區",
    "觀塘區", "葵青區", "荃灣區", "屯門區", "元朗區", "北區", "大埔區", "沙田區", "西貢區", "離島區",
)
DEFAULT_SELECTORS = {
    "card": "article, .deal-card, .offer-card, [data-deal]",
    "title": ".deal-title, .offer-title, h2, h3",
    "discount_info": ".discount-info, .discount, .offer-description, .description",
    "promo_code": ".promo-code, .coupon-code, [data-promo-code]",
    "start_date": ".start-date, .valid-from, .start, [data-start-date]",
    "expiry_date": ".expiry-date, .expiry, .valid-until, time",
    "store_name": ".store-name, .merchant-name, .brand-name, [data-store-name]",
    "floor": ".floor, .store-floor, [data-floor]",
    "shop_number": ".shop-number, .shop-no, .unit-number, [data-shop-number]",
    "phone": ".store-phone, .phone, [data-phone]",
    "link": "a[href]",
    "image": "img",
    "district": ".district, .location, [data-district]",
    "daily_special": ".daily-special, .today-only, [data-daily-special='true']",
}
PROMO_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,50}$")
PROMO_CODE_IN_TEXT = re.compile(
    r"(?:優惠碼|折扣碼|promo\s*code|coupon\s*code|code)\s*[:：]?\s*([A-Za-z0-9_-]{3,50})",
    re.IGNORECASE,
)
EVERGREEN_MALL_POLICY_PATTERN = re.compile(
    r"(?:免費\s*)?泊車|parking|長期|全年|常設",
    re.IGNORECASE,
)
PLACEHOLDER_STORE_FIELD_PATTERN = re.compile(
    r"(?i)^(n/?a|null|none|undefined|unknown|xxx+|test|placeholder|待定|\.+|-)$"
)
SUBSTANTIVE_STORE_DETAIL = re.compile(
    r"(港幣\s*\$?\s*\d|\$\s*\d|\d+\s*分|積分|印花|倍|折扣|回贈|現金券|電子券|"
    r"Point Dollar|H COIN|P-Coin|星星|印花|會員價|優惠價)"
)
ISO_DATE_PATTERN = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")
DAY_MONTH_YEAR_DATE_PATTERN = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})")
YEAR_MONTH_DAY_RANGE_PATTERN = re.compile(
    r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*(?:-|–|至)\s*(\d{1,2})[./-](\d{1,2})"
)
CHINESE_DATE_PATTERN = re.compile(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
ENGLISH_DAY_MONTH_PATTERN = re.compile(
    r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)(?:\.?,?\s*(\d{4}))?",
    re.IGNORECASE,
)
ENGLISH_MONTH_DAY_PATTERN = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(\d{1,2})(?:\.?,?\s*(\d{4}))?",
    re.IGNORECASE,
)
MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class ScraperError(RuntimeError):
    """A source-specific error that must not stop other configured sources."""


@dataclass(frozen=True)
class Mall:
    mall_name: str
    district: str
    address: str
    phone: str | None
    network_phone: str | None
    mall_url: str | None


@dataclass(frozen=True)
class Offer:
    title: str
    category: str
    offer_type: str
    is_daily_special: bool
    is_evergreen: bool
    created_date: str
    created_at: str
    start_date: str
    discount_info: str
    details: str | None
    promo_code: str | None
    expiry_date: str
    source_url: str
    image_url: str | None
    district: str | None = None
    mall_name: str | None = None
    brand_name: str | None = None
    store_name: str | None = None
    floor: str | None = None
    shop_number: str | None = None
    phone: str | None = None
    source_name: str | None = None


@dataclass(frozen=True)
class SourceConfig:
    identifier: str
    enabled: bool
    target: str
    name: str
    url: str
    category: str
    offer_type: str
    selectors: dict[str, str]
    district: str | None
    mall: dict[str, Any] | None
    brand_name: str | None
    card_text_contains: str | None
    is_daily_special: bool
    is_evergreen: bool
    rolling_expiry_days: int | None
    details: str | None
    title_override: str | None
    start_date_override: str | None
    expiry_date_override: str | None
    load_more_selector: str | None
    max_load_more_clicks: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceConfig":
        required = ("id", "target", "name", "url", "category")
        missing = [field for field in required if not raw.get(field)]
        if missing:
            raise ScraperError(f"來源設定缺少欄位：{', '.join(missing)}")
        if raw["target"] not in TARGET_GROUPS:
            raise ScraperError(f"{raw['id']} 的 target 必須是：{', '.join(sorted(TARGET_GROUPS))}")
        if raw["category"] not in CATEGORIES:
            raise ScraperError(f"{raw['id']} 的 category 必須是：{', '.join(sorted(CATEGORIES))}")
        offer_type = raw.get("offer_type", "mall")
        if offer_type not in {"mall", "store"}:
            raise ScraperError(f"{raw['id']} 的 offer_type 必須是 mall 或 store")
        if not is_http_url(raw["url"]):
            raise ScraperError(f"{raw['id']} 的 url 不是有效 HTTP(S) URL")

        selectors = DEFAULT_SELECTORS.copy()
        custom_selectors = raw.get("selectors", {})
        if not isinstance(custom_selectors, dict) or not all(
            isinstance(value, str) for value in custom_selectors.values()
        ):
            raise ScraperError(f"{raw['id']} 的 selectors 必須是 CSS selector JSON 物件")
        selectors.update(custom_selectors)
        return cls(
            identifier=raw["id"],
            enabled=bool(raw.get("enabled", True)),
            target=raw["target"],
            name=raw["name"],
            url=raw["url"],
            category=raw["category"],
            offer_type=offer_type,
            selectors=selectors,
            district=raw.get("district"),
            mall=raw.get("mall"),
            brand_name=raw.get("brand_name"),
            card_text_contains=raw.get("card_text_contains"),
            is_daily_special=bool(raw.get("is_daily_special", False)),
            is_evergreen=bool(raw.get("is_evergreen", False)),
            rolling_expiry_days=(
                int(raw["rolling_expiry_days"]) if raw.get("rolling_expiry_days") is not None else None
            ),
            details=str(raw["details"]).strip() if raw.get("details") else None,
            title_override=optional_text(raw.get("title_override")),
            start_date_override=optional_iso_date(raw.get("start_date_override"), raw["id"]),
            expiry_date_override=optional_iso_date(raw.get("expiry_date_override"), raw["id"]),
            load_more_selector=raw.get("load_more_selector"),
            max_load_more_clicks=int(raw.get("max_load_more_clicks", 0)),
        )


class HttpClient:
    """robots.txt checking plus a 2–3 second delay before every HTTP request."""

    def __init__(self) -> None:
        self.session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })

    def wait(self) -> None:
        delay = random.uniform(2, 3)
        logging.debug("Polite delay: %.2f seconds", delay)
        time.sleep(delay)

    def ensure_allowed_by_robots(self, target_url: str) -> None:
        parsed = urlparse(target_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        self.wait()
        try:
            response = self.session.get(robots_url, timeout=20)
            if response.status_code == 404:
                logging.info("robots.txt 不存在（依標準視為未限制）：%s", robots_url)
                return
            response.raise_for_status()
        except requests.RequestException as error:
            raise ScraperError(f"無法讀取 robots.txt（停止抓取）：{error}") from error

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(USER_AGENT, target_url):
            raise ScraperError(f"robots.txt 不允許抓取：{target_url}")


class DynamicSourceScraper:
    """A configurable Playwright adapter for all currently planned dynamic sources."""

    def __init__(self, client: HttpClient, source: SourceConfig) -> None:
        self.client = client
        self.source = source

    def scrape(self) -> tuple[list[Offer], list[Mall]]:
        self.client.ensure_allowed_by_robots(self.source.url)
        html = self._load_page()
        soup = BeautifulSoup(html, "html.parser")
        offers = self._parse_offers(soup)
        malls = self._parse_mall(soup)
        return offers, malls

    def _load_page(self) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            logging.warning("Playwright 無法載入，改用靜態 HTML 後備模式：%s", error)
            self.client.wait()
            try:
                response = self.client.session.get(self.source.url, timeout=30)
                response.raise_for_status()
                if response.apparent_encoding:
                    response.encoding = response.apparent_encoding
                return response.text
            except requests.RequestException as request_error:
                raise ScraperError(f"無法以後備模式載入 {self.source.name}：{request_error}") from request_error

        async def load() -> str:
            self.client.wait()
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(user_agent=USER_AGENT, locale="zh-HK")
                await page.goto(self.source.url, wait_until="networkidle", timeout=45_000)
                for _ in range(self.source.max_load_more_clicks):
                    selector = self.source.load_more_selector
                    if not selector or await page.locator(selector).count() == 0:
                        break
                    self.client.wait()
                    await page.locator(selector).first.click()
                    await page.wait_for_load_state("networkidle", timeout=30_000)
                html = await page.content()
                await browser.close()
                return html

        try:
            return asyncio.run(load())
        except Exception as error:
            raise ScraperError(f"無法載入 {self.source.name}：{error}") from error

    def _parse_offers(self, soup: BeautifulSoup) -> list[Offer]:
        cards = soup.select(self.source.selectors["card"])
        if not cards:
            raise ScraperError("找不到優惠卡片；請更新 sources.json 的 selectors.card。")

        captured_at = datetime.now(timezone.utc).astimezone()
        today = captured_at.date()
        offers: list[Offer] = []
        for card in cards:
            title = self.source.title_override or select_text(card, self.source.selectors["title"]) or (
                self.source.name
                if self.source.offer_type == "mall" and self.source.is_evergreen and self.source.details
                else ""
            )
            discount_info = select_text(card, self.source.selectors["discount_info"]) or title
            if not title:
                continue

            card_text = card.get_text(" ", strip=True)
            if self.source.card_text_contains and self.source.card_text_contains not in card_text:
                continue
            is_daily_special = self.source.is_daily_special or bool(
                card.select_one(self.source.selectors["daily_special"])
            )
            raw_dates = select_text(card, self.source.selectors["expiry_date"]) or card_text
            start_date, expiry_date = parse_date_range(raw_dates, today)
            start_date = self.source.start_date_override or start_date
            expiry_date = self.source.expiry_date_override or expiry_date
            raw_start = select_text(card, self.source.selectors["start_date"])
            if raw_start:
                start_date = parse_expiry_date(raw_start, today) or start_date
            start_date = start_date or today.isoformat()
            is_evergreen = self.source.is_evergreen or (
                self.source.offer_type == "mall"
                and not is_daily_special
                and expiry_date is None
                and is_evergreen_mall_policy(title, discount_info, card_text)
            )
            # Daily specials may not advertise an end date. Their 1-day TTL is the expiry date.
            if not expiry_date and is_daily_special:
                expiry_date = today.isoformat()
            if not expiry_date and is_evergreen:
                # Evergreen policies remain valid until the source is explicitly
                # changed or disabled, while retaining a schema-compatible date.
                expiry_date = today.isoformat()
            if not expiry_date and self.source.rolling_expiry_days is not None:
                expiry_date = (today + timedelta(days=self.source.rolling_expiry_days)).isoformat()
            if not expiry_date:
                logging.warning("略過沒有有效 expiry_date 的一般優惠：%s", title)
                continue

            link = card if card.name == "a" and card.get("href") else card.select_one(self.source.selectors["link"])
            candidate_url = urljoin(self.source.url, link.get("href", "")) if link else self.source.url
            source_url = candidate_url if is_http_url(candidate_url) else self.source.url
            image = card.select_one(self.source.selectors["image"])
            image_source = (image.get("src") or image.get("data-src")) if image else None
            image_url = urljoin(self.source.url, image_source) if image_source else None
            raw_code = select_text(card, self.source.selectors["promo_code"])
            store_name = select_text(card, self.source.selectors["store_name"])
            floor = select_text(card, self.source.selectors["floor"])
            shop_number = select_text(card, self.source.selectors["shop_number"])
            if self.source.offer_type == "store":
                floor, shop_number = split_store_location(floor, shop_number)

            if self.source.offer_type == "store" and not all(
                is_usable_store_field(value)
                for value in (
                    store_name or self.source.brand_name,
                    floor,
                    shop_number,
                    select_text(card, self.source.selectors["phone"]),
                )
            ):
                logging.warning("略過缺少完整商店欄位的優惠：%s", title)
                continue

            offer = Offer(
                title=normalise_text(title),
                category=self.source.category,
                offer_type=self.source.offer_type,
                is_daily_special=is_daily_special,
                is_evergreen=is_evergreen,
                created_date=today.isoformat(),
                created_at=captured_at.isoformat(timespec="seconds"),
                start_date=start_date,
                discount_info=normalise_text(discount_info),
                details=self.source.details or normalise_text(discount_info),
                promo_code=normalise_promo_code(raw_code) or extract_promo_code(card_text),
                expiry_date=expiry_date,
                source_url=source_url,
                image_url=image_url,
                district=resolve_district(card, card_text, self.source),
                mall_name=mall_name_from_config(self.source.mall),
                brand_name=self.source.brand_name,
                store_name=(store_name or self.source.brand_name) if self.source.offer_type == "store" else None,
                floor=floor,
                shop_number=shop_number,
                phone=select_text(card, self.source.selectors["phone"]),
                source_name=self.source.name,
            )
            valid, reason = validate_offer(offer)
            if valid:
                offers.append(offer)
            else:
                logging.warning("略過不合規優惠「%s」：%s", offer.title, reason)
        return deduplicate_offers(offers)

    def _parse_mall(self, soup: BeautifulSoup) -> list[Mall]:
        if self.source.target != "malls" or not self.source.mall:
            return []
        profile = self.source.mall
        mall = Mall(
            mall_name=normalise_text(str(profile.get("mall_name", ""))),
            district=normalise_district(str(profile.get("district", self.source.district or ""))),
            address=normalise_text(str(profile.get("address", ""))),
            phone=optional_text(profile.get("phone")),
            network_phone=optional_text(profile.get("network_phone")),
            mall_url=str(profile.get("mall_url", self.source.url)),
        )
        if not mall.mall_name or not mall.district or not mall.address or not is_http_url(mall.mall_url):
            logging.warning("略過不完整的商場檔案：%s", self.source.identifier)
            return []
        return [mall]


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_store_location(floor: str | None, shop_number: str | None) -> tuple[str | None, str | None]:
    """Split a combined official mall location such as 「聚寶坊(第十一期)B64號舖」."""
    if not floor or shop_number != floor:
        return floor, shop_number
    match = re.search(r"(?P<shop>(?:地庫)?[A-Z]?\d[\dA-Z&-]*)號[舖铺]", floor, re.IGNORECASE)
    if not match:
        return floor, shop_number
    parsed_floor = normalise_text(floor[:match.start()])
    return parsed_floor or None, match.group("shop").upper()


def optional_text(value: Any) -> str | None:
    return normalise_text(str(value)) if value else None


def optional_iso_date(value: Any, source_id: str) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as error:
        raise ScraperError(f"{source_id} 的日期覆寫欄位必須為 YYYY-MM-DD") from error


def select_text(card: Tag, selector: str) -> str | None:
    element = card.select_one(selector)
    return normalise_text(element.get_text(" ", strip=True)) if element else None


def normalise_promo_code(value: str | None) -> str | None:
    if not value:
        return None
    candidate = normalise_text(value).upper()
    return candidate if PROMO_CODE_PATTERN.fullmatch(candidate) else None


def extract_promo_code(text: str) -> str | None:
    match = PROMO_CODE_IN_TEXT.search(text)
    return match.group(1).upper() if match else None


def parse_expiry_date(value: str, today: date) -> str | None:
    """Return only YYYY-MM-DD, as required by the updated lifecycle specification."""
    iso_match = ISO_DATE_PATTERN.search(value)
    if iso_match:
        return safe_iso_date(*(int(part) for part in iso_match.groups()))

    chinese_match = CHINESE_DATE_PATTERN.search(value)
    if chinese_match:
        year_text, month_text, day_text = chinese_match.groups()
        year = int(year_text) if year_text else today.year
        parsed = safe_iso_date(year, int(month_text), int(day_text))
        # A month/day with no year is conventionally the next occurrence if it already passed.
        if parsed and not year_text and date.fromisoformat(parsed) < today:
            parsed = safe_iso_date(year + 1, int(month_text), int(day_text))
        return parsed
    return None


def parse_date_range(value: str, today: date) -> tuple[str | None, str | None]:
    """Parse first/last dates in a listing card across ISO, Chinese, and English formats."""
    candidates: list[tuple[int | None, int, int]] = []
    range_match = YEAR_MONTH_DAY_RANGE_PATTERN.search(value)
    if range_match:
        year, start_month, start_day, end_month, end_day = (int(part) for part in range_match.groups())
        candidates.extend(((year, start_month, start_day), (year, end_month, end_day)))
    for match in ISO_DATE_PATTERN.finditer(value):
        candidate = tuple(int(part) for part in match.groups())
        if safe_iso_date(*candidate) and candidate not in candidates:
            candidates.append(candidate)
    for match in DAY_MONTH_YEAR_DATE_PATTERN.finditer(value):
        day, month, year = (int(part) for part in match.groups())
        candidate = (year, month, day)
        if safe_iso_date(*candidate) and candidate not in candidates:
            candidates.append(candidate)

    if not candidates:
        last_year = today.year
        for match in CHINESE_DATE_PATTERN.finditer(value):
            year_text, month_text, day_text = match.groups()
            if year_text:
                last_year = int(year_text)
            parsed = safe_iso_date(last_year, int(month_text), int(day_text))
            if parsed:
                candidates.append((last_year, int(month_text), int(day_text)))

    if not candidates:
        for match in ENGLISH_DAY_MONTH_PATTERN.finditer(value):
            day_text, month_text, year_text = match.groups()
            candidates.append((
                int(year_text) if year_text else None,
                MONTH_NUMBERS[month_text[:3].lower()],
                int(day_text),
            ))
        for match in ENGLISH_MONTH_DAY_PATTERN.finditer(value):
            month_text, day_text, year_text = match.groups()
            candidates.append((
                int(year_text) if year_text else None,
                MONTH_NUMBERS[month_text[:3].lower()],
                int(day_text),
            ))

    if not candidates:
        return None, None

    known_year = next((year for year, _, _ in reversed(candidates) if year is not None), today.year)
    dates = [
        safe_iso_date(year or known_year, month, day)
        for year, month, day in candidates
    ]
    parsed_dates = [value for value in dates if value]
    if not parsed_dates:
        return None, None
    if re.search(r"即日起|from\s+now", value, re.IGNORECASE):
        return today.isoformat(), parsed_dates[-1]
    start = parsed_dates[0]
    end = parsed_dates[-1]
    return start, end


def is_evergreen_mall_policy(title: str, discount_info: str, card_text: str) -> bool:
    """Identify undated, mall-wide policies that are normally continuous."""
    return bool(EVERGREEN_MALL_POLICY_PATTERN.search(" ".join((title, discount_info, card_text))))


def safe_iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalise_district(value: str) -> str | None:
    for district in HK_DISTRICTS:
        if district in value:
            return district
    return None


def resolve_district(card: Tag, card_text: str, source: SourceConfig) -> str | None:
    if source.district:
        return normalise_district(source.district)
    selected = select_text(card, source.selectors["district"])
    return normalise_district(selected or card_text)


def mall_name_from_config(mall: dict[str, Any] | None) -> str | None:
    return normalise_text(str(mall["mall_name"])) if mall and mall.get("mall_name") else None


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_usable_store_field(value: str | None) -> bool:
    """Reject empty, placeholder, or fabricated store contact fields."""
    from store_authenticity import is_placeholder_text

    text = normalise_text(value or "")
    if is_placeholder_text(text):
        return False
    if PLACEHOLDER_STORE_FIELD_PATTERN.fullmatch(text):
        return False
    return True


def validate_offer(offer: Offer) -> tuple[bool, str]:
    from store_authenticity import (
        authenticity_failures,
        lifecycle_failures,
        offer_to_auth_payload,
    )

    if offer.category not in CATEGORIES:
        return False, "category 不在允許的四個分類內"
    if not offer.title or not offer.discount_info:
        return False, "缺少 title 或 discount_info"
    if offer.offer_type not in {"mall", "store"}:
        return False, "offer_type 必須是 mall 或 store"
    if offer.offer_type == "store":
        failures = authenticity_failures(offer_to_auth_payload(offer))
        if failures:
            return False, f"store 優惠未通過真實性六欄驗證：{', '.join(failures)}"
    if not is_http_url(offer.source_url):
        return False, "source_url 不是有效 HTTP(S) URL"
    if offer.promo_code and not PROMO_CODE_PATTERN.fullmatch(offer.promo_code):
        return False, "promo_code 格式不合法"
    try:
        date.fromisoformat(offer.created_date)
        start_date = date.fromisoformat(offer.start_date)
        expiry_date = date.fromisoformat(offer.expiry_date)
        datetime.fromisoformat(offer.created_at)
    except ValueError:
        return False, "created_date、created_at、start_date 或 expiry_date 格式不合法"
    if start_date > expiry_date:
        return False, "開始日期不得晚於結束日期"
    life = lifecycle_failures(
        {"start_date": offer.start_date, "expiry_date": offer.expiry_date}
    )
    if life:
        return False, f"優惠未通過時效生命週期過濾：{', '.join(life)}"
    return True, ""


def deduplicate_offers(offers: list[Offer]) -> list[Offer]:
    unique: dict[tuple[str, str, str, str | None, str | None, str | None], Offer] = {}
    for offer in offers:
        key = (
            offer.title.casefold(),
            offer.category,
            offer.expiry_date,
            offer.district,
            offer.mall_name,
            offer.store_name,
        )
        unique.setdefault(key, offer)
    return list(unique.values())


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError) as error:
        logging.warning("忽略無法讀取的 %s：%s", path, error)
        return {}


def offer_from_json(raw: Any) -> Offer | None:
    if not isinstance(raw, dict):
        return None
    try:
        offer = Offer(
            title=str(raw["title"]),
            category=str(raw["category"]),
            offer_type=str(raw.get("offer_type", "mall")),
            is_daily_special=bool(raw["is_daily_special"]),
            is_evergreen=bool(raw.get("is_evergreen", False)),
            created_date=str(raw["created_date"]),
            created_at=str(raw.get("created_at", f"{raw['created_date']}T00:00:00+00:00")),
            start_date=str(raw.get("start_date", raw["created_date"])),
            discount_info=str(raw["discount_info"]),
            details=raw.get("details", raw.get("discount_info")),
            promo_code=raw.get("promo_code"),
            expiry_date=str(raw["expiry_date"]),
            source_url=str(raw["source_url"]),
            image_url=raw.get("image_url"),
            district=raw.get("district"),
            mall_name=raw.get("mall_name"),
            brand_name=raw.get("brand_name"),
            store_name=raw.get("store_name"),
            floor=raw.get("floor"),
            shop_number=raw.get("shop_number"),
            phone=raw.get("phone"),
            source_name=raw.get("source_name"),
        )
    except KeyError:
        return None
    return offer if validate_offer(offer)[0] else None


def mall_from_json(raw: Any) -> Mall | None:
    if not isinstance(raw, dict):
        return None
    try:
        mall = Mall(**{field: raw.get(field) for field in Mall.__dataclass_fields__})
    except TypeError:
        return None
    return mall if mall.mall_name and mall.district and mall.address and (
        mall.mall_url is None or is_http_url(mall.mall_url)
    ) else None


def clean_offers(offers: list[Offer], reference_time: datetime) -> list[Offer]:
    """Keep only in-progress offers and previews starting within three days.

    Applies to *all* offers (including evergreen). Expired rows are always dropped.
    Daily specials additionally expire one day after created_at.
    """
    from store_authenticity import is_within_lifecycle_window

    today = reference_time.date()
    retained: list[Offer] = []
    dropped_expired = dropped_preview = dropped_daily = dropped_bad_date = 0
    for offer in offers:
        try:
            created_at = datetime.fromisoformat(offer.created_at)
            start = date.fromisoformat(offer.start_date)
            expiry = date.fromisoformat(offer.expiry_date)
        except ValueError:
            logging.warning("刪除日期不合法的資料：%s", offer.title)
            dropped_bad_date += 1
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if offer.is_daily_special and reference_time > created_at + timedelta(days=1):
            logging.info("清除超過 1 天的每日優惠：%s", offer.title)
            dropped_daily += 1
            continue
        if not is_within_lifecycle_window(start.isoformat(), expiry.isoformat(), today=today):
            if expiry < today:
                logging.info("清除已過期優惠：%s", offer.title)
                dropped_expired += 1
            else:
                logging.info("清除超過 3 天才開始的優惠：%s", offer.title)
                dropped_preview += 1
            continue
        retained.append(offer)
    logging.info(
        "lifecycle clean kept=%s dropped_expired=%s dropped_beyond_preview=%s "
        "dropped_daily=%s dropped_bad_date=%s",
        len(retained),
        dropped_expired,
        dropped_preview,
        dropped_daily,
        dropped_bad_date,
    )
    return retained


def merge_offers(existing: list[Offer], fresh: list[Offer], reference_time: datetime) -> list[Offer]:
    # Several official merchant pages publish many offers under one listing URL.
    # Keep each distinct title / mall / store instead of allowing the final card
    # to overwrite all others that share a source URL.
    def identity(offer: Offer) -> tuple[str, str, str | None, str | None]:
        return (
            offer.source_url,
            offer.title.casefold(),
            offer.mall_name,
            offer.store_name,
        )

    merged = {identity(offer): offer for offer in existing}
    merged.update({identity(offer): offer for offer in fresh})
    return clean_offers(list(merged.values()), reference_time)


def merge_malls(existing: list[Mall], fresh: list[Mall]) -> list[Mall]:
    merged = {(mall.mall_name, mall.district): mall for mall in existing}
    merged.update({(mall.mall_name, mall.district): mall for mall in fresh})
    return sorted(merged.values(), key=lambda mall: (mall.district, mall.mall_name))


def load_mall_overrides(path: Path, known_malls: set[tuple[str, str]], reference_time: datetime) -> list[Offer]:
    """Load manually verified evergreen mall policies as a resilient source fallback."""
    overrides = load_json(path).get("overrides", [])
    if not isinstance(overrides, list):
        logging.warning("忽略不正確的常青優惠對照表：%s", path)
        return []

    today = reference_time.date().isoformat()
    offers: list[Offer] = []
    for raw in overrides:
        if not isinstance(raw, dict):
            continue
        mall_name = normalise_text(str(raw.get("mall_name", "")))
        district = normalise_district(str(raw.get("district", "")))
        if not mall_name or not district or (district, mall_name) not in known_malls:
            logging.warning("略過未在商場名冊配對的常青優惠：%s", mall_name or "未知商場")
            continue
        if raw.get("is_evergreen") is not True:
            logging.warning("略過未標記 is_evergreen 的常青優惠：%s", mall_name)
            continue
        offer_type = str(raw.get("offer_type", "mall"))
        if offer_type not in {"mall", "store"}:
            logging.warning("略過不支援 offer_type 的常青優惠：%s", mall_name)
            continue
        offer = Offer(
            title=normalise_text(str(raw.get("title", ""))),
            category="商場優惠",
            offer_type=offer_type,
            is_daily_special=False,
            is_evergreen=True,
            created_date=today,
            created_at=reference_time.isoformat(timespec="seconds"),
            start_date=today,
            discount_info=normalise_text(str(raw.get("details", ""))),
            details=optional_text(raw.get("details")),
            promo_code=None,
            expiry_date=today,
            source_url=str(raw.get("source_url", "")),
            image_url=None,
            district=district,
            mall_name=mall_name,
            brand_name=optional_text(raw.get("brand_name")) or mall_name,
            store_name=optional_text(raw.get("store_name")) if offer_type == "store" else None,
            floor=optional_text(raw.get("floor")) if offer_type == "store" else None,
            shop_number=optional_text(raw.get("shop_number")) if offer_type == "store" else None,
            phone=optional_text(raw.get("phone")) if offer_type == "store" else None,
            source_name="mall_overrides",
        )
        valid, reason = validate_offer(offer)
        if valid:
            offers.append(offer)
        else:
            logging.warning("略過不合規的常青優惠覆寫「%s」：%s", mall_name, reason)
    return deduplicate_offers(offers)


def load_chain_store_offers(
    path: Path, known_malls: set[tuple[str, str]], reference_time: datetime
) -> list[Offer]:
    """Expand only *verified* chain loyalty pins onto host malls."""
    from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified

    payload = load_json(path)
    chains_raw = payload.get("chains", [])
    presence_raw = payload.get("presence", [])
    if not isinstance(chains_raw, list) or not isinstance(presence_raw, list):
        logging.warning("忽略不正確的連鎖商店對照表：%s", path)
        return []

    chains: dict[str, dict[str, Any]] = {}
    for raw in chains_raw:
        if not isinstance(raw, dict):
            continue
        chain_id = str(raw.get("chain_id", "")).strip()
        if not chain_id or raw.get("is_evergreen") is not True:
            continue
        chains[chain_id] = raw

    today = reference_time.date().isoformat()
    offers: list[Offer] = []
    skipped_pending = 0
    for raw in presence_raw:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("verification_status", "")).strip() != VERIFICATION_VERIFIED:
            skipped_pending += 1
            continue
        if not presence_is_verified(raw):
            logging.warning(
                "略過標示 verified 但六欄不完整的連鎖對應：%s@%s",
                raw.get("chain_id"),
                raw.get("mall_name"),
            )
            continue
        chain = chains.get(str(raw.get("chain_id", "")).strip())
        if not chain:
            continue
        mall_name = normalise_text(str(raw.get("mall_name", "")))
        district = normalise_district(str(raw.get("district", "")))
        if not mall_name or not district or (district, mall_name) not in known_malls:
            logging.warning("略過未在商場名冊配對的連鎖商店：%s", mall_name or "未知商場")
            continue
        shop_number = normalise_text(str(raw.get("shop_number") or ""))
        explicit_store = normalise_text(str(raw.get("store_name") or ""))
        chain_store = normalise_text(str(chain.get("store_name") or ""))
        if explicit_store:
            store_name = explicit_store
        elif shop_number and not re.fullmatch(r"[A-Za-z]{0,2}\d+[A-Za-z0-9\-]*", shop_number):
            store_name = shop_number
        else:
            store_name = chain_store
        details_text = normalise_text(str(chain.get("details", "")))
        if not SUBSTANTIVE_STORE_DETAIL.search(details_text):
            logging.warning(
                "略過內容空泛的連鎖商店優惠「%s」：details 需含積分／折扣／回贈等具體說明",
                store_name or chain.get("chain_id"),
            )
            continue
        floor = normalise_text(str(raw.get("floor") or ""))
        phone = normalise_text(str(raw.get("phone") or ""))
        offer = Offer(
            title=normalise_text(str(chain.get("title", ""))),
            category="商場優惠",
            offer_type="store",
            is_daily_special=False,
            is_evergreen=True,
            created_date=today,
            created_at=reference_time.isoformat(timespec="seconds"),
            start_date=today,
            discount_info=details_text,
            details=details_text or None,
            promo_code=None,
            expiry_date=today,
            source_url=str(chain.get("source_url", "")),
            image_url=None,
            district=district,
            mall_name=mall_name,
            brand_name=store_name,
            store_name=store_name,
            floor=floor,
            shop_number=shop_number,
            phone=phone,
            source_name="chain_store_offers",
        )
        valid, reason = validate_offer(offer)
        if valid:
            offers.append(offer)
        else:
            logging.warning("略過不合規的連鎖商店優惠「%s@%s」：%s", store_name, mall_name, reason)
    if skipped_pending:
        logging.info("連鎖對應待核實／未驗證列已略過：%s 筆", skipped_pending)
    return deduplicate_offers(offers)


def classify_offer_category(offer_type: str, is_evergreen: bool) -> tuple[str, str]:
    """Return machine + Traditional Chinese labels for frontend filtering."""
    if offer_type == "store":
        return "store_offer", "個別商店優惠"
    if is_evergreen:
        return "evergreen_benefit", "長青福利"
    return "official_event", "官方活動"


def enrich_offer_payload(raw: dict[str, Any]) -> dict[str, Any]:
    category_id, category_label = classify_offer_category(
        str(raw.get("offer_type", "mall")),
        bool(raw.get("is_evergreen")),
    )
    raw["offer_category"] = category_id
    raw["offer_category_label"] = category_label
    try:
        scripts_dir = Path(__file__).resolve().parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from offer_tagging import apply_offer_tags

        apply_offer_tags(raw)
    except Exception:  # noqa: BLE001
        # Tagging is additive; never block scrapes if the helper is unavailable.
        raw.setdefault("vertical_category", "Other")
        raw.setdefault("vertical_category_label", "其他")
        raw.setdefault("tags", [])
    return raw


def write_outputs(discounts_path: Path, malls_path: Path, offers: list[Offer], malls: list[Mall]) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    serialised = [enrich_offer_payload(asdict(offer)) for offer in offers]
    by_category: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for category in sorted(CATEGORIES):
        category_offers = [offer for offer in serialised if offer["category"] == category]
        districts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for offer in category_offers:
            if offer["district"]:
                districts[offer["district"]].append(offer)
        by_category[category] = {"offers": category_offers, "by_district": dict(districts)}

    discounts_path.write_text(
        json.dumps(
            {"scrape_time": timestamp, "offers": serialised, "by_category": by_category},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    malls_by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mall in malls:
        malls_by_district[mall.district].append(asdict(mall))
    malls_path.write_text(
        json.dumps(
            {"scrape_time": timestamp, "malls": [asdict(mall) for mall in malls], "by_district": dict(malls_by_district)},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def load_sources(config_path: Path) -> list[SourceConfig]:
    raw = load_json(config_path)
    sources = raw.get("sources")
    if not isinstance(sources, list):
        raise ScraperError("設定檔必須包含 sources 陣列。可先使用 --write-example-config 建立範本。")
    return [SourceConfig.from_dict(source) for source in sources if isinstance(source, dict)]


def example_config() -> dict[str, Any]:
    return {
        "_comment": "填入已確認允許抓取的網址與實際 CSS selectors；未知網址不應直接加入。",
        "sources": [
            {
                "id": "skyscanner-hk",
                "enabled": False,
                "target": "flights",
                "name": "Skyscanner 香港",
                "url": "https://www.skyscanner.com.hk/",
                "category": "機票",
                "is_daily_special": True,
                "selectors": {"card": ".replace-with-actual-card-selector", "title": "h2", "discount_info": ".description"},
            },
            {
                "id": "hk-disney",
                "enabled": False,
                "target": "theme-parks",
                "name": "香港迪士尼樂園",
                "url": "https://www.hongkongdisneyland.com/zh-hk/",
                "category": "主題樂園",
                "district": "離島區",
                "is_daily_special": False,
                "selectors": {"card": ".replace-with-actual-card-selector", "title": "h2", "discount_info": ".description"},
            },
            {
                "id": "ocean-park",
                "enabled": False,
                "target": "theme-parks",
                "name": "香港海洋公園",
                "url": "https://www.oceanpark.com.hk/",
                "category": "主題樂園",
                "district": "南區",
                "is_daily_special": False,
                "selectors": {"card": ".replace-with-actual-card-selector", "title": "h2", "discount_info": ".description"},
            },
            {
                "id": "authorised-mall",
                "enabled": False,
                "target": "malls",
                "name": "已授權商場",
                "url": "https://mall.example.com/promotions",
                "category": "商場優惠",
                "district": "沙田區",
                "is_daily_special": False,
                "mall": {
                    "mall_name": "商場名稱",
                    "district": "沙田區",
                    "address": "商場地址",
                    "phone": "聯絡電話",
                    "network_phone": None,
                    "mall_url": "https://mall.example.com/",
                },
                "selectors": {"card": ".replace-with-actual-card-selector", "title": ".title", "discount_info": ".offer"},
            },
            {
                "id": "authorised-buffet",
                "enabled": False,
                "target": "buffets",
                "name": "已授權自助餐平台",
                "url": "https://buffet.example.com/promotions",
                "category": "自助餐",
                "is_daily_special": False,
                "selectors": {
                    "card": ".replace-with-actual-card-selector",
                    "title": ".title",
                    "discount_info": ".offer",
                    "district": ".restaurant-district",
                },
            },
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HK-Deal 動態多來源優惠爬蟲")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("data/sources.json"),
        help="來源設定檔（預設：data/sources.json）",
    )
    parser.add_argument("--targets", default="all", help="逗號分隔：malls,flights,buffets,theme-parks；預設 all")
    parser.add_argument("--discounts-output", type=Path, default=Path("discounts.json"))
    parser.add_argument("--mall-overrides", type=Path, default=Path("data/mall_overrides.json"))
    parser.add_argument(
        "--chain-store-offers",
        type=Path,
        default=Path("data/chain_store_offers.json"),
        help="連鎖商店常態優惠對照表",
    )
    parser.add_argument(
        "--malls-output",
        type=Path,
        default=Path("data/malls-registry.json"),
        help="平面商場檔案輸出；請勿指向 SPA 使用的 malls.json",
    )
    parser.add_argument("--write-example-config", action="store_true", help="寫入 sources.example.json 後結束")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.write_example_config:
        output = Path("sources.example.json")
        output.write_text(json.dumps(example_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logging.info("已建立 %s", output)
        return 0

    try:
        requested_targets = TARGET_GROUPS if args.targets == "all" else frozenset(args.targets.split(","))
        invalid = requested_targets - TARGET_GROUPS
        if invalid:
            raise ScraperError(f"未知 target：{', '.join(sorted(invalid))}")
        sources = [
            source
            for source in load_sources(args.config)
            if source.enabled and source.target in requested_targets
        ]
        if not sources:
            logging.warning("沒有已啟用且符合 target 的來源設定；只執行既有 JSON 資料清理。")

        existing_offers = [offer for raw in load_json(args.discounts_output).get("offers", []) if (offer := offer_from_json(raw))]
        existing_malls = [mall for raw in load_json(args.malls_output).get("malls", []) if (mall := mall_from_json(raw))]
        fresh_offers: list[Offer] = []
        fresh_malls: list[Mall] = []
        if sources:
            client = HttpClient()
            for source in sources:
                try:
                    offers, malls = DynamicSourceScraper(client, source).scrape()
                    fresh_offers.extend(offers)
                    fresh_malls.extend(malls)
                    logging.info("%s：取得 %s 筆優惠、%s 筆商場資料", source.name, len(offers), len(malls))
                except ScraperError as error:
                    logging.error("%s 抓取失敗：%s", source.name, error)

        reference_time = datetime.now(timezone.utc).astimezone()
        known_malls = {(mall.district, mall.mall_name) for mall in existing_malls + fresh_malls}
        override_offers = load_mall_overrides(args.mall_overrides, known_malls, reference_time)
        chain_offers = load_chain_store_offers(args.chain_store_offers, known_malls, reference_time)
        covered_policy_sources = {
            (offer.district, offer.mall_name, offer.source_url)
            for offer in existing_offers + fresh_offers
            if offer.offer_type == "mall" and offer.is_evergreen
        }
        override_offers = [
            offer for offer in override_offers
            if (offer.district, offer.mall_name, offer.source_url) not in covered_policy_sources
        ]
        offers = merge_offers(
            existing_offers, fresh_offers + override_offers + chain_offers, reference_time
        )
        malls = merge_malls(existing_malls, fresh_malls)
        write_outputs(args.discounts_output, args.malls_output, offers, malls)
        logging.info("完成：%s 筆優惠寫入 %s；%s 筆商場寫入 %s", len(offers), args.discounts_output, len(malls), args.malls_output)
        return 0
    except ScraperError as error:
        logging.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
