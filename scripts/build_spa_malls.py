"""Build the SPA malls.json feed from scraped discounts without overwriting its schema."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for path in (ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from store_authenticity import (  # noqa: E402
    is_authentic_store_payload,
    is_within_lifecycle_window,
)
from offer_tagging import (  # noqa: E402
    STATUS_ACTIVE,
    STATUS_UPCOMING,
    apply_offer_tags,
    classify_lifecycle_status,
)

COORDS_PATH = ROOT / "data" / "mall_coordinates.json"


def load_mall_coordinates(path: Path = COORDS_PATH) -> dict[str, dict[str, float]]:
    payload = load_json(path)
    raw = payload.get("coordinates") if isinstance(payload, dict) else {}
    out: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for name, coords in raw.items():
        if not isinstance(coords, dict):
            continue
        try:
            lat = float(coords["lat"])
            lng = float(coords["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        out[str(name)] = {"lat": lat, "lng": lng}
    return out


def attach_geo(mall: dict[str, Any], coords_by_name: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Attach WGS84 lat/lng geo tags used by SPA map links."""
    name = str(mall.get("mall_name") or "")
    hit = coords_by_name.get(name)
    if hit:
        mall["lat"] = hit["lat"]
        mall["lng"] = hit["lng"]
        mall["geo_tags"] = [f"lat:{hit['lat']:.5f}", f"lng:{hit['lng']:.5f}"]
    else:
        mall.pop("lat", None)
        mall.pop("lng", None)
        mall["geo_tags"] = []
    return mall


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def is_retained(offer: dict[str, Any], today: date, now: datetime) -> bool:
    """Keep in-progress / within-3-day preview offers; never keep expired rows."""
    if not is_within_lifecycle_window(
        offer.get("start_date"),
        offer.get("expiry_date") or offer.get("end_date"),
        today=today,
    ):
        return False
    if offer.get("is_daily_special"):
        try:
            created_at = datetime.fromisoformat(str(offer["created_at"]))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return now <= created_at + timedelta(days=1)
        except (KeyError, ValueError):
            return False
    return True


def classify_offer_category(offer: dict[str, Any]) -> tuple[str, str]:
    if offer.get("offer_category") and offer.get("offer_category_label"):
        return str(offer["offer_category"]), str(offer["offer_category_label"])
    if offer.get("offer_type") == "store" or offer.get("type") == "store":
        return "store_offer", "個別商店優惠"
    if offer.get("is_evergreen"):
        return "evergreen_benefit", "長青福利"
    return "official_event", "官方活動"


def offer_card(offer: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    category_id, category_label = classify_offer_category(offer)
    tagged = apply_offer_tags(
        {
            **offer,
            "title": offer.get("title") or offer.get("offer_title"),
            "details": offer.get("details") or offer.get("discount_info"),
        }
    )
    status = classify_lifecycle_status(tagged, today=today)
    return {
        "type": offer.get("type") or offer.get("offer_type", "mall"),
        "offer_title": offer["title"],
        "details": offer.get("details") or offer.get("discount_info"),
        "start_date": offer.get("start_date") or offer["created_date"],
        "end_date": offer["expiry_date"],
        "source_url": offer.get("source_url"),
        "is_daily_special": bool(offer.get("is_daily_special")),
        "is_evergreen": bool(offer.get("is_evergreen")),
        "status": status,
        "lifecycle_status": status,
        "offer_category": category_id,
        "offer_category_label": category_label,
        "vertical_category": tagged.get("vertical_category"),
        "vertical_category_label": tagged.get("vertical_category_label"),
        "tags": list(tagged.get("tags") or []),
        "tag_labels": list(tagged.get("tag_labels") or []),
    }


def fallback_offer_card(mall: dict[str, Any]) -> dict[str, Any]:
    """Provide a truthful UI state when no verified offer is available."""
    return {
        "type": "fallback",
        "offer_title": "官方優惠資料待確認",
        "details": "我們正在核實此商場的官方優惠資料。你可直接前往商場官網查看最新公告。",
        "source_url": mall.get("mall_url"),
        "is_daily_special": False,
        "is_evergreen": False,
        "status": "fallback",
        "lifecycle_status": "fallback",
        "offer_category": "fallback",
        "offer_category_label": "資料待確認",
        "vertical_category": "Other",
        "vertical_category_label": "其他",
        "tags": [],
        "tag_labels": [],
    }


def _normalize_sub_offers(raw: Any) -> list[dict[str, str]]:
    """SPA contract: always a list; each item has time_slot / title / detail."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("offer_title") or "").strip()
        detail = str(
            item.get("detail") or item.get("details") or item.get("discount_info") or ""
        ).strip()
        time_slot = str(item.get("time_slot") or "").strip()
        if not time_slot:
            start = str(item.get("start_date") or "").strip()
            end = str(item.get("expiry_date") or item.get("end_date") or "").strip()
            if start and end and end != start:
                time_slot = f"{start} 至 {end}"
            elif start:
                time_slot = f"{start} 起"
        out.append(
            {
                "time_slot": time_slot,
                "title": title,
                "detail": detail,
            }
        )
    return out


def store_offer_card(offer: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    sub_offers = _normalize_sub_offers(offer.get("sub_offers"))
    merchant_type = str(offer.get("merchant_type") or "").strip()
    card = {
        **offer_card(offer, today=today),
        "store_name": offer["store_name"],
        "floor": str(offer.get("floor") or "").strip(),
        "shop_number": str(offer.get("shop_number") or "").strip(),
        "phone": offer["phone"],
        "sub_offers": sub_offers,
        "consolidated_offer_count": int(
            offer.get("consolidated_offer_count") or (1 + len(sub_offers))
        ),
        "merchant_type": merchant_type or None,
    }
    if offer.get("quota_fill"):
        card["quota_fill"] = True
    pattern_id = str(offer.get("pattern_id") or "").strip()
    if pattern_id:
        card["pattern_id"] = pattern_id
    image_url = str(
        offer.get("store_image_url")
        or offer.get("facade_image_url")
        or offer.get("image_url")
        or ""
    ).strip()
    if image_url:
        card["store_image_url"] = image_url
        card["facade_image_url"] = image_url
        card["image_url"] = image_url
    branch_id = str(offer.get("branch_id") or "").strip()
    if branch_id:
        card["branch_id"] = branch_id
    relocation = str(offer.get("relocation_status") or "").strip()
    if relocation:
        card["relocation_status"] = relocation
    return card


def consolidate_spa_store_offers(
    cards: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """One SPA card per shop: merge same store/floor/shop across active + upcoming.

    Extra promos fold into ``sub_offers``. Primary prefers an active row when both
    statuses exist so the store appears once on screen.
    """
    del today  # reserved for future date-aware ranking
    passthrough: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for card in cards:
        if not isinstance(card, dict):
            continue
        row = dict(card)
        status = str(row.get("status") or row.get("lifecycle_status") or "").strip()
        store = str(row.get("store_name") or "").strip()
        floor = str(row.get("floor") or "").strip()
        shop = str(row.get("shop_number") or "").strip()
        if status not in {STATUS_ACTIVE, STATUS_UPCOMING} or not (store and floor and shop):
            row["sub_offers"] = _normalize_sub_offers(row.get("sub_offers"))
            row.setdefault("consolidated_offer_count", 1 + len(row["sub_offers"]))
            passthrough.append(row)
            continue
        groups.setdefault((store, floor, shop), []).append(row)

    consolidated: list[dict[str, Any]] = []
    for rows in groups.values():
        active_rows = [
            r
            for r in rows
            if str(r.get("status") or r.get("lifecycle_status") or "") == STATUS_ACTIVE
        ]
        upcoming_rows = [
            r
            for r in rows
            if str(r.get("status") or r.get("lifecycle_status") or "") == STATUS_UPCOMING
        ]
        primary_status = STATUS_ACTIVE if active_rows else STATUS_UPCOMING
        pool = active_rows if active_rows else upcoming_rows
        pool.sort(
            key=lambda r: (
                str(r.get("start_date") or ""),
                str(r.get("offer_title") or r.get("title") or ""),
            )
        )
        primary_row = pool[0]
        primary = dict(primary_row)
        extras = [r for r in rows if r is not primary_row]
        def _slot_for(extra: dict[str, Any]) -> str:
            start = str(extra.get("start_date") or "").strip()
            end = str(extra.get("end_date") or extra.get("expiry_date") or "").strip()
            if start and end and end != start:
                slot = f"{start} 至 {end}"
            elif start:
                slot = f"{start} 起"
            else:
                slot = "時段待確認"
            st = str(extra.get("status") or extra.get("lifecycle_status") or "").strip()
            if st == STATUS_UPCOMING and primary_status == STATUS_ACTIVE:
                return f"即將開始｜{slot}"
            if st == STATUS_ACTIVE and primary_status == STATUS_UPCOMING:
                return f"進行中｜{slot}"
            return slot

        subs: list[dict[str, str]] = _normalize_sub_offers(primary.get("sub_offers"))
        for extra in extras:
            # Skip exact duplicate of primary body; keep its nested subs.
            same_body = (
                str(extra.get("start_date") or "") == str(primary.get("start_date") or "")
                and str(extra.get("offer_title") or extra.get("title") or "")
                == str(primary.get("offer_title") or primary.get("title") or "")
                and str(extra.get("status") or extra.get("lifecycle_status") or "")
                == str(primary.get("status") or primary.get("lifecycle_status") or "")
            )
            if not same_body:
                subs.append(
                    {
                        "time_slot": _slot_for(extra),
                        "title": str(
                            extra.get("offer_title") or extra.get("title") or ""
                        ).strip(),
                        "detail": str(extra.get("details") or "").strip(),
                    }
                )
            for nested in _normalize_sub_offers(extra.get("sub_offers")):
                nested_slot = str(nested.get("time_slot") or "").strip()
                st = str(extra.get("status") or extra.get("lifecycle_status") or "")
                if (
                    st == STATUS_UPCOMING
                    and primary_status == STATUS_ACTIVE
                    and nested_slot
                    and not nested_slot.startswith("即將開始")
                ):
                    nested = {**nested, "time_slot": f"即將開始｜{nested_slot}"}
                subs.append(nested)

        seen: set[tuple[str, str, str]] = set()
        unique_subs: list[dict[str, str]] = []
        primary_title = str(primary.get("offer_title") or primary.get("title") or "").strip()
        primary_start = str(primary.get("start_date") or "").strip()
        for sub in subs:
            title = str(sub.get("title") or "").strip()
            slot = str(sub.get("time_slot") or "").strip()
            detail = str(sub.get("detail") or "").strip()
            if title == primary_title and primary_start and primary_start in slot:
                continue
            sig = (slot, title, detail)
            if (not title and not slot) or sig in seen:
                continue
            seen.add(sig)
            unique_subs.append({"time_slot": slot, "title": title, "detail": detail})

        primary["sub_offers"] = unique_subs
        primary["consolidated_offer_count"] = 1 + len(unique_subs)
        primary["status"] = primary_status
        primary["lifecycle_status"] = primary_status
        primary["has_active"] = bool(active_rows) or primary_status == STATUS_ACTIVE
        primary["has_upcoming"] = bool(upcoming_rows) or primary_status == STATUS_UPCOMING
        # Prefer quota-balanced stamp so SPA cards keep the 70:30 deck labels.
        for r in rows:
            mt = str(r.get("merchant_type") or "").strip()
            if mt and r.get("quota_balanced"):
                primary["merchant_type"] = mt
                primary["quota_balanced"] = True
                break
        else:
            for r in rows:
                mt = str(r.get("merchant_type") or "").strip()
                if mt and not r.get("quota_fill"):
                    primary["merchant_type"] = mt
                    break
            else:
                for r in rows:
                    mt = str(r.get("merchant_type") or "").strip()
                    if mt:
                        primary["merchant_type"] = mt
                        break
        if not primary.get("store_image_url") and not primary.get("facade_image_url") and not primary.get("image_url"):
            for r in rows:
                img = str(
                    r.get("store_image_url")
                    or r.get("facade_image_url")
                    or r.get("image_url")
                    or ""
                ).strip()
                if img:
                    primary["store_image_url"] = img
                    primary["facade_image_url"] = img
                    primary["image_url"] = img
                    break
        else:
            img = str(
                primary.get("store_image_url")
                or primary.get("facade_image_url")
                or primary.get("image_url")
                or ""
            ).strip()
            if img:
                primary["store_image_url"] = img
                primary["facade_image_url"] = img
                primary["image_url"] = img
        if not primary.get("branch_id"):
            for r in rows:
                bid = str(r.get("branch_id") or "").strip()
                if bid:
                    primary["branch_id"] = bid
                    break
        consolidated.append(primary)

    return passthrough + consolidated


def attach_upcoming_bucket(mall: dict[str, Any]) -> dict[str, Any]:
    """Populate upcoming/active buckets and consolidated offer totals."""
    all_cards = list(mall.get("mall_offers") or []) + list(mall.get("store_offers") or [])

    def _is_upcoming_card(card: dict[str, Any]) -> bool:
        if card.get("type") == "fallback":
            return False
        if card.get("has_upcoming"):
            return True
        return (card.get("status") or card.get("lifecycle_status")) == STATUS_UPCOMING

    def _is_active_card(card: dict[str, Any]) -> bool:
        if card.get("type") == "fallback":
            return False
        if card.get("has_active"):
            return True
        return (card.get("status") or card.get("lifecycle_status")) == STATUS_ACTIVE

    upcoming = [card for card in all_cards if _is_upcoming_card(card)]
    active = [card for card in all_cards if _is_active_card(card)]
    mall["upcoming_offers"] = upcoming
    mall["upcoming_count"] = len(upcoming)
    mall["upcoming_offer_total"] = sum(
        int(card.get("consolidated_offer_count") or (1 + len(card.get("sub_offers") or [])))
        for card in upcoming
    )
    mall["active_count"] = len(active)
    mall["active_offer_total"] = sum(
        int(card.get("consolidated_offer_count") or (1 + len(card.get("sub_offers") or [])))
        for card in active
    )
    return mall



def mall_key(district: str, mall_name: str) -> tuple[str, str]:
    return district, mall_name


def main() -> int:
    parser = argparse.ArgumentParser(description="將 discounts.json 建構成 18 區 SPA 的 malls.json")
    parser.add_argument("--discounts", type=Path, default=Path("discounts.json"))
    parser.add_argument("--registry", type=Path, default=Path("data/malls-registry.json"))
    parser.add_argument("--output", type=Path, default=Path("malls.json"))
    args = parser.parse_args()

    today = date.today()
    now = datetime.now(timezone.utc).astimezone()
    current = load_json(args.output)
    registry = load_json(args.registry)
    discounts = load_json(args.discounts).get("offers", [])
    coords_by_name = load_mall_coordinates()

    malls: dict[tuple[str, str], dict[str, Any]] = {}
    # The registry is authoritative. Legacy mixed `stores` data is deliberately not
    # carried forward because it lacks the mandatory store-offer fields.
    for district_data in current.get("districts", []):
        district = district_data.get("district")
        for mall in district_data.get("malls", []):
            key = mall_key(district, mall.get("mall_name", ""))
            malls[key] = {
                **{field: value for field, value in mall.items() if field != "stores"},
                "mall_offers": [],
                "store_offers": [],
            }

    # Registry is the authoritative source for mall contacts/address after each scrape.
    for mall in registry.get("malls", []):
        key = mall_key(mall["district"], mall["mall_name"])
        malls[key] = {
            **{field: value for field, value in malls.get(key, {}).items() if field != "stores"},
            **mall,
            "mall_offers": [],
            "store_offers": [],
        }

    for offer in discounts:
        if offer.get("category") != "商場優惠" or not is_retained(offer, today, now):
            continue
        district, mall_name = offer.get("district"), offer.get("mall_name")
        if not district or not mall_name:
            continue
        key = mall_key(district, mall_name)
        mall = malls.setdefault(key, {
            "mall_name": mall_name, "district": district, "address": "請向商場查詢",
            "mall_offers": [], "store_offers": [],
        })
        if offer.get("offer_type", "mall") == "store":
            if not is_authentic_store_payload(offer):
                continue
            mall["store_offers"].append(store_offer_card(offer, today=today))
        else:
            mall["mall_offers"].append(offer_card(offer, today=today))

    missing_geo = 0
    upcoming_covered = 0
    for mall in malls.values():
        attach_geo(mall, coords_by_name)
        if mall.get("lat") is None or mall.get("lng") is None:
            missing_geo += 1
        if not mall["mall_offers"] and not mall["store_offers"]:
            mall["mall_offers"].append(fallback_offer_card(mall))
        mall["store_offers"] = consolidate_spa_store_offers(
            mall["store_offers"], today=today
        )
        attach_upcoming_bucket(mall)
        if int(mall.get("upcoming_count") or 0) > 0:
            upcoming_covered += 1

    grouped: dict[str, list[dict[str, Any]]] = {}
    for (district, _), mall in sorted(malls.items()):
        grouped.setdefault(district, []).append(mall)

    payload = {
        "updated_at": now.isoformat(timespec="seconds"),
        "lifecycle_preview_days": 3,
        "districts": [{"district": district, "malls": mall_list} for district, mall_list in grouped.items()],
    }
    try:
        from check_store_status import attach_images_from_cache  # noqa: WPS433

        stamped = attach_images_from_cache(payload)
        if stamped:
            print(f"Attached store images from cache: {stamped}")
    except Exception as exc:  # noqa: BLE001
        print(f"[build_spa] store image attach skipped: {exc}")

    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {sum(len(item['malls']) for item in payload['districts'])} malls to {args.output} "
        f"(geo_tagged={len(malls) - missing_geo}/{len(malls)}, "
        f"upcoming_covered={upcoming_covered}/{len(malls)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
