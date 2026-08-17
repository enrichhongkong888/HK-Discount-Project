# -*- coding: utf-8 -*-
"""Diagnostic audit: malls with zero individual store offers + gap causes.

Writes:
  data/cache/empty_store_audit.json
  data/cache/empty_store_audit.md
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from store_authenticity import presence_is_verified  # noqa: E402
from fix_store_locations import VERIFIED_PINS  # noqa: E402

MALLS_JSON = ROOT / "malls.json"
DISCOUNTS_JSON = ROOT / "discounts.json"
CHAIN_JSON = ROOT / "data" / "chain_store_offers.json"
LOCATOR_JSON = ROOT / "data" / "brand_store_locators.json"
CACHE_PINS = ROOT / "data" / "cache" / "directory_verified_pins.json"
OUT_JSON = ROOT / "data" / "cache" / "empty_store_audit.json"
OUT_MD = ROOT / "data" / "cache" / "empty_store_audit.md"


def _load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    malls_payload = _load(MALLS_JSON)
    discounts = _load(DISCOUNTS_JSON)
    chain = _load(CHAIN_JSON) if isinstance(_load(CHAIN_JSON), dict) else {}
    locators = _load(LOCATOR_JSON)
    cache_pins = _load(CACHE_PINS)

    verified_pin_malls = {p.get("mall_name") for p in VERIFIED_PINS}
    locator_malls = {
        str(p.get("mall_hint") or p.get("mall_name") or "").strip()
        for p in (locators.get("pins") or [] if isinstance(locators, dict) else [])
    }
    presence = list(chain.get("presence") or []) if isinstance(chain, dict) else []
    presence_by_mall: dict[str, list[dict]] = {}
    for row in presence:
        mall = str(row.get("mall_name") or "").strip()
        presence_by_mall.setdefault(mall, []).append(row)

    cache_by_mall: dict[str, list[dict]] = {}
    for row in (cache_pins.get("pins") or [] if isinstance(cache_pins, dict) else []):
        mall = str(row.get("mall_name") or "").strip()
        cache_by_mall.setdefault(mall, []).append(row)

    discount_store_by_mall: Counter[str] = Counter()
    for raw in discounts.get("offers") or [] if isinstance(discounts, dict) else []:
        if str(raw.get("offer_type") or "") != "store":
            continue
        discount_store_by_mall[str(raw.get("mall_name") or "").strip()] += 1

    empty_rows: list[dict] = []
    with_store = 0
    total = 0
    for district in malls_payload.get("districts") or []:
        for mall in district.get("malls") or []:
            total += 1
            name = str(mall.get("mall_name") or "").strip()
            store_n = len(mall.get("store_offers") or [])
            mall_n = len(mall.get("mall_offers") or [])
            if store_n > 0:
                with_store += 1
                continue

            rows = presence_by_mall.get(name, [])
            verified_presence = [r for r in rows if presence_is_verified({**r, "verification_status": r.get("verification_status") or "pending"})]
            # presence_is_verified requires verification_status==verified
            verified_ok = [
                r
                for r in rows
                if str(r.get("verification_status") or "") == "verified" and presence_is_verified(r)
            ]
            pending = [r for r in rows if str(r.get("verification_status") or "") != "verified"]
            incomplete_verified = [
                r
                for r in rows
                if str(r.get("verification_status") or "") == "verified" and not presence_is_verified(r)
            ]
            cache_n = len(cache_by_mall.get(name, []))
            reasons: list[str] = []
            if name not in verified_pin_malls:
                reasons.append("no_VERIFIED_PINS")
            if not any(name in h or h in name for h in locator_malls if h):
                reasons.append("no_brand_locator_match")
            if cache_n == 0:
                reasons.append("no_directory_cache_pins")
            if not verified_ok:
                reasons.append("no_verified_presence_passing_six_fields")
            if pending:
                reasons.append(f"pending_presence_rows={len(pending)}")
            if incomplete_verified:
                reasons.append(f"verified_but_incomplete_six_fields={len(incomplete_verified)}")
            if discount_store_by_mall.get(name, 0) == 0:
                reasons.append("no_store_rows_in_discounts_json")
            if mall_n > 0 and store_n == 0:
                reasons.append("mall_only_offers_present")

            empty_rows.append(
                {
                    "district": mall.get("district"),
                    "mall_name": name,
                    "mall_offers": mall_n,
                    "spa_store_offers": store_n,
                    "discounts_store_offers": discount_store_by_mall.get(name, 0),
                    "verified_pins": name in verified_pin_malls,
                    "directory_cache_pins": cache_n,
                    "presence_total": len(rows),
                    "presence_verified_ok": len(verified_ok),
                    "presence_pending": len(pending),
                    "reasons": reasons,
                    "primary_gap": reasons[0] if reasons else "unknown",
                }
            )

    gap_counter = Counter(r["primary_gap"] for r in empty_rows)
    report = {
        "summary": {
            "total_malls": total,
            "malls_with_store_offers": with_store,
            "malls_empty_store_offers": len(empty_rows),
            "primary_gap_breakdown": dict(gap_counter),
        },
        "empty_malls": empty_rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Empty store-offer mall audit",
        "",
        f"- Total malls: **{total}**",
        f"- With store offers: **{with_store}**",
        f"- Empty store offers: **{len(empty_rows)}**",
        "",
        "## Primary gap breakdown",
        "",
    ]
    for k, v in gap_counter.most_common():
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Empty malls", ""])
    for row in empty_rows:
        lines.append(
            f"- **{row['district']} / {row['mall_name']}** — "
            f"mall_offers={row['mall_offers']}; reasons: {', '.join(row['reasons'])}"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
