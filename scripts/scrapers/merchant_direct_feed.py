# -*- coding: utf-8 -*-
"""商戶自主登錄結構化數據管線 (Merchant Direct Feed).

Reads merchant-submitted JSON / CSV files from ``data/merchant_submissions/``,
normalises rows against the 74-mall registry, enforces the six-column gate, and
emits authentic store offers with ``source_name=merchant_direct_feed``.

Only rows whose start_date falls in ``[today, today + LIFECYCLE_PREVIEW_DAYS]``
are retained (lifecycle then classifies active vs upcoming).
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from offer_tagging import apply_offer_tags, parse_flexible_date
from store_authenticity import (
    LIFECYCLE_PREVIEW_DAYS,
    is_placeholder_text,
    is_precise_phone,
    is_precise_shop_number,
    six_column_failures,
)
from store_channels.http_util import normalize_phone
from store_channels.mall_match import build_registry_index, match_mall
from store_channels.offer_emit import build_store_offer, filter_authentic

ROOT = Path(__file__).resolve().parents[2]
SUBMISSIONS_DIR = ROOT / "data" / "merchant_submissions"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"
CACHE_PATH = ROOT / "data" / "cache" / "merchant_direct_feed_offers.json"
SOURCE_NAME = "merchant_direct_feed"

REQUIRED_FIELDS = (
    "mall_name",
    "store_name",
    "floor",
    "shop_number",
    "phone",
    "title",
    "details",
    "start_date",
    "expiry_date",
    "source_url",
)


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(payload.get("malls") or []) if isinstance(payload, dict) else []


def _read_json_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("submissions", "offers", "stores", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
        if any(k in payload for k in REQUIRED_FIELDS):
            return [payload]
    return []


def _read_csv_file(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def discover_submission_files(directory: Path | None = None) -> list[Path]:
    root = directory or SUBMISSIONS_DIR
    if not root.exists():
        return []
    files: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith("_") or name.startswith("."):
            continue
        if name.lower().endswith((".json", ".csv")):
            files.append(path)
    return files


def load_raw_submissions(directory: Path | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in discover_submission_files(directory):
        try:
            if path.suffix.lower() == ".json":
                batch = _read_json_file(path)
            else:
                batch = _read_csv_file(path)
        except (OSError, json.JSONDecodeError, csv.Error) as exc:
            print(f"[merchant_feed] skip {path.name}: {exc}")
            continue
        for row in batch:
            row = dict(row)
            row["_submission_file"] = path.name
            rows.append(row)
        print(f"[merchant_feed] loaded {path.name} rows={len(batch)}")
    return rows


def _in_preview_window(start: date, *, today: date) -> bool:
    """Accept start_date ∈ [today, today + preview_days]."""
    return today <= start <= today + timedelta(days=LIFECYCLE_PREVIEW_DAYS)


def normalize_submission(
    row: dict[str, Any],
    registry: list[dict[str, Any]],
    *,
    today: date,
) -> dict[str, Any] | None:
    """Clean one merchant row; return None when it fails authenticity gates."""
    index = build_registry_index(registry)
    mall_hint = str(row.get("mall_name") or row.get("mall_hint") or "").strip()
    address = str(row.get("address") or "").strip()
    hit = match_mall(index, mall_hint=mall_hint, address=address or mall_hint)
    if not hit:
        print(f"[merchant_feed] reject unknown mall={mall_hint!r} file={row.get('_submission_file')}")
        return None

    store = str(row.get("store_name") or "").strip()
    floor = str(row.get("floor") or "").strip()
    shop = str(row.get("shop_number") or row.get("shop") or "").strip()
    phone = normalize_phone(str(row.get("phone") or row.get("tel") or ""))
    title = str(row.get("title") or row.get("offer_title") or "").strip()
    details = str(row.get("details") or row.get("offer_text") or row.get("description") or "").strip()
    source_url = str(row.get("source_url") or row.get("url") or "").strip()
    category_tag = str(
        row.get("vertical_category")
        or row.get("category_tag")
        or row.get("tags")
        or row.get("category")
        or "Retail"
    ).strip()

    start = parse_flexible_date(row.get("start_date") or row.get("effective_from"))
    end = parse_flexible_date(
        row.get("expiry_date") or row.get("end_date") or row.get("valid_to")
    )

    # Field presence / placeholder hard rejects
    for label, value in (
        ("store_name", store),
        ("floor", floor),
        ("shop_number", shop),
        ("phone", phone),
        ("title", title),
        ("details", details),
        ("source_url", source_url),
    ):
        if is_placeholder_text(value) or not str(value or "").strip():
            print(
                f"[merchant_feed] reject missing/placeholder {label} "
                f"store={store!r} mall={hit.mall_name}"
            )
            return None

    if not is_precise_shop_number(shop) or not is_precise_phone(phone):
        print(f"[merchant_feed] reject imprecise shop/phone store={store!r} @ {hit.mall_name}")
        return None

    if start is None or end is None:
        print(f"[merchant_feed] reject invalid dates store={store!r} @ {hit.mall_name}")
        return None
    if end < start:
        print(f"[merchant_feed] reject end<start store={store!r} @ {hit.mall_name}")
        return None
    if not _in_preview_window(start, today=today):
        print(
            f"[merchant_feed] reject start outside preview window "
            f"start={start.isoformat()} store={store!r} @ {hit.mall_name}"
        )
        return None

    if not title:
        title = f"{store}｜商戶自主登錄優惠"
    if category_tag and category_tag not in details:
        details = f"[{category_tag}] {details}"

    offer = build_store_offer(
        mall_name=hit.mall_name,
        district=hit.district,
        store_name=store,
        floor=floor,
        shop_number=shop,
        phone=phone,
        title=title[:120],
        details=details[:500],
        source_url=source_url,
        source_name=SOURCE_NAME,
        start_date=start.isoformat(),
        expiry_date=end.isoformat(),
        is_evergreen=False,
    )
    if not offer:
        print(f"[merchant_feed] reject build_store_offer failed store={store!r} @ {hit.mall_name}")
        return None

    # Ensure category tags for six-column col2 before status stamp.
    offer["offer_category"] = "store_offer"
    offer["offer_category_label"] = "個別商店優惠"
    if category_tag:
        offer["vertical_category"] = category_tag if category_tag in {
            "Dining", "Retail", "Entertainment", "Services", "Other"
        } else offer.get("vertical_category")
    tagged = apply_offer_tags(offer)

    # Status will be finalized by lifecycle_manager; seed a consistent value now.
    if start > today:
        tagged["status"] = "upcoming"
        tagged["lifecycle_status"] = "upcoming"
    else:
        tagged["status"] = "active"
        tagged["lifecycle_status"] = "active"

    fails = six_column_failures(tagged, today=today, require_status=True)
    if fails:
        print(
            f"[merchant_feed] reject 6-column {fails} store={store!r} @ {hit.mall_name}"
        )
        return None
    return tagged


def scrape_merchant_direct_feed(
    *,
    today: date | None = None,
    directory: Path | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    today = today or date.today()
    registry = _load_registry()
    raw_rows = load_raw_submissions(directory)
    offers: list[dict[str, Any]] = []
    for row in raw_rows:
        offer = normalize_submission(row, registry, today=today)
        if offer:
            offers.append(offer)

    kept = filter_authentic(offers, label="merchant_feed")
    if persist_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "today": today.isoformat(),
                    "offers": kept,
                    "raw_submissions": len(raw_rows),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        f"[merchant_feed] raw={len(raw_rows)} authentic={len(kept)} "
        f"dir={directory or SUBMISSIONS_DIR}"
    )
    return kept


def apply_merchant_direct_feed(
    offers: list[dict[str, Any]],
    *,
    today: date | None = None,
    directory: Path | None = None,
    persist_cache: bool = True,
) -> list[dict[str, Any]]:
    """Replace prior merchant_direct_feed rows and append freshly ingested ones."""
    today = today or date.today()
    base = [o for o in offers if str(o.get("source_name") or "") != SOURCE_NAME]
    fresh = scrape_merchant_direct_feed(
        today=today, directory=directory, persist_cache=persist_cache
    )
    return base + fresh
