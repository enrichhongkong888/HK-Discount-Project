# -*- coding: utf-8 -*-
"""Run only indie channels (social / food-court / community) + rematerialize."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from expand_store_channels import INDEPENDENT_CACHE, rematerialize  # noqa: E402
from match_store_locators import load_registry_malls  # noqa: E402
from store_channels.community_aggregator import scrape_community_offers  # noqa: E402
from store_channels.food_court_scanner import scrape_food_court_offers  # noqa: E402
from store_channels.social_media_parser import scrape_social_media_offers  # noqa: E402

registry = load_registry_malls()
sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8")).get("sources") or []
social = scrape_social_media_offers(registry, sources=sources)
food = scrape_food_court_offers(registry)
community = scrape_community_offers(registry)
independent = social + food + community
dedup = {}
for row in independent:
    key = (
        str(row.get("mall_name") or ""),
        str(row.get("store_name") or ""),
        str(row.get("title") or ""),
        str(row.get("expiry_date") or ""),
    )
    dedup[key] = row
independent = list(dedup.values())
INDEPENDENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
INDEPENDENT_CACHE.write_text(
    json.dumps({"offers": independent}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"independent total={len(independent)}")
rematerialize(independent)
