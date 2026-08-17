# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from store_authenticity import is_precise_floor, is_precise_phone, is_precise_shop_number

d = json.loads((ROOT / "discounts.json").read_text(encoding="utf-8"))
seen = set()
rows = []
for o in d["offers"]:
    if o.get("offer_type") != "store":
        continue
    mall = o.get("mall_name")
    if mall in seen:
        continue
    floor = str(o.get("floor") or "")
    shop = str(o.get("shop_number") or "")
    phone = str(o.get("phone") or "")
    if "{" in floor or '"' in shop or "\\" in shop:
        continue
    if not (
        is_precise_floor(floor)
        and is_precise_shop_number(shop)
        and is_precise_phone(phone)
        and o.get("source_url")
    ):
        continue
    seen.add(mall)
    rows.append(
        {
            k: o.get(k)
            for k in (
                "mall_name",
                "district",
                "store_name",
                "floor",
                "shop_number",
                "phone",
                "source_url",
            )
        }
    )
    if len(rows) >= 6:
        break
print(json.dumps(rows, ensure_ascii=False, indent=2))
