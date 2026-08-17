# -*- coding: utf-8 -*-
"""Infer vertical category + promo tags for mall/store offers.

Categories (vertical):
  Dining | Retail | Entertainment | Services | Other

Tags (multi-label promo facets), e.g.:
  CreditCard | AfternoonTea | Parking | Member | Takeaway | Birthday
  FreeGift | Discount | Points | AppOnly | Evergreen | Upcoming

Also provides lifecycle status helpers for the 3-day upcoming window
[today, today + LIFECYCLE_PREVIEW_DAYS].
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from store_authenticity import LIFECYCLE_PREVIEW_DAYS, parse_offer_date

VERTICAL_DINING = "Dining"
VERTICAL_RETAIL = "Retail"
VERTICAL_ENTERTAINMENT = "Entertainment"
VERTICAL_SERVICES = "Services"
VERTICAL_OTHER = "Other"

STATUS_ACTIVE = "active"
STATUS_UPCOMING = "upcoming"
STATUS_EXPIRED = "expired"
STATUS_SCHEDULED = "scheduled"
STATUS_FALLBACK = "fallback"

VERTICAL_LABELS = {
    VERTICAL_DINING: "餐飲",
    VERTICAL_RETAIL: "零售",
    VERTICAL_ENTERTAINMENT: "娛樂",
    VERTICAL_SERVICES: "服務",
    VERTICAL_OTHER: "其他",
}

TAG_DEFS: list[tuple[str, re.Pattern[str]]] = [
    ("CreditCard", re.compile(r"信用卡|Visa|Mastercard|銀聯|AE\b|American\s*Express|簽帳|卡賞|卡戶", re.I)),
    ("AfternoonTea", re.compile(r"下午茶|high\s*tea|tea\s*set|Tea\s*Set", re.I)),
    ("Parking", re.compile(r"泊車|停車|parking|免費泊|優惠泊", re.I)),
    ("Member", re.compile(r"會員|Member|Club\s*100|Rewards|KLUB|yuu|MoneyBack|The\s*Point|S\+|hello\s*恒隆|passport|App\s*會員", re.I)),
    ("Takeaway", re.compile(r"外賣|自取|takeaway|take-?out|外送|delivery", re.I)),
    ("Birthday", re.compile(r"生日|birthday", re.I)),
    ("FreeGift", re.compile(r"贈品|換領|免費換|禮遇|禮品|贈送", re.I)),
    ("Discount", re.compile(r"折扣|減\$|優惠|\%\s*off|半價|特價|滿\$", re.I)),
    ("Points", re.compile(r"積分|賺分|獎賞分|Point|Miles|里數", re.I)),
    ("AppOnly", re.compile(r"App\s*專屬|手機點餐|App\s*限定|網上換領", re.I)),
    ("Evergreen", re.compile(r"常態|長青|evergreen|全年", re.I)),
    ("Cinema", re.compile(r"戲院|電影|cinema|AMC|UA\b|英皇戲院", re.I)),
    ("Beauty", re.compile(r"藥妝|護膚|美妝|美容|個人護理|屈臣氏|萬寧", re.I)),
    ("Supermarket", re.compile(r"超市|百佳|惠康|Market\s*Place|AEON|一田|city'?s?uper", re.I)),
    ("Upcoming", re.compile(r"即將開始|即將推出|新一期|週末限定|快閃|新菜單|3\s*天內", re.I)),
    ("PopUp", re.compile(r"快閃|Pop-?up|期間限定店|期間限定", re.I)),
    ("Weekend", re.compile(r"週末|周末|Saturday|Sunday|週六|週日", re.I)),
]

TAG_LABELS = {
    "CreditCard": "信用卡",
    "AfternoonTea": "下午茶",
    "Parking": "泊車",
    "Member": "會員",
    "Takeaway": "外賣",
    "Birthday": "生日",
    "FreeGift": "贈品換領",
    "Discount": "折扣",
    "Points": "積分",
    "AppOnly": "App 專屬",
    "Evergreen": "長青",
    "Cinema": "戲院",
    "Beauty": "美妝護理",
    "Supermarket": "超市",
    "Upcoming": "即將開始",
    "PopUp": "快閃",
    "Weekend": "週末",
}

DINING_RE = re.compile(
    r"餐飲|餐廳|咖啡|茶|拉麵|米線|壽司|快餐|外賣|下午茶|飲食|美食|"
    r"Starbucks|星巴克|麥當勞|大家樂|大快活|必勝客|譚仔|Pizza|Fairwood|"
    r"Cafe|Dining|Restaurant|Food\s*Court|美心|MX\b",
    re.I,
)
RETAIL_RE = re.compile(
    r"零售|購物|百貨|超市|藥妝|服飾|UNIQLO|無印|MUJI|豐澤|百老匯|"
    r"屈臣氏|萬寧|AEON|一田|莎莎|Sasa|Market\s*Place|Living\s*PLAZA|"
    r"Shop|Store|Retail|Fashion|超市",
    re.I,
)
ENTERTAINMENT_RE = re.compile(
    r"娛樂|戲院|電影|遊戲|Kiztopia|歡樂天地|遊樂|Entertainment|Cinema|AMC",
    re.I,
)
SERVICES_RE = re.compile(r"銀行|保險|服務|診所|美容|Salon|Banking|Service", re.I)

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_CN_FULL_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_CN_RANGE_RE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"\s*至\s*"
    r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
_EFFECTIVE_KEYS = (
    "start_date",
    "effective_from",
    "effectiveFrom",
    "startTime",
    "start_time",
    "promoStart",
    "promotionStart",
    "validFrom",
)


def _blob(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("store_name"),
        payload.get("brand_name"),
        payload.get("title"),
        payload.get("offer_title"),
        payload.get("details"),
        payload.get("discount_info"),
        payload.get("chain_id"),
    ]
    return " ".join(str(p) for p in parts if p)


def parse_flexible_date(value: Any) -> date | None:
    """Parse ISO, ISO datetime, or Chinese calendar dates into a date."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    hit = parse_offer_date(text[:10]) if len(text) >= 10 and text[4] == "-" else None
    if hit:
        return hit
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    m = _ISO_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _CN_FULL_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_date_range_from_text(text: str) -> tuple[date | None, date | None]:
    """Extract start/end from Chinese range copy like 2026年8月17日至10月31日."""
    m = _CN_RANGE_RE.search(text or "")
    if not m:
        single = parse_flexible_date(text)
        return single, None
    y1, mo1, d1, y2, mo2, d2 = m.groups()
    try:
        start = date(int(y1), int(mo1), int(d1))
        end = date(int(y2) if y2 else int(y1), int(mo2), int(d2))
        return start, end
    except ValueError:
        return None, None


def extract_start_date(payload: dict[str, Any]) -> date | None:
    """Prefer explicit start/effective fields, then free-text date ranges."""
    for key in _EFFECTIVE_KEYS:
        if key in payload and payload.get(key) not in (None, ""):
            hit = parse_flexible_date(payload.get(key))
            if hit:
                return hit
    blob = _blob(payload)
    start, _ = parse_date_range_from_text(blob)
    return start


def upcoming_window_end(
    today: date | None = None, *, preview_days: int = LIFECYCLE_PREVIEW_DAYS
) -> date:
    today = today or date.today()
    return today + timedelta(days=preview_days)


def is_upcoming_start(
    start: date | None,
    *,
    today: date | None = None,
    preview_days: int = LIFECYCLE_PREVIEW_DAYS,
) -> bool:
    """True when start is strictly after today and within the preview window."""
    today = today or date.today()
    if start is None:
        return False
    return today < start <= today + timedelta(days=preview_days)


def classify_lifecycle_status(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    preview_days: int = LIFECYCLE_PREVIEW_DAYS,
) -> str:
    """Lifecycle state machine (priority order):

    1. fallback — SPA placeholder card
    2. expired  — today > end_date  (must be pruned)
    3. active   — start_date <= today <= end_date
       (auto-promotes from upcoming when start is reached)
    4. upcoming — today <= start_date <= today + preview_days
       and not yet active (i.e. start_date > today)
    5. scheduled — start beyond preview (must be pruned from sync feed)
    """
    today = today or date.today()
    if payload.get("type") == "fallback" or payload.get("offer_category") == "fallback":
        return STATUS_FALLBACK
    start = extract_start_date(payload) or parse_flexible_date(payload.get("start_date"))
    end = parse_flexible_date(payload.get("expiry_date") or payload.get("end_date"))
    if end is not None and today > end:
        return STATUS_EXPIRED
    # Active takes priority when the campaign has started.
    if start is not None and end is not None and start <= today <= end:
        return STATUS_ACTIVE
    if payload.get("is_evergreen") and (start is None or start <= today):
        if end is None or today <= end:
            return STATUS_ACTIVE
    if start is None:
        return STATUS_ACTIVE if (end is None or today <= end) else STATUS_EXPIRED
    # Upcoming window: today < start <= today+preview
    # (user form today <= start <= today+3 with active checked first).
    if is_upcoming_start(start, today=today, preview_days=preview_days):
        return STATUS_UPCOMING
    if today < start:
        return STATUS_SCHEDULED
    return STATUS_ACTIVE


def scheduled_upcoming_start(mall_name: str, *, today: date | None = None) -> date:
    """Stable start date in (today, today+3] derived from mall name."""
    today = today or date.today()
    offset = (sum(ord(ch) for ch in mall_name) % 3) + 1
    return today + timedelta(days=offset)


def infer_vertical_category(payload: dict[str, Any]) -> str:
    text = _blob(payload)
    if ENTERTAINMENT_RE.search(text):
        return VERTICAL_ENTERTAINMENT
    if DINING_RE.search(text):
        return VERTICAL_DINING
    if RETAIL_RE.search(text):
        return VERTICAL_RETAIL
    if SERVICES_RE.search(text):
        return VERTICAL_SERVICES
    if payload.get("offer_type") == "store" or payload.get("type") == "store":
        return VERTICAL_RETAIL
    return VERTICAL_OTHER


def infer_tags(payload: dict[str, Any]) -> list[str]:
    text = _blob(payload)
    tags: list[str] = []
    for tag, pattern in TAG_DEFS:
        if pattern.search(text):
            tags.append(tag)
    if payload.get("is_evergreen") and "Evergreen" not in tags:
        tags.append("Evergreen")
    if classify_lifecycle_status(payload) == STATUS_UPCOMING and "Upcoming" not in tags:
        tags.append("Upcoming")
    if payload.get("offer_type") == "store" or payload.get("type") == "store":
        if "Member" not in tags and re.search(r"會員|App|積分|Rewards|Club", text, re.I):
            tags.append("Member")
    order = {name: i for i, (name, _) in enumerate(TAG_DEFS)}
    order["Evergreen"] = order.get("Evergreen", 99)
    return sorted(set(tags), key=lambda t: order.get(t, 999))


def apply_offer_tags(payload: dict[str, Any]) -> dict[str, Any]:
    """Mutate and return payload with vertical_category + tags + lifecycle status."""
    vertical = infer_vertical_category(payload)
    status = classify_lifecycle_status(payload)
    payload["lifecycle_status"] = status
    tags = infer_tags(payload)
    payload["vertical_category"] = vertical
    payload["vertical_category_label"] = VERTICAL_LABELS.get(vertical, VERTICAL_OTHER)
    payload["tags"] = tags
    payload["tag_labels"] = [TAG_LABELS.get(tag, tag) for tag in tags]
    return payload
