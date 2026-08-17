"""Extreme-authenticity rules for individual store offers.

A store offer may reach the frontend only when all six fields are present and
non-placeholder:

1. store_name
2. floor
3. shop_number
4. phone
5. offer content (title / discount_info / details)
6. validity dates (start_date + expiry_date)

Lifecycle window (applies to every retained offer, including evergreen):
- drop when expiry_date < today
- drop when start_date > today + LIFECYCLE_PREVIEW_DAYS
- keep when currently in progress, or starting within the preview window
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

PLACEHOLDER_TEXTS = frozenset(
    {
        "請向分店查詢",
        "請向商場查詢",
        "商場指定層",
        "商場內分店",
        "駐場分店",
        "全場參與商戶",
        "待核實",
        "待確認",
        "n/a",
        "na",
        "null",
        "none",
        "unknown",
        "xxx",
        "test",
        "placeholder",
        "待定",
    }
)

VAGUE_LOCATION_TEXTS = frozenset(
    {
        "個人護理區",
        "AEON STYLE 樓層",
        "一田樓層",
        "DONKI 專門店樓層",
        "餐飲樓層",
        "食肆區",
        "商場內",
        "Xsite",
    }
)

PHONE_PATTERN = re.compile(r"(?:\+?852[-\s]?)?(?:\d{4}[\s-]?\d{4}|\d{8})")
SHOP_UNIT_PATTERN = re.compile(r"\d")
VERIFICATION_VERIFIED = "verified"
VERIFICATION_PENDING = "pending"
LIFECYCLE_PREVIEW_DAYS = 3


def _norm(value: Any) -> str:
    return str(value or "").strip()


def is_placeholder_text(value: Any) -> bool:
    text = _norm(value)
    if not text:
        return True
    lowered = text.casefold()
    if text in PLACEHOLDER_TEXTS or lowered in PLACEHOLDER_TEXTS:
        return True
    if text.startswith("replace-with") or "placeholder" in lowered:
        return True
    return False


def is_precise_floor(value: Any) -> bool:
    text = _norm(value)
    if is_placeholder_text(text) or text in VAGUE_LOCATION_TEXTS:
        return False
    return True


def is_precise_shop_number(value: Any) -> bool:
    text = _norm(value)
    if is_placeholder_text(text) or text in VAGUE_LOCATION_TEXTS:
        return False
    return bool(SHOP_UNIT_PATTERN.search(text))


def is_precise_phone(value: Any) -> bool:
    text = _norm(value)
    if is_placeholder_text(text):
        return False
    return bool(PHONE_PATTERN.search(text))


def is_precise_content(value: Any) -> bool:
    text = _norm(value)
    return bool(text) and not is_placeholder_text(text)


def has_validity_dates(start_date: Any, expiry_date: Any) -> bool:
    start = _norm(start_date)
    end = _norm(expiry_date)
    if not start or not end:
        return False
    if is_placeholder_text(start) or is_placeholder_text(end):
        return False
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end)
    )


def parse_offer_date(value: Any) -> date | None:
    text = _norm(value)
    if not text or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def is_within_lifecycle_window(
    start_date: Any,
    expiry_date: Any,
    *,
    today: date | None = None,
    preview_days: int = LIFECYCLE_PREVIEW_DAYS,
) -> bool:
    """True only for in-progress offers or those starting within preview_days."""
    today = today or date.today()
    start = parse_offer_date(start_date)
    end = parse_offer_date(expiry_date)
    if start is None or end is None:
        return False
    if end < start:
        return False
    if end < today:
        return False
    if start > today + timedelta(days=preview_days):
        return False
    return True


def lifecycle_failures(payload: dict[str, Any], *, today: date | None = None) -> list[str]:
    """Return lifecycle violation codes for an offer payload."""
    today = today or date.today()
    start_raw = payload.get("start_date")
    end_raw = payload.get("expiry_date") or payload.get("end_date")
    if not has_validity_dates(start_raw, end_raw):
        return ["validity_dates"]
    start = parse_offer_date(start_raw)
    end = parse_offer_date(end_raw)
    assert start is not None and end is not None
    if end < start:
        return ["invalid_date_order"]
    if end < today:
        return ["expired"]
    if start > today + timedelta(days=LIFECYCLE_PREVIEW_DAYS):
        return ["starts_beyond_preview"]
    return []


def authenticity_failures(payload: dict[str, Any], *, today: date | None = None) -> list[str]:
    failures: list[str] = []
    store_name = _norm(payload.get("store_name"))
    floor = _norm(payload.get("floor"))
    shop_number = _norm(payload.get("shop_number"))
    phone = _norm(payload.get("phone"))
    content = _norm(payload.get("details") or payload.get("discount_info") or payload.get("title"))
    start_date = payload.get("start_date")
    expiry_date = payload.get("expiry_date") or payload.get("end_date")

    if is_placeholder_text(store_name):
        failures.append("store_name")
    if not is_precise_floor(floor):
        failures.append("floor")
    if not is_precise_shop_number(shop_number):
        failures.append("shop_number")
    if not is_precise_phone(phone):
        failures.append("phone")
    if not is_precise_content(content):
        failures.append("offer_content")
    if not has_validity_dates(start_date, expiry_date):
        failures.append("validity_dates")
    else:
        failures.extend(lifecycle_failures(payload, today=today))
    return failures


def six_column_failures(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    require_status: bool = True,
) -> list[str]:
    """Strict 6-column gate for store offers / SPA store cards.

    Columns:
      1. store_name          — 商戶名稱
      2. category_tags       — 分類標籤 (offer_category / vertical_category / tags)
      3. validity_dates      — 起訖日期 (start_date + end/expiry)
      4. status              — 生命週期狀態 (active|upcoming) when require_status
      5. store_location      — 門市樓層＋鋪號
      6. source_channel      — 來源渠道 (source_url and/or source_name)
    """
    today = today or date.today()
    failures: list[str] = []

    # 1. Store name
    if is_placeholder_text(payload.get("store_name")):
        failures.append("col1_store_name")

    # 2. Category / tags
    has_category = bool(
        _norm(payload.get("offer_category"))
        or _norm(payload.get("vertical_category"))
        or _norm(payload.get("offer_category_label"))
        or (isinstance(payload.get("tags"), list) and payload.get("tags"))
        or _norm(payload.get("category"))
    )
    if not has_category:
        failures.append("col2_category_tags")

    # 3. Start / end dates (+ no expired residue)
    start_raw = payload.get("start_date")
    end_raw = payload.get("expiry_date") or payload.get("end_date")
    if not has_validity_dates(start_raw, end_raw):
        failures.append("col3_validity_dates")
    else:
        start = parse_offer_date(start_raw)
        end = parse_offer_date(end_raw)
        if start is None or end is None or end < start:
            failures.append("col3_validity_dates")
        elif today > end:
            failures.append("col3_expired_residue")
        elif start > today + timedelta(days=LIFECYCLE_PREVIEW_DAYS):
            failures.append("col3_beyond_preview")

    # 4. Lifecycle status
    if require_status:
        status = _norm(payload.get("status") or payload.get("lifecycle_status")).casefold()
        if status not in {"active", "upcoming"}:
            failures.append("col4_status")

    # 5. Floor + shop number
    if not is_precise_floor(payload.get("floor")) or not is_precise_shop_number(
        payload.get("shop_number")
    ):
        failures.append("col5_store_location")

    # 6. Source channel
    source_url = _norm(payload.get("source_url"))
    source_name = _norm(payload.get("source_name"))
    if not source_url and not source_name:
        failures.append("col6_source_channel")
    elif source_url and is_placeholder_text(source_url):
        failures.append("col6_source_channel")

    # Placeholders in any core text field hard-fail.
    for field in (
        "store_name",
        "floor",
        "shop_number",
        "phone",
        "details",
        "discount_info",
        "offer_title",
        "title",
    ):
        value = _norm(payload.get(field))
        if value and value in PLACEHOLDER_TEXTS:
            failures.append(f"placeholder:{field}")

    return failures


def is_authentic_store_payload(payload: dict[str, Any], *, today: date | None = None) -> bool:
    return not authenticity_failures(payload, today=today)


def presence_is_verified(row: dict[str, Any]) -> bool:
    if _norm(row.get("verification_status")) != VERIFICATION_VERIFIED:
        return False
    return (
        not is_placeholder_text(row.get("store_name") or row.get("shop_number"))
        and is_precise_floor(row.get("floor"))
        and is_precise_shop_number(row.get("shop_number"))
        and is_precise_phone(row.get("phone"))
    )


def offer_to_auth_payload(offer: Any) -> dict[str, Any]:
    """Adapt Offer dataclass or dict into authenticity payload."""
    if isinstance(offer, dict):
        return offer
    return {
        "store_name": getattr(offer, "store_name", None),
        "floor": getattr(offer, "floor", None),
        "shop_number": getattr(offer, "shop_number", None),
        "phone": getattr(offer, "phone", None),
        "details": getattr(offer, "details", None),
        "discount_info": getattr(offer, "discount_info", None),
        "title": getattr(offer, "title", None),
        "start_date": getattr(offer, "start_date", None),
        "expiry_date": getattr(offer, "expiry_date", None),
    }
