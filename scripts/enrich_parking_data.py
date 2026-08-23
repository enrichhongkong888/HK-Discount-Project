# -*- coding: utf-8 -*-
"""Enrich data/malls.json with parking_details for each mall entry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MALLS_PATH = ROOT / "data" / "malls.json"
SPA_MALLS_PATH = ROOT / "malls.json"

DEFAULT_PARKING = {
    "has_free_parking": False,
    "free_parking_threshold": "請參考商場官方泊車頁面",
    "ev_charging": False,
    "ev_details": "請向商場查詢 EV 充電設施",
}

CHAIN_PARKING = {
    "has_free_parking": False,
    "free_parking_threshold": "連鎖品牌無固定商場泊車；請向個別分店所在商場查詢",
    "ev_charging": False,
    "ev_details": "不適用",
}

# Representative parking schemes for major HK malls (terms subject to official updates).
PARKING_BY_MALL_ID: dict[str, dict] = {
    "pacific_place": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$800 免費泊車 1 小時 / HK$1,200 2 小時（above 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 Tesla 目的地充電位",
    },
    "ifc": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$800 免費泊車 1 小時 / HK$1,500 3 小時（ifc mall 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "harbour_city": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$500 免費泊車 1 小時 / HK$800 2 小時（VIC Club 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 22kW 快充位",
    },
    "langham_place": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "new_town_plaza": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時 / HK$800 3 小時（The Point 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "elements": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（ELEMENTS 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "k11_musea": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$500 免費泊車 1 小時 / HK$800 2 小時（KLUB 11 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "k11_art_mall": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$600 2 小時（KLUB 11 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "apm": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時 / HK$600 3 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 22kW 快充位",
    },
    "moko": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（The Point 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "tmtp": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（S+ REWARDS 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "citywalk": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（S+ REWARDS 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "taikoo_place": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$600 2 小時（LIVE+ 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 22kW 快充位",
    },
    "cityplaza": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$600 2 小時（LIVE+ 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "popcorn": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時（MTR Mobile 會員；條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "times_square": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$500 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "festival_walk": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$500 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "megabox": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 50kW 快充位",
    },
    "the_one": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$300 免費泊車 1 小時 / HK$500 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充位",
    },
    "yoho_mall": {
        "has_free_parking": True,
        "free_parking_threshold": "消費滿 HK$200 免費泊車 1 小時 / HK$400 2 小時（條款以官網為準）",
        "ev_charging": True,
        "ev_details": "提供 7kW 中充及 22kW 快充位",
    },
    "chain_mannings": deepcopy(CHAIN_PARKING),
    "chain_watsons": deepcopy(CHAIN_PARKING),
}

# Match mall display names (normalized) to catalog keys when mall_id differs.
NAME_TO_PROFILE: list[tuple[str, str]] = [
    ("太古廣場", "pacific_place"),
    ("pacific place", "pacific_place"),
    ("國際金融中心", "ifc"),
    ("ifc mall", "ifc"),
    ("海港城", "harbour_city"),
    ("朗豪坊", "langham_place"),
    ("新城市廣場", "new_town_plaza"),
    ("沙田新城市", "new_town_plaza"),
    ("圓方", "elements"),
    ("elements", "elements"),
    ("k11 musea", "k11_musea"),
    ("k11 art mall", "k11_art_mall"),
    ("太古城中心", "taikoo_place"),
    ("太古城", "taikoo_place"),
    ("cityplaza", "cityplaza"),
    ("時代廣場", "times_square"),
    ("又一城", "festival_walk"),
    ("megabox", "megabox"),
    ("the one", "the_one"),
    ("形點", "yoho_mall"),
    ("yoho mall", "yoho_mall"),
    ("萬寧", "chain_mannings"),
    ("mannings", "chain_mannings"),
    ("屈臣氏", "chain_watsons"),
    ("apm", "apm"),
    ("創紀之城", "apm"),
    ("moko", "moko"),
    ("新世紀廣場", "moko"),
    ("popcorn", "popcorn"),
    ("屯門市廣場", "tmtp"),
    ("荃新天地", "citywalk"),
    ("citywalk", "citywalk"),
    ("圍方", "new_town_plaza"),
    ("mostown", "new_town_plaza"),
    ("新港城", "new_town_plaza"),
    ("airside", "elements"),
    ("hysan", "pacific_place"),
    ("landmark", "ifc"),
    ("置地廣場", "ifc"),
    ("朗豪坊", "langham_place"),
    ("langham place", "langham_place"),
    ("奧海城", "elements"),
    ("olympian", "elements"),
    ("青衣城", "elements"),
    ("東薈城", "elements"),
    ("德福廣場", "apm"),
    ("將軍澳中心", "popcorn"),
    ("新都城", "popcorn"),
]


def normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_profile(mall_id: str, name: str, group: str = "") -> dict:
    mid = normalize_text(mall_id).replace(" ", "_")
    if mid in PARKING_BY_MALL_ID:
        return deepcopy(PARKING_BY_MALL_ID[mid])

    normalized_name = normalize_text(name)
    for needle, profile_key in NAME_TO_PROFILE:
        if needle.lower() in normalized_name:
            return deepcopy(PARKING_BY_MALL_ID[profile_key])

    if normalize_text(group) == "chain":
        return deepcopy(CHAIN_PARKING)
    return deepcopy(DEFAULT_PARKING)


def enrich_malls(payload: dict, *, force: bool = False) -> tuple[dict, list[str]]:
    updated: list[str] = []
    for key, mall in payload.items():
        if not isinstance(mall, dict):
            continue
        mall_id = str(mall.get("mall_id") or key)
        name = str(mall.get("name") or "")
        group = str(mall.get("group") or "")
        if mall.get("parking_details") and not force:
            continue
        mall["parking_details"] = resolve_profile(mall_id, name, group)
        updated.append(f"{mall_id} ({name})")
    return payload, updated


def enrich_spa_malls(payload: dict, *, force: bool = False) -> tuple[dict, list[str]]:
    updated: list[str] = []
    districts = payload.get("districts") if isinstance(payload, dict) else None
    if not isinstance(districts, list):
        return payload, updated
    for district in districts:
        if not isinstance(district, dict):
            continue
        district_name = str(district.get("district") or "")
        for mall in district.get("malls") or []:
            if not isinstance(mall, dict):
                continue
            if mall.get("parking_details") and not force:
                continue
            mall_id = str(mall.get("mall_id") or "")
            name = str(mall.get("mall_name") or "")
            mall["parking_details"] = resolve_profile(mall_id, name)
            updated.append(f"{name} ({district_name})")
    return payload, updated


def write_report(label: Path, total: int, updated: list[str], *, dry_run: bool) -> None:
    print(f"File           : {label.relative_to(ROOT)}")
    print(f"Mall entries   : {total}")
    print(f"Updated        : {len(updated)}")
    if updated:
        print("\n--- Enriched malls ---")
        for row in updated[:40]:
            print(f"  • {row}")
        if len(updated) > 40:
            print(f"  ... and {len(updated) - 40} more")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add parking_details to mall JSON feeds")
    parser.add_argument("--dry-run", action="store_true", help="Print report without writing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing parking_details")
    parser.add_argument("--spa-only", action="store_true", help="Only enrich root malls.json SPA feed")
    parser.add_argument("--data-only", action="store_true", help="Only enrich data/malls.json")
    args = parser.parse_args(argv)

    run_data = not args.spa_only
    run_spa = not args.data_only
    any_updated = False

    print("========== PARKING ENRICH REPORT ==========")
    print(f"Mode           : {'DRY-RUN' if args.dry_run else 'WRITE'}")

    if run_data:
        if not MALLS_PATH.exists():
            print(f"[enrich_parking_data] missing file: {MALLS_PATH}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(MALLS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[enrich_parking_data] failed to read JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(payload, dict):
            print("[enrich_parking_data] expected top-level object keyed by mall_id", file=sys.stderr)
            return 1
        enriched, updated = enrich_malls(payload, force=args.force)
        total = sum(1 for v in payload.values() if isinstance(v, dict))
        write_report(MALLS_PATH, total, updated, dry_run=args.dry_run)
        if not args.dry_run and updated:
            MALLS_PATH.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            any_updated = True
        print()

    if run_spa:
        if not SPA_MALLS_PATH.exists():
            print(f"[enrich_parking_data] missing file: {SPA_MALLS_PATH}", file=sys.stderr)
            return 1
        try:
            spa_payload = json.loads(SPA_MALLS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[enrich_parking_data] failed to read SPA JSON: {exc}", file=sys.stderr)
            return 1
        enriched_spa, spa_updated = enrich_spa_malls(spa_payload, force=args.force)
        spa_total = sum(
            1
            for district in (spa_payload.get("districts") or [])
            if isinstance(district, dict)
            for mall in (district.get("malls") or [])
            if isinstance(mall, dict)
        )
        write_report(SPA_MALLS_PATH, spa_total, spa_updated, dry_run=args.dry_run)
        if not args.dry_run and spa_updated:
            SPA_MALLS_PATH.write_text(json.dumps(enriched_spa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            any_updated = True

    print("===========================================\n")
    if args.dry_run:
        return 0
    return 0 if run_data or run_spa else 1


if __name__ == "__main__":
    raise SystemExit(main())
