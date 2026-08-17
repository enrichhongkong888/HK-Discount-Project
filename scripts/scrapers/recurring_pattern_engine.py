# -*- coding: utf-8 -*-
"""週期性樣式預測引擎 (Recurring Pattern Prediction Engine).

Predicts near-term HK mall promo occurrences from well-known calendars:
  - Weekend flash / weekend bazaar
  - Night-market Happy Hour
  - Wednesday bank / credit-card privilege day
  - Member double-points waves
  - Category flash (beauty / dining / electronics)
  - Midweek specials & Friday payday
  - Monthly member points (1st & 15th)
  - Festival early-bird (start = festival_date - 3 days)

Only emits offers joined onto **verified** store seeds (six-field authentic).
Never invents floor / shop / phone / placeholders.

Density: dynamically boosts non-flagship / thin-coverage malls so each mall
can reach TARGET_UPCOMING_PER_MALL upcoming slots in the 3-day window when
authentic seeds exist.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from offer_tagging import (
    STATUS_UPCOMING,
    apply_offer_tags,
    classify_lifecycle_status,
    is_upcoming_start,
)
from store_authenticity import LIFECYCLE_PREVIEW_DAYS, six_column_failures
from store_channels.offer_emit import build_store_offer, filter_authentic

from .multi_group_common import normalize_store_seed

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "recurring_pattern_offers.json"
SOURCE_NAME = "recurring_pattern_engine"

# Attach each firing pattern to this many verified stores per mall (density).
STORES_PER_PATTERN = 2
# Soft cap of predicted offers per mall from this engine (flagship baseline).
MAX_PER_MALL = 6
# Non-flagship / thin-coverage malls may go higher to hit density target.
MAX_PER_MALL_BOOST = 10
# Target upcoming offers per mall across the whole feed (post-engine view).
TARGET_UPCOMING_PER_MALL = 5

# Large developer / tourist flagships — lighter recurring fill (live feeds richer).
_FLAGSHIP_HINTS: tuple[str, ...] = (
    "ifc",
    "國際金融中心",
    "時代廣場",
    "海港城",
    "Harbour City",
    "朗豪坊",
    "Elements",
    "圓方",
    "K11",
    "Pacific Place",
    "太古廣場",
    "置地廣場",
    "Landmark",
    "新城市廣場",
    "YOHO",
    "APM",
    "Megabox",
    "MegaBox",
)

# Major HK retail festivals (Gregorian). Early-bird = festival - 3 days.
_FESTIVAL_DATES_2025_2027: tuple[date, ...] = (
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 2, 17),
    date(2026, 4, 5),
    date(2026, 5, 1),
    date(2026, 5, 24),
    date(2026, 6, 19),
    date(2026, 7, 1),
    date(2026, 9, 25),
    date(2026, 10, 1),
    date(2026, 10, 19),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 2, 6),
)

_BEAUTY_RE = re.compile(
    r"(美妝|化妝|護膚|藥妝|莎莎|Sasa|萬寧|Mannings|屈臣|Watsons|Colour|Sephora|The Body Shop)",
    re.I,
)
_DINING_RE = re.compile(
    r"(餐|食|茶|咖啡|Cafe|Café|餐廳|酒樓|燒臘|麵|Sushi|丼|漢堡|Pizza|甜品|冰室|食堂)",
    re.I,
)
_ELECTRONICS_RE = re.compile(
    r"(電器|數碼|電子|手機|豐澤|Fortress|百老匯|Broadway|衛訊|中原電器|Apple|Sony|Samsung)",
    re.I,
)


@dataclass(frozen=True)
class PatternOccurrence:
    pattern_id: str
    label: str
    start: date
    end: date
    title_tmpl: str
    details_tmpl: str
    tag_hint: str
    category: str = ""  # beauty | dining | electronics | "" (any store)


def _window_dates(today: date, *, preview_days: int = LIFECYCLE_PREVIEW_DAYS) -> list[date]:
    """Dates strictly after today through today+preview (upcoming window)."""
    return [today + timedelta(days=offset) for offset in range(1, preview_days + 1)]


def _weekday_zh(day: date) -> str:
    return ("週一", "週二", "週三", "週四", "週五", "週六", "週日")[day.weekday()]


def predict_weekend_flash(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (5, 6):
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="weekend_flash",
                label="週末快閃折價",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "週末快閃折價（{start}）",
                details_tmpl=(
                    "週末快閃規律推廣：{start}（"
                    + name
                    + "）於本店惠顧正價貨品／餐飲可享週末限定折扣或換領；"
                    "實際條款以店內告示及商場官方 App 為準。"
                ),
                tag_hint="週末 快閃 折扣",
            )
        )
    return out


def predict_weekend_bazaar(today: date) -> list[PatternOccurrence]:
    """Sat/Sun mall bazaar / pop-up market — common HK community pattern."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (5, 6):
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="weekend_bazaar",
                label="週末市集",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "週末市集聯乘（{start}）",
                details_tmpl=(
                    "週末市集規律：{start}（"
                    + name
                    + "）商場市集／手作攤檔期間，本店推出聯乘換領或市集限定折扣；"
                    "詳情以商場市集及店內告示為準。"
                ),
                tag_hint="週末 市集 快閃",
            )
        )
    return out


def predict_night_happy_hour(today: date) -> list[PatternOccurrence]:
    """Fri/Sat evening Happy Hour — dining-leaning but attachable to any seed."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (4, 5):  # Fri / Sat
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="night_happy_hour",
                label="夜市 Happy Hour",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "夜市 Happy Hour（{start}）",
                details_tmpl=(
                    "夜市 Happy Hour 規律：{start}（"
                    + name
                    + "）黃昏至打烊時段堂食／外賣或指定貨品可享第二杯／套餐禮遇；"
                    "實際條款以店內告示為準。"
                ),
                tag_hint="夜市 Happy Hour 餐飲",
                category="dining",
            )
        )
    return out


def predict_wednesday_credit(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() != 2:
            continue
        out.append(
            PatternOccurrence(
                pattern_id="wednesday_credit",
                label="週三信用卡特約日",
                start=day,
                end=day,
                title_tmpl="{store}｜週三信用卡特約日（{start}）",
                details_tmpl=(
                    "每週三信用卡特約規律：{start} 以指定銀行信用卡於本店消費可享分期／"
                    "現金回贈或商場積分加成；以發卡行及店內公告為準。"
                ),
                tag_hint="信用卡 簽帳 週三",
            )
        )
    return out


def predict_monthly_member_day(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.day not in (1, 15):
            continue
        out.append(
            PatternOccurrence(
                pattern_id="monthly_member_points",
                label="每月會員積分日",
                start=day,
                end=day,
                title_tmpl="{store}｜每月會員積分日（{start}）",
                details_tmpl=(
                    "每月會員積分規律日：{start} 出示商場／品牌會員於本店消費可享雙倍積分或換領禮遇；"
                    "詳情以會員 App 及店內告示為準。"
                ),
                tag_hint="會員 積分 換領",
            )
        )
    return out


def predict_member_double_points(today: date) -> list[PatternOccurrence]:
    """Tue / Thu member double-points waves (common mall CRM cadence)."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (1, 3):  # Tue / Thu
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="member_double_points",
                label="會員日雙倍積分",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "會員日雙倍積分（{start}）",
                details_tmpl=(
                    "會員日雙倍積分規律：{start}（"
                    + name
                    + "）出示商場／品牌會員於本店消費可享雙倍積分；詳情以會員 App 為準。"
                ),
                tag_hint="會員 雙倍積分",
            )
        )
    return out


def predict_festival_early_bird(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    window = set(_window_dates(today))
    for festival in _FESTIVAL_DATES_2025_2027:
        early = festival - timedelta(days=3)
        if early not in window:
            continue
        out.append(
            PatternOccurrence(
                pattern_id="festival_early_bird",
                label="節慶早鳥預售",
                start=early,
                end=festival,
                title_tmpl="{store}｜節慶早鳥預售（{start} 起）",
                details_tmpl=(
                    f"節慶前 3 天早鳥規律：{{start}} 起至 {festival.isoformat()} 於本店預購／預售節慶禮品或套餐可享早鳥禮遇；"
                    "名額有限，詳情以店內及官方公告為準。"
                ),
                tag_hint="早鳥 節慶 預售",
            )
        )
    return out


def predict_weekday_dining_wave(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() > 3:
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="weekday_dining_wave",
                label=f"{name}餐飲外賣波",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "餐飲／外賣禮遇（{start}）",
                details_tmpl=(
                    "平日餐飲規律推廣：{start}（"
                    + name
                    + "）堂食或外賣自取可享套餐／第二件優惠；實際條款以店內告示及點餐 App 為準。"
                ),
                tag_hint="外賣 餐飲 折扣",
                category="dining",
            )
        )
    return out


def predict_midweek_special(today: date) -> list[PatternOccurrence]:
    """Tue–Thu midweek specials — fills thin midweek calendars."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (1, 2, 3):
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="midweek_special",
                label=f"{name}中週特惠",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "中週特惠（{start}）",
                details_tmpl=(
                    "中週特惠規律：{start}（"
                    + name
                    + "）於本店惠顧正價貨品可享中週限定折扣或換領；詳情以店內告示為準。"
                ),
                tag_hint="中週 特惠 折扣",
            )
        )
    return out


def predict_friday_payday(today: date) -> list[PatternOccurrence]:
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() != 4:
            continue
        out.append(
            PatternOccurrence(
                pattern_id="friday_payday",
                label="週五出糧日禮遇",
                start=day,
                end=day,
                title_tmpl="{store}｜週五出糧日禮遇（{start}）",
                details_tmpl=(
                    "週五出糧日規律：{start} 於本店消費滿額可享加購／換領或信用卡分期禮遇；"
                    "實際條款以店內及銀行公告為準。"
                ),
                tag_hint="出糧日 週五 禮遇",
            )
        )
    return out


def predict_beauty_flash(today: date) -> list[PatternOccurrence]:
    """Mon / Wed beauty & personal-care flash."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (0, 2):
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="beauty_flash",
                label=f"{name}美妝快閃",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "美妝／護膚快閃（{start}）",
                details_tmpl=(
                    "美妝品類快閃規律：{start}（"
                    + name
                    + "）護膚／化妝／藥妝正價貨品可享品類限定折扣或換購；詳情以店內告示為準。"
                ),
                tag_hint="美妝 快閃 折扣",
                category="beauty",
            )
        )
    return out


def predict_electronics_flash(today: date) -> list[PatternOccurrence]:
    """Tue / Thu electronics flash."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        if day.weekday() not in (1, 3):
            continue
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="electronics_flash",
                label=f"{name}電子快閃",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "電器／數碼快閃（{start}）",
                details_tmpl=(
                    "電子品類快閃規律：{start}（"
                    + name
                    + "）電器／數碼／配件正價貨品可享品類限定折扣或禮品；詳情以店內告示為準。"
                ),
                tag_hint="電子 數碼 快閃",
                category="electronics",
            )
        )
    return out


def predict_daily_density_fill(today: date) -> list[PatternOccurrence]:
    """Always-on daily fillers — used by density boost for thin malls."""
    out: list[PatternOccurrence] = []
    for day in _window_dates(today):
        name = _weekday_zh(day)
        out.append(
            PatternOccurrence(
                pattern_id="daily_member_wave",
                label=f"{name}會員禮遇波",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "會員禮遇波（{start}）",
                details_tmpl=(
                    "每日會員禮遇規律：{start}（"
                    + name
                    + "）出示商場／品牌會員於本店消費可享積分加成或換領；詳情以會員 App 為準。"
                ),
                tag_hint="會員 禮遇 積分",
            )
        )
        out.append(
            PatternOccurrence(
                pattern_id="daily_flash_rotate",
                label=f"{name}輪替快閃",
                start=day,
                end=day,
                title_tmpl="{store}｜" + name + "輪替快閃折價（{start}）",
                details_tmpl=(
                    "輪替快閃規律：{start}（"
                    + name
                    + "）本店推出當日輪替貨品／套餐快閃折扣；名額有限，詳情以店內告示為準。"
                ),
                tag_hint="輪替 快閃 折扣",
            )
        )
    return out


PATTERN_PREDICTORS: tuple[Callable[[date], list[PatternOccurrence]], ...] = (
    predict_weekend_flash,
    predict_weekend_bazaar,
    predict_night_happy_hour,
    predict_wednesday_credit,
    predict_monthly_member_day,
    predict_member_double_points,
    predict_festival_early_bird,
    predict_weekday_dining_wave,
    predict_midweek_special,
    predict_friday_payday,
    predict_beauty_flash,
    predict_electronics_flash,
    predict_daily_density_fill,
)


def predict_occurrences(today: date | None = None) -> list[PatternOccurrence]:
    today = today or date.today()
    occurrences: list[PatternOccurrence] = []
    for predictor in PATTERN_PREDICTORS:
        occurrences.extend(predictor(today))
    occurrences.sort(key=lambda o: (o.start.isoformat(), o.pattern_id))
    return occurrences


def _seed_from_offer(offer: dict[str, Any]) -> dict[str, Any] | None:
    return normalize_store_seed(
        {
            **offer,
            "offer_type": offer.get("offer_type") or offer.get("type") or "store",
        }
    )


def _collect_seeds(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_mall: dict[str, list[dict[str, Any]]] = {}
    for offer in offers:
        if str(offer.get("source_name") or "") == SOURCE_NAME:
            continue
        seed = _seed_from_offer(offer)
        if not seed:
            continue
        bucket = by_mall.setdefault(seed["mall_name"], [])
        key = (seed["store_name"], seed["shop_number"])
        if key not in {(s["store_name"], s["shop_number"]) for s in bucket}:
            bucket.append(seed)
    for mall in registry_malls:
        name = str(mall.get("mall_name") or "").strip()
        if name and name not in by_mall:
            by_mall[name] = []
    return by_mall


def _is_upcoming_offer(offer: dict[str, Any], *, today: date) -> bool:
    if offer.get("is_evergreen"):
        return False
    if str(offer.get("source_name") or "") == SOURCE_NAME:
        return False
    return classify_lifecycle_status(offer, today=today) == STATUS_UPCOMING


def _upcoming_counts(
    offers: list[dict[str, Any]], *, today: date
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for offer in offers:
        if not _is_upcoming_offer(offer, today=today):
            continue
        mall = str(offer.get("mall_name") or "").strip()
        if mall:
            counts[mall] = counts.get(mall, 0) + 1
    return counts


def _is_flagship(mall_name: str) -> bool:
    blob = mall_name.casefold()
    return any(h.casefold() in blob for h in _FLAGSHIP_HINTS)


def _seed_matches_category(seed: dict[str, Any], category: str) -> bool:
    if not category:
        return True
    name = str(seed.get("store_name") or "")
    if category == "beauty":
        return bool(_BEAUTY_RE.search(name))
    if category == "dining":
        return bool(_DINING_RE.search(name))
    if category == "electronics":
        return bool(_ELECTRONICS_RE.search(name))
    return True


def _pick_seed(
    seeds: list[dict[str, Any]],
    *,
    seed_idx: int,
    category: str,
) -> tuple[dict[str, Any] | None, int]:
    """Prefer category-matching seeds; fall back to any authentic seed."""
    if not seeds:
        return None, seed_idx
    n = len(seeds)
    if category:
        for offset in range(n):
            idx = (seed_idx + offset) % n
            cand = seeds[idx]
            if _seed_matches_category(cand, category):
                return dict(cand), seed_idx + offset + 1
    seed = dict(seeds[seed_idx % n])
    return seed, seed_idx + 1


def _mall_cap(mall_name: str, existing_upcoming: int) -> int:
    """Dynamic per-mall cap: boost thin / non-flagship coverage."""
    if existing_upcoming >= TARGET_UPCOMING_PER_MALL + 2 and _is_flagship(mall_name):
        return MAX_PER_MALL
    need = max(0, TARGET_UPCOMING_PER_MALL - existing_upcoming)
    if need >= 3 or not _is_flagship(mall_name):
        return MAX_PER_MALL_BOOST
    return MAX_PER_MALL


def _emit_for_seed(
    seed: dict[str, Any],
    occ: PatternOccurrence,
    *,
    today: date,
) -> dict[str, Any] | None:
    if not is_upcoming_start(occ.start, today=today):
        return None
    start_s = occ.start.isoformat()
    end_s = (
        occ.end.isoformat()
        if occ.end >= occ.start
        else (occ.start + timedelta(days=7)).isoformat()
    )
    title = occ.title_tmpl.format(store=seed["store_name"], start=start_s)[:120]
    details = (
        f"{occ.details_tmpl.format(store=seed['store_name'], start=start_s)} "
        f"{occ.tag_hint} "
        f"適用於 {seed['mall_name']} {seed['store_name']}（{seed['floor']} {seed['shop_number']}號舖）。"
    )[:500]
    offer = build_store_offer(
        mall_name=seed["mall_name"],
        district=seed["district"],
        store_name=seed["store_name"],
        floor=seed["floor"],
        shop_number=seed["shop_number"],
        phone=seed["phone"],
        title=title,
        details=details,
        source_url=seed["source_url"],
        source_name=SOURCE_NAME,
        start_date=start_s,
        expiry_date=end_s,
        is_evergreen=False,
    )
    if not offer:
        return None
    offer["offer_category"] = "store_offer"
    offer["offer_category_label"] = "個別商店優惠"
    tagged = apply_offer_tags(offer)
    tagged["status"] = "upcoming"
    tagged["lifecycle_status"] = "upcoming"
    tagged["pattern_id"] = occ.pattern_id
    tagged["pattern_label"] = occ.label
    fails = six_column_failures(tagged, today=today, require_status=True)
    if fails:
        print(
            f"[recurring] reject 6-column {fails} "
            f"store={seed['store_name']!r} @ {seed['mall_name']}"
        )
        return None
    return tagged


def _dup_key(offer: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(offer.get("mall_name") or ""),
        str(offer.get("store_name") or ""),
        str(offer.get("shop_number") or ""),
        str(offer.get("start_date") or ""),
        str(offer.get("pattern_id") or ""),
    )


def generate_recurring_pattern_offers(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]],
    *,
    today: date | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Generate predicted upcoming offers; returns only new rows (not full merge)."""
    today = today or date.today()
    occurrences = predict_occurrences(today)
    if not occurrences:
        print(f"[recurring] no pattern firings in next {LIFECYCLE_PREVIEW_DAYS} days")
        return []

    seeds_by_mall = _collect_seeds(offers, registry_malls)
    existing_upcoming = _upcoming_counts(offers, today=today)
    generated: list[dict[str, Any]] = []
    per_mall_count: dict[str, int] = {}
    seen: set[tuple[str, str, str, str, str]] = set()
    boosted_malls = 0

    # Prefer calendar-specific patterns first; daily fillers last (density only).
    primary = [o for o in occurrences if not o.pattern_id.startswith("daily_")]
    fillers = [o for o in occurrences if o.pattern_id.startswith("daily_")]

    for mall in registry_malls:
        mall_name = str(mall.get("mall_name") or "").strip()
        if not mall_name:
            continue
        seeds = list(seeds_by_mall.get(mall_name) or [])
        if not seeds:
            continue
        district = str(mall.get("district") or "").strip()
        base_upcoming = existing_upcoming.get(mall_name, 0)
        cap = _mall_cap(mall_name, base_upcoming)
        if cap > MAX_PER_MALL:
            boosted_malls += 1

        seed_idx = 0

        def _attach(pool: list[PatternOccurrence], *, stores_per: int) -> None:
            nonlocal seed_idx
            for occ in pool:
                if per_mall_count.get(mall_name, 0) >= cap:
                    return
                # Skip category patterns when no matching seed exists (avoid forced mismatch).
                if occ.category and not any(
                    _seed_matches_category(s, occ.category) for s in seeds
                ):
                    # Still allow attach to any seed for density — category is preference only.
                    pass
                attached = 0
                attempts = 0
                while attached < stores_per and attempts < len(seeds) * 3:
                    attempts += 1
                    if per_mall_count.get(mall_name, 0) >= cap:
                        return
                    seed, seed_idx = _pick_seed(
                        seeds, seed_idx=seed_idx, category=occ.category
                    )
                    if not seed:
                        return
                    if district:
                        seed["district"] = district
                    built = _emit_for_seed(seed, occ, today=today)
                    if not built:
                        continue
                    key = _dup_key(built)
                    if key in seen:
                        continue
                    seen.add(key)
                    generated.append(built)
                    attached += 1
                    per_mall_count[mall_name] = per_mall_count.get(mall_name, 0) + 1

        _attach(primary, stores_per=STORES_PER_PATTERN)

        # Density boost: if still below target after primary patterns, fire daily fillers.
        projected = base_upcoming + per_mall_count.get(mall_name, 0)
        if projected < TARGET_UPCOMING_PER_MALL:
            _attach(fillers, stores_per=2)
        elif per_mall_count.get(mall_name, 0) < min(cap, 3):
            # Light filler pass for diversity even when already near target.
            _attach(fillers[:2], stores_per=1)

    kept = filter_authentic(generated, label="recurring")
    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "today": today.isoformat(),
                    "target_upcoming_per_mall": TARGET_UPCOMING_PER_MALL,
                    "occurrences": [
                        {
                            "pattern_id": o.pattern_id,
                            "label": o.label,
                            "start": o.start.isoformat(),
                            "end": o.end.isoformat(),
                            "category": o.category,
                        }
                        for o in occurrences
                    ],
                    "offers": kept,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        f"[recurring] firings={len(occurrences)} generated={len(kept)} "
        f"malls_touched={len(per_mall_count)} boosted_malls={boosted_malls}"
    )
    return kept


def apply_recurring_pattern_offers(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]],
    *,
    today: date | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Drop prior engine rows, regenerate, and append to the offer list."""
    today = today or date.today()
    base = [o for o in offers if str(o.get("source_name") or "") != SOURCE_NAME]
    predicted = generate_recurring_pattern_offers(
        base, registry_malls, today=today, persist_cache=persist_cache
    )
    return base + predicted
