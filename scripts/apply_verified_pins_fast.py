# -*- coding: utf-8 -*-
"""Apply VERIFIED_PINS + curated locators onto cached directory pins, then rematerialize."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from expand_store_channels import (  # noqa: E402
    CACHE_PATH,
    apply_presence,
    merge_verified_pins,
    rematerialize,
)
from fix_store_locations import VERIFIED_PINS  # noqa: E402
from match_store_locators import match_locator_pins  # noqa: E402
from store_authenticity import VERIFICATION_VERIFIED  # noqa: E402

cached = []
if CACHE_PATH.exists():
    cached = list(json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("pins") or [])

manual = [
    {**pin, "verification_status": VERIFICATION_VERIFIED, "source": "verified_pins"}
    for pin in VERIFIED_PINS
]
locator = match_locator_pins()
verified = merge_verified_pins([manual, locator, cached])
CACHE_PATH.write_text(
    json.dumps({"pins": verified}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
verified_n, pending_n = apply_presence(verified)
print(f"presence verified={verified_n} pending={pending_n} unique_pins={len(verified)}")
rematerialize([])
