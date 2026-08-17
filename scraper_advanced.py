"""Strict official-source synchroniser for the HK-Deal mall offer feed.

This module deliberately reuses the project's validated source adapters and
lifecycle rules. It never discovers or imports third-party offers on its own.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from scraper import (
    TARGET_GROUPS,
    DynamicSourceScraper,
    HttpClient,
    Mall,
    Offer,
    ScraperError,
    load_chain_store_offers,
    load_json,
    load_mall_overrides,
    load_sources,
    mall_from_json,
    merge_malls,
    merge_offers,
    offer_from_json,
    write_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HK-Deal 進階官方優惠同步器：只保留進行中及 3 天內預告優惠"
    )
    parser.add_argument("--config", type=Path, default=Path("data/sources.json"))
    parser.add_argument("--targets", default="malls")
    parser.add_argument("--discounts-output", type=Path, default=Path("discounts.json"))
    parser.add_argument("--malls-output", type=Path, default=Path("data/malls-registry.json"))
    parser.add_argument("--mall-overrides", type=Path, default=Path("data/mall_overrides.json"))
    parser.add_argument(
        "--chain-store-offers",
        type=Path,
        default=Path("data/chain_store_offers.json"),
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def active_sources(config_path: Path, targets: str):
    requested = TARGET_GROUPS if targets == "all" else frozenset(targets.split(","))
    invalid = requested - TARGET_GROUPS
    if invalid:
        raise ScraperError(f"未知 target：{', '.join(sorted(invalid))}")
    return [source for source in load_sources(config_path) if source.enabled and source.target in requested]


def sync(args: argparse.Namespace) -> tuple[list[Offer], list[Mall]]:
    sources = active_sources(args.config, args.targets)
    existing_offers = [
        offer for raw in load_json(args.discounts_output).get("offers", [])
        if (offer := offer_from_json(raw))
    ]
    existing_malls = [
        mall for raw in load_json(args.malls_output).get("malls", [])
        if (mall := mall_from_json(raw))
    ]
    fresh_offers: list[Offer] = []
    fresh_malls: list[Mall] = []
    client = HttpClient()

    for source in sources:
        try:
            offers, malls = DynamicSourceScraper(client, source).scrape()
            fresh_offers.extend(offers)
            fresh_malls.extend(malls)
            logging.info("%s：接受 %s 筆已驗證官方優惠", source.name, len(offers))
        except ScraperError as error:
            logging.error("%s 抓取失敗：%s", source.name, error)

    reference_time = datetime.now(timezone.utc).astimezone()
    known_malls = {(mall.district, mall.mall_name) for mall in existing_malls + fresh_malls}
    overrides = load_mall_overrides(args.mall_overrides, known_malls, reference_time)
    chain_offers = load_chain_store_offers(args.chain_store_offers, known_malls, reference_time)
    covered_sources = {
        (offer.district, offer.mall_name, offer.source_url)
        for offer in existing_offers + fresh_offers
        if offer.offer_type == "mall" and offer.is_evergreen
    }
    overrides = [
        offer for offer in overrides
        if (offer.district, offer.mall_name, offer.source_url) not in covered_sources
    ]

    # merge_offers invokes clean_offers: expired offers are removed, distant
    # future offers are withheld, and verified evergreen policies are retained.
    offers = merge_offers(
        existing_offers, fresh_offers + overrides + chain_offers, reference_time
    )
    return offers, merge_malls(existing_malls, fresh_malls)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        offers, malls = sync(args)
        write_outputs(args.discounts_output, args.malls_output, offers, malls)
        logging.info(
            "完成進階同步：%s 筆優惠寫入 %s；%s 間商場寫入 %s",
            len(offers), args.discounts_output, len(malls), args.malls_output,
        )
        return 0
    except ScraperError as error:
        logging.error("%s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
