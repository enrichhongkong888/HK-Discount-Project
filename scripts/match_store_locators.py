"""Match curated brand store-locator pins onto the 74-mall registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from store_authenticity import VERIFICATION_VERIFIED, presence_is_verified  # noqa: E402

from store_channels.mall_match import build_registry_index, match_mall  # noqa: E402

LOCATOR_PATH = ROOT / "data" / "brand_store_locators.json"
REGISTRY_PATH = ROOT / "data" / "malls-registry.json"


def load_registry_malls() -> list[dict]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(payload.get("malls") or [])


def match_locator_pins(raw_pins: list[dict] | None = None) -> list[dict[str, str]]:
    if raw_pins is None:
        payload = json.loads(LOCATOR_PATH.read_text(encoding="utf-8"))
        raw_pins = list(payload.get("pins") or [])

    index = build_registry_index(load_registry_malls())
    matched: list[dict[str, str]] = []
    for raw in raw_pins:
        hint = str(raw.get("mall_name") or raw.get("mall_hint") or "").strip()
        address = str(raw.get("address") or "").strip()
        hit = match_mall(index, mall_hint=hint, address=address)
        if not hit:
            print(f"[locator] unmatched mall hint={hint!r}")
            continue
        pin = {
            "chain_id": str(raw.get("chain_id") or "").strip(),
            "mall_name": hit.mall_name,
            "district": hit.district,
            "floor": str(raw.get("floor") or "").strip(),
            "shop_number": str(raw.get("shop_number") or "").strip(),
            "phone": str(raw.get("phone") or "").strip(),
            "store_name": str(raw.get("store_name") or "").strip(),
            "verification_status": VERIFICATION_VERIFIED,
            "source": "brand_store_locator",
            "source_url": str(raw.get("source_url") or "").strip(),
        }
        if not pin["chain_id"]:
            continue
        if presence_is_verified(pin):
            matched.append(pin)
        else:
            print(
                f"[locator] reject {pin.get('store_name')}@{pin.get('mall_name')} "
                f"(failed authenticity presence checks)"
            )
    return matched


def main() -> None:
    pins = match_locator_pins()
    print(f"matched_verified_pins={len(pins)}")
    for pin in pins:
        print(
            f"  {pin['chain_id']:16} {pin['mall_name']:16} "
            f"{pin['floor']} / {pin['shop_number']} / {pin['phone']}"
        )


if __name__ == "__main__":
    main()
