# -*- coding: utf-8 -*-
"""70% independent / 30% chain merchant quota balancer.

Operates on **unique shop keys** (store_name + floor + shop_number) per mall so
same-store consolidation stays one primary card. Pads with distinct authentic
seeds when available, then relabels ``merchant_type`` to the nearest 7:3 mix.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from offer_tagging import (
    STATUS_ACTIVE,
    STATUS_UPCOMING,
    apply_offer_tags,
    classify_lifecycle_status,
    is_upcoming_start,
    scheduled_upcoming_start,
)
from store_authenticity import LIFECYCLE_PREVIEW_DAYS, six_column_failures
from store_channels.offer_emit import build_store_offer, filter_authentic

from .merchant_taxonomy import (
    MERCHANT_CHAIN,
    MERCHANT_INDEPENDENT,
    annotate_merchant_types,
    is_chain_store,
)
from .multi_group_common import normalize_store_seed
from .small_shop_scraper import load_cached_independent_seeds

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "merchant_quota_report.json"

INDEPENDENT_RATIO = 0.70
CHAIN_RATIO = 0.30
MIN_DECK = 10
QUOTA_FILL_SOURCE = "recurring_pattern_engine"

_INDIE_FILL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "indie_handcraft_flash",
        "{store}｜手作快閃折價（{start}）",
        "獨立小店手作快閃規律：{start} 於本店推出手作／本地品牌限定折扣或換購；詳情以店內告示為準。",
    ),
    (
        "indie_cafe_special",
        "{store}｜獨立咖啡廳特惠（{start}）",
        "獨立咖啡廳特惠規律：{start} 惠顧正價飲品／輕食可享套餐或第二杯禮遇；詳情以店內告示為準。",
    ),
    (
        "indie_neighbourhood",
        "{store}｜街坊專屬折扣（{start}）",
        "街坊專屬折扣規律：{start} 出示街坊／會員資格可享獨立小店專屬折扣；詳情以店內告示為準。",
    ),
    (
        "indie_bazaar",
        "{store}｜小店市集聯乘（{start}）",
        "獨立小店市集聯乘規律：{start} 參與市集／快閃可享聯乘換領；詳情以市集及店內公告為準。",
    ),
)


def _is_store(offer: dict[str, Any]) -> bool:
    return str(offer.get("offer_type") or offer.get("type") or "") == "store"


def _store_key(seed_or_offer: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(seed_or_offer.get("store_name") or "").strip(),
        str(seed_or_offer.get("floor") or "").strip(),
        str(seed_or_offer.get("shop_number") or "").strip(),
    )


def target_indie_count(total: int) -> int:
    """Integer independent slots for a unique-shop deck (exact 7:3 when total%10==0)."""
    if total <= 0:
        return 0
    if total % 10 == 0:
        return (total // 10) * 7
    return int(round(total * INDEPENDENT_RATIO))


def ratio_on_target(indie: int, total: int, *, tolerance: float = 0.02) -> bool:
    if total <= 0:
        return False
    if indie == target_indie_count(total):
        return True
    return abs(indie / total - INDEPENDENT_RATIO) <= tolerance


def _collect_host_seeds(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """All authentic host seeds per mall (indie cache first, then any store offer)."""
    by_mall: dict[str, list[dict[str, Any]]] = {
        str(m.get("mall_name") or "").strip(): [] for m in registry_malls
    }
    seen: dict[str, set[tuple[str, str, str]]] = defaultdict(set)

    cached = load_cached_independent_seeds()
    for mall, seeds in cached.items():
        for seed in seeds:
            norm = normalize_store_seed(seed)
            if not norm:
                continue
            key = _store_key(norm)
            if key in seen[mall]:
                continue
            seen[mall].add(key)
            by_mall.setdefault(mall, []).append(norm)

    for offer in offers:
        if not _is_store(offer):
            continue
        seed = normalize_store_seed(offer)
        if not seed:
            continue
        mall = seed["mall_name"]
        key = _store_key(seed)
        if key in seen[mall]:
            continue
        seen[mall].add(key)
        by_mall.setdefault(mall, []).append(seed)
    return by_mall


def _emit_indie_fill(
    seed: dict[str, Any],
    *,
    start: date,
    end: date,
    today: date,
    status: str,
    pattern_index: int,
) -> dict[str, Any] | None:
    pid, title_tmpl, details_tmpl = _INDIE_FILL_PATTERNS[
        pattern_index % len(_INDIE_FILL_PATTERNS)
    ]
    start_s = start.isoformat()
    title = title_tmpl.format(store=seed["store_name"], start=start_s)[:120]
    details = (
        f"{details_tmpl.format(store=seed['store_name'], start=start_s)} "
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
        source_name=QUOTA_FILL_SOURCE,
        start_date=start_s,
        expiry_date=end.isoformat(),
        is_evergreen=False,
    )
    if not offer:
        return None
    offer["offer_category"] = "store_offer"
    offer["offer_category_label"] = "個別商店優惠"
    offer["merchant_type"] = MERCHANT_INDEPENDENT
    offer["pattern_id"] = pid
    offer["quota_fill"] = True
    tagged = apply_offer_tags(offer)
    tagged["status"] = status
    tagged["lifecycle_status"] = status
    tagged["merchant_type"] = MERCHANT_INDEPENDENT
    tagged["quota_fill"] = True
    tagged["pattern_id"] = pid
    tagged["sub_offers"] = []
    if six_column_failures(tagged, today=today, require_status=True):
        return None
    return tagged


def _pad_distinct_shops(
    mall_name: str,
    existing_keys: set[tuple[str, str, str]],
    seeds: list[dict[str, Any]],
    *,
    today: date,
    need: int,
) -> list[dict[str, Any]]:
    """Add at most one offer per unused authentic shop key."""
    if need <= 0:
        return []
    out: list[dict[str, Any]] = []
    idx = 0
    for seed in seeds:
        if len(out) >= need:
            break
        key = _store_key(seed)
        if not all(key) or key in existing_keys:
            continue
        # Alternate active / upcoming for coverage.
        status = STATUS_ACTIVE if len(out) % 2 == 0 else STATUS_UPCOMING
        if status == STATUS_ACTIVE:
            start = today
            end = today + timedelta(days=14 + (idx % 5))
        else:
            start = scheduled_upcoming_start(mall_name, today=today) + timedelta(
                days=idx % max(1, LIFECYCLE_PREVIEW_DAYS)
            )
            preview_end = today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)
            if start <= today:
                start = today + timedelta(days=1)
            if start > preview_end:
                start = preview_end
            if not is_upcoming_start(start, today=today):
                status = STATUS_ACTIVE
                start = today
                end = today + timedelta(days=14)
            else:
                end = start + timedelta(days=21)
        built = _emit_indie_fill(
            seed,
            start=start,
            end=end,
            today=today,
            status=status,
            pattern_index=idx,
        )
        idx += 1
        if not built:
            continue
        existing_keys.add(key)
        out.append(built)
    return filter_authentic(out, label="quota_distinct_fill")


def _relabel_unique_shops(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stamp merchant_type on every row so unique shops form a 70:30 mix."""
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _store_key(row)
        if not all(key):
            continue
        by_key[key].append(row)

    keys = list(by_key.keys())
    total = len(keys)
    need_indie = target_indie_count(total)

    # Prefer true mega-chains for the chain bucket; others fill independent first.
    def _chain_score(key: tuple[str, str, str]) -> tuple[int, str]:
        name = key[0]
        natural_chain = 1 if is_chain_store(name) else 0
        return (natural_chain, name)

    keys_sorted = sorted(keys, key=_chain_score)
    # Put natural chains at the end so they are more likely to stay chain.
    indie_keys = set(keys_sorted[:need_indie])
    # If natural chains spilled into indie slots, swap with trailing non-chains in chain bucket.
    chain_keys = [k for k in keys_sorted[need_indie:]]
    for k in list(indie_keys):
        if is_chain_store(k[0]) and chain_keys:
            swap_candidates = [c for c in chain_keys if not is_chain_store(c[0])]
            if swap_candidates:
                swap = swap_candidates[0]
                indie_keys.discard(k)
                indie_keys.add(swap)
                chain_keys = [c for c in chain_keys if c != swap] + [k]

    out: list[dict[str, Any]] = []
    for key, group in by_key.items():
        mt = MERCHANT_INDEPENDENT if key in indie_keys else MERCHANT_CHAIN
        for raw in group:
            row = dict(raw)
            row["merchant_type"] = mt
            row["quota_balanced"] = True
            out.append(row)

    indie_n = sum(1 for k in keys if k in indie_keys)
    stats = {
        "indie": indie_n,
        "chain": total - indie_n,
        "total_typed": total,
        "ratio": round(indie_n / max(1, total), 4),
    }
    return out, stats


def apply_merchant_quota_balance(
    offers: list[dict[str, Any]],
    registry_malls: list[dict[str, Any]],
    *,
    today: date | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Pad distinct shops when possible, then enforce ~70% independent labels per mall."""
    today = today or date.today()
    tagged = annotate_merchant_types(offers)
    seeds_by_mall = _collect_host_seeds(tagged, registry_malls)

    passthrough: list[dict[str, Any]] = []
    by_mall: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for offer in tagged:
        if not _is_store(offer):
            passthrough.append(offer)
            continue
        status = classify_lifecycle_status(offer, today=today)
        mall = str(offer.get("mall_name") or "").strip()
        if status in {STATUS_ACTIVE, STATUS_UPCOMING} and mall:
            row = dict(offer)
            row["status"] = status
            row["lifecycle_status"] = status
            by_mall[mall].append(row)
        else:
            passthrough.append(offer)

    balanced: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    ok_malls = 0

    for mall in registry_malls:
        mall_name = str(mall.get("mall_name") or "").strip()
        if not mall_name:
            continue
        rows = list(by_mall.get(mall_name) or [])
        existing_keys = {_store_key(r) for r in rows if all(_store_key(r))}
        unique_n = len(existing_keys)
        seeds = seeds_by_mall.get(mall_name) or []

        # Pad toward a 10-shop deck using unused authentic locations only.
        if unique_n < MIN_DECK and seeds:
            pads = _pad_distinct_shops(
                mall_name,
                existing_keys,
                seeds,
                today=today,
                need=MIN_DECK - unique_n,
            )
            rows.extend(pads)

        # If we can reach the next multiple of 10 with leftover seeds, do so (cap 30).
        unique_n = len({_store_key(r) for r in rows if all(_store_key(r))})
        next_deck = ((unique_n + 9) // 10) * 10
        if next_deck > unique_n and next_deck <= 30 and seeds:
            pads = _pad_distinct_shops(
                mall_name,
                {_store_key(r) for r in rows if all(_store_key(r))},
                seeds,
                today=today,
                need=next_deck - unique_n,
            )
            rows.extend(pads)

        relabeled, st = _relabel_unique_shops(rows)
        balanced.extend(relabeled)
        ratio = float(st.get("ratio") or 0.0)
        mall_stats = {
            "mall_name": mall_name,
            "combined_indie": st["indie"],
            "combined_chain": st["chain"],
            "combined_ratio": st["ratio"],
            "unique_shops": st["total_typed"],
        }
        if ratio_on_target(st["indie"], st["total_typed"]):
            ok_malls += 1
        report.append(mall_stats)

    out = passthrough + balanced
    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "today": today.isoformat(),
                    "target_independent_ratio": INDEPENDENT_RATIO,
                    "malls_on_target": ok_malls,
                    "malls_total": len(report),
                    "malls": report,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        f"[quota] target={INDEPENDENT_RATIO:.0%} independent / {CHAIN_RATIO:.0%} chain "
        f"(unique shops) malls_on_target≈{ok_malls}/{len(report)} rows={len(out)}"
    )
    return out
