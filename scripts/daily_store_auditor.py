"""Daily store relocation / closure / expiry auditor with hard-delete cleanup.

Compares ``malls.json`` store offers against today's official directory snapshot
(``data/cache/official_directory.json``, produced by ``crawl_mall_stores.py``).

Rules
-----
A. Relocated unit: ``(mall_id, unit)`` now maps to a different ``store_name``.
B. Closed / vacated: ``store_name`` + ``unit`` absent from official directory.
C. Expired: ``end_date`` / ``expiry_date`` is strictly before today (Asia/Hong_Kong).

Disposition: hard-delete matching store offers from ``malls.json``, delete local
facade files under ``frontend/images/stores/``, append ``logs/audit_YYYY-MM-DD.log``,
and append records to ``archived_deals.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MALLS = ROOT / "malls.json"
DIRECTORY_CACHE = ROOT / "data" / "cache" / "official_directory.json"
ARCHIVE_PATH = ROOT / "archived_deals.json"
LOG_DIR = ROOT / "logs"
STORE_IMG_DIR = ROOT / "frontend" / "images" / "stores"

HK_TZ = timezone(timedelta(hours=8))


def today_hk() -> date:
    return datetime.now(HK_TZ).date()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def parse_date(value: Any) -> date | None:
    text = norm(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def make_mall_id(mall_name: str) -> str:
    text = norm(mall_name)
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if len(ascii_part) >= 2:
        return ascii_part[:32]
    import hashlib

    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def local_image_path(offer: dict[str, Any]) -> Path | None:
    for key in ("store_image_url", "facade_image_url", "image_url"):
        rel = norm(offer.get(key))
        if rel.startswith("frontend/images/stores/") or rel.startswith("images/stores/"):
            path = ROOT / rel.replace("\\", "/")
            return path
    store_key = norm(offer.get("store_key"))
    if store_key:
        return STORE_IMG_DIR / f"{store_key}.jpg"
    return None


def classify_offer(
    *,
    mall_id: str,
    offer: dict[str, Any],
    by_unit: dict[str, Any],
    by_name_unit: dict[str, Any],
    store_keys: set[str],
    today: date,
) -> str | None:
    """Return rule id (A/B/C) or None if the offer should be kept."""
    store_name = norm(offer.get("store_name"))
    unit = norm(offer.get("shop_number") or offer.get("unit"))
    store_key = norm(offer.get("store_key"))
    if not (store_name and unit and mall_id):
        return None

    end = parse_date(offer.get("end_date") or offer.get("expiry_date"))
    evergreen = bool(offer.get("is_evergreen"))
    # Rule C: expired dated promos only (evergreen cards keep rolling).
    if end is not None and end < today and not evergreen:
        return "C_expired"

    unit_key = f"{mall_id}||{unit.casefold()}"
    name_unit_key = f"{mall_id}||{store_name.casefold()}||{unit.casefold()}"

    # Empty directory → skip A/B to avoid mass wipe.
    if not by_unit and not by_name_unit and not store_keys:
        return None

    # Still present by composite key → keep.
    if store_key and store_key in store_keys:
        return None

    unit_hit = by_unit.get(unit_key)
    if isinstance(unit_hit, dict):
        live_name = norm(unit_hit.get("store_name"))
        if live_name and live_name.casefold() != store_name.casefold():
            return "A_relocated"
        if live_name and live_name.casefold() == store_name.casefold():
            return None

    if name_unit_key in by_name_unit or (store_key and store_key in store_keys):
        return None

    # Rule B: only for tenants previously verified against an official directory
    # (have image_source / directory_verified). Never wipe SPA-only cards that
    # were never present in the crawled directory index.
    verified = bool(
        offer.get("directory_verified")
        or offer.get("image_source")
        in {"directory_crawl", "openrice", "yoho_cms", "linkreit", "yoho", "link"}
    )
    mall_has_rows = any(k.startswith(f"{mall_id}||") for k in by_unit)
    if verified and mall_has_rows:
        return "B_closed"

    return None


def append_log(lines: list[str], *, day: date) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"audit_{day.isoformat()}.log"
    stamp = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S%z")
    block = [f"[{stamp}] daily_store_auditor"] + lines + [""]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(block) + "\n")
    return path


def archive_records(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    payload = load_json(ARCHIVE_PATH, {"archived": []})
    if not isinstance(payload, dict):
        payload = {"archived": []}
    archived = payload.get("archived")
    if not isinstance(archived, list):
        archived = []
    archived.extend(records)
    payload["archived"] = archived
    payload["updated_at"] = datetime.now(HK_TZ).isoformat(timespec="seconds")
    write_json(ARCHIVE_PATH, payload)


def audit_malls(
    malls_payload: dict[str, Any],
    directory: dict[str, Any],
    *,
    today: date,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    by_unit = directory.get("by_unit") if isinstance(directory.get("by_unit"), dict) else {}
    by_name_unit = (
        directory.get("by_name_unit") if isinstance(directory.get("by_name_unit"), dict) else {}
    )
    store_keys = {
        norm(row.get("store_key"))
        for row in (directory.get("stores") or [])
        if isinstance(row, dict) and row.get("store_key")
    }

    deleted: list[dict[str, Any]] = []
    log_lines: list[str] = []

    for district in malls_payload.get("districts") or []:
        if not isinstance(district, dict):
            continue
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            mall_name = norm(mall.get("mall_name"))
            mall_id = norm(mall.get("mall_id")) or make_mall_id(mall_name)
            offers = mall.get("store_offers")
            if not isinstance(offers, list):
                continue
            keep: list[Any] = []
            for offer in offers:
                if not isinstance(offer, dict):
                    keep.append(offer)
                    continue
                if offer.get("type") == "fallback":
                    keep.append(offer)
                    continue
                rule = classify_offer(
                    mall_id=mall_id,
                    offer=offer,
                    by_unit=by_unit,
                    by_name_unit=by_name_unit,
                    store_keys=store_keys,
                    today=today,
                )
                if not rule:
                    keep.append(offer)
                    continue
                record = {
                    "deleted_at": datetime.now(HK_TZ).isoformat(timespec="seconds"),
                    "rule": rule,
                    "mall_id": mall_id,
                    "mall_name": mall_name,
                    "store_name": offer.get("store_name"),
                    "floor": offer.get("floor"),
                    "shop_number": offer.get("shop_number"),
                    "store_key": offer.get("store_key"),
                    "offer_title": offer.get("offer_title") or offer.get("title"),
                    "end_date": offer.get("end_date") or offer.get("expiry_date"),
                    "store_image_url": offer.get("store_image_url"),
                    "snapshot": offer,
                }
                deleted.append(record)
                log_lines.append(
                    f"DELETE [{rule}] mall={mall_name} store={offer.get('store_name')} "
                    f"unit={offer.get('shop_number')} key={offer.get('store_key')}"
                )
                if not dry_run:
                    img = local_image_path(offer)
                    if img and img.exists():
                        try:
                            img.unlink()
                            log_lines.append(f"  removed image {img.relative_to(ROOT)}")
                        except OSError as exc:
                            log_lines.append(f"  image remove failed: {exc}")
            if not dry_run:
                mall["store_offers"] = keep

    return deleted, log_lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily store auditor (hard-delete stale offers)")
    parser.add_argument("--malls", type=Path, default=DEFAULT_MALLS)
    parser.add_argument("--directory", type=Path, default=DIRECTORY_CACHE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--inject-relocated-test",
        action="store_true",
        help="Inject a synthetic relocated store into the first mall, then audit (self-test)",
    )
    args = parser.parse_args(argv)

    malls_payload = load_json(args.malls, {})
    directory = load_json(args.directory, {})
    if not isinstance(malls_payload, dict) or not malls_payload.get("districts"):
        print(f"[auditor] missing malls feed: {args.malls}")
        return 1
    if not isinstance(directory, dict):
        directory = {}

    today = today_hk()

    if args.inject_relocated_test:
        # Self-test: plant a ghost tenant at a unit that already belongs to someone else.
        planted = False
        by_unit = directory.get("by_unit") if isinstance(directory.get("by_unit"), dict) else {}
        for district in malls_payload.get("districts") or []:
            for mall in district.get("malls") or []:
                mall_name = norm(mall.get("mall_name"))
                mall_id = norm(mall.get("mall_id")) or make_mall_id(mall_name)
                # Find any live unit for this mall in the directory.
                live_unit = None
                live_name = None
                for key, meta in by_unit.items():
                    if key.startswith(f"{mall_id}||") and isinstance(meta, dict):
                        live_unit = key.split("||", 1)[1]
                        live_name = norm(meta.get("store_name"))
                        break
                if not live_unit:
                    continue
                ghost = {
                    "type": "store",
                    "store_name": "審計測試已搬離店",
                    "floor": "測試樓層",
                    "shop_number": live_unit,  # same unit, different name → Rule A
                    "phone": "0000 0000",
                    "offer_title": "搬離測試優惠（應被刪除）",
                    "details": "synthetic relocated tenant for auditor self-test",
                    "start_date": "2020-01-01",
                    "end_date": "2099-01-01",
                    "status": "active",
                    "lifecycle_status": "active",
                    "mall_id": mall_id,
                    "store_key": f"{mall_id}_test_relocated_ghost",
                    "store_image_url": f"frontend/images/stores/{mall_id}_test_relocated_ghost.jpg",
                }
                # Touch a fake image file so auditor can delete it.
                img_path = STORE_IMG_DIR / f"{mall_id}_test_relocated_ghost.jpg"
                img_path.parent.mkdir(parents=True, exist_ok=True)
                img_path.write_bytes(b"\xff\xd8\xff\xd9")
                offers = mall.setdefault("store_offers", [])
                if isinstance(offers, list):
                    offers.append(ghost)
                planted = True
                print(
                    f"[auditor] injected relocated test store at {mall_name} unit={live_unit} "
                    f"(live tenant was {live_name!r})"
                )
                break
            if planted:
                break
        if not planted:
            print("[auditor] inject failed: no live directory unit found")
            return 1

    deleted, log_lines = audit_malls(
        malls_payload,
        directory,
        today=today,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        if deleted:
            archive_records(deleted)
        log_path = append_log(
            log_lines
            or [f"No deletions (checked against directory stores={directory.get('store_count', 0)})"],
            day=today,
        )
        write_json(args.malls, malls_payload)
        print(f"[auditor] deleted={len(deleted)} log={log_path}")
    else:
        print(f"[auditor] dry-run deleted={len(deleted)}")
        for line in log_lines[:20]:
            print(" ", line)

    # Self-test assertion
    if args.inject_relocated_test:
        rules = {r.get("rule") for r in deleted}
        names = {norm(r.get("store_name")) for r in deleted}
        ok = "A_relocated" in rules and "審計測試已搬離店" in names
        print(f"[auditor] inject-test {'PASS' if ok else 'FAIL'} rules={sorted(rules)}")
        return 0 if ok else 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
