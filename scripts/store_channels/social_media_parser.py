# -*- coding: utf-8 -*-
"""Parse structured social-media export posts into authentic store offers.

Designed for Instagram / Facebook exports or mall-official structured feeds
(JSON), not for inventing incomplete captions. Every emitted offer must pass
store_authenticity six-field + 3-day lifecycle gates.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from store_authenticity import is_precise_phone, is_precise_shop_number

from .mall_match import build_registry_index, match_mall
from .offer_emit import build_store_offer, filter_authentic

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POSTS_PATH = ROOT / "data" / "social_media_posts.json"
SOURCE_NAME = "social_media_parser"

# Caption patterns commonly used by mall / district community posts.
_PHONE_RE = re.compile(r"(?:電話|Tel\.?|☎|📱)\s*[:：]?\s*(\d{4}\s*-?\s*\d{4})", re.I)
_SHOP_RE = re.compile(
    r"(?:舖|鋪|Shop)\s*(?:No\.?|號)?\s*[:：]?\s*([A-Za-z]?\d+[A-Za-z0-9\-/,，及至]*)",
    re.I,
)
_FLOOR_RE = re.compile(
    r"((?:B|LG|UG|G|L|M)?\d{0,2}\s*(?:樓|\/F|F)|地下|地庫|美食廣場|Food\s*Court)",
    re.I,
)
_DATE_RE = re.compile(
    r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})"
)
_PROMO_HINT = re.compile(r"(週年慶|市集|小店|優惠|折扣|回贈|滿\$|減\$|\%|免費|換購)")


def _parse_date_token(raw: str) -> str | None:
    text = raw.strip().replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    parts = text.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(y, m, d).date().isoformat()
        except ValueError:
            return None
    return None


def extract_fields_from_caption(caption: str) -> dict[str, str]:
    """Best-effort field extraction from a bilingual social caption."""
    text = caption or ""
    out: dict[str, str] = {}
    m_phone = _PHONE_RE.search(text)
    if m_phone:
        out["phone"] = re.sub(r"\s+", " ", m_phone.group(1)).strip()
    m_shop = _SHOP_RE.search(text)
    if m_shop:
        out["shop_number"] = m_shop.group(1).replace("，", ",").strip()
    m_floor = _FLOOR_RE.search(text)
    if m_floor:
        out["floor"] = m_floor.group(1).strip()
    dates = [_parse_date_token(x) for x in _DATE_RE.findall(text)]
    dates = [d for d in dates if d]
    if dates:
        out["start_date"] = dates[0]
        out["expiry_date"] = dates[1] if len(dates) > 1 else dates[0]
    # Store name: first line or 「」 quoted segment.
    quoted = re.search(r"[「『]([^」』]{2,40})[」』]", text)
    if quoted:
        out["store_name"] = quoted.group(1).strip()
    else:
        first = text.strip().splitlines()[0].strip() if text.strip() else ""
        first = re.sub(r"^[\W_]+", "", first)[:40]
        if first and not _PROMO_HINT.search(first):
            out["store_name"] = first
    return out


def _load_posts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[social] fail load {path}: {exc}")
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        return [p for p in (payload.get("posts") or []) if isinstance(p, dict)]
    return []


def posts_from_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect structured post payloads declared on community/social sources."""
    posts: list[dict[str, Any]] = []
    for src in sources:
        if not src.get("enabled"):
            continue
        if str(src.get("channel") or "").strip() not in {"social_media", "social_media_parser"}:
            continue
        feed = src.get("structured_posts_path") or src.get("posts_path")
        if feed:
            posts.extend(_load_posts(ROOT / str(feed)))
        for row in src.get("posts") or []:
            if isinstance(row, dict):
                row = {**row, "source_url": row.get("source_url") or src.get("url")}
                posts.append(row)
    return posts


def parse_post_to_offer(
    post: dict[str, Any],
    registry_malls: list[dict],
) -> dict[str, Any] | None:
    index = build_registry_index(registry_malls)
    caption = str(post.get("caption") or post.get("text") or "")
    extracted = extract_fields_from_caption(caption) if caption else {}

    store_name = str(post.get("store_name") or extracted.get("store_name") or "").strip()
    floor = str(post.get("floor") or extracted.get("floor") or "").strip()
    shop = str(post.get("shop_number") or extracted.get("shop_number") or "").strip()
    phone = str(post.get("phone") or extracted.get("phone") or "").strip()
    title = str(post.get("title") or "").strip()
    details = str(post.get("details") or post.get("offer_text") or caption or "").strip()
    start = str(post.get("start_date") or extracted.get("start_date") or "").strip() or None
    end = str(post.get("expiry_date") or extracted.get("expiry_date") or "").strip() or None
    source_url = str(post.get("source_url") or post.get("permalink") or "").strip()
    mall_hint = str(post.get("mall_hint") or post.get("mall_name") or caption).strip()
    address = str(post.get("address") or "").strip()

    if not title:
        platform = str(post.get("platform") or "社群").strip()
        title = f"{platform}小店優惠：{store_name or '獨立店舖'}"
    if not source_url:
        return None
    if not (store_name and floor and is_precise_shop_number(shop) and is_precise_phone(phone)):
        return None
    if not details or not _PROMO_HINT.search(details):
        # Require promo-like content for social channel (avoid plain location posts).
        if not str(post.get("details") or post.get("offer_text") or "").strip():
            return None

    hit = match_mall(index, mall_hint=mall_hint, address=address or mall_hint)
    if not hit:
        print(f"[social] unmatched mall hint={mall_hint!r} store={store_name}")
        return None

    return build_store_offer(
        mall_name=hit.mall_name,
        district=hit.district,
        store_name=store_name,
        floor=floor,
        shop_number=shop,
        phone=phone,
        title=title,
        details=details[:500],
        source_url=source_url,
        source_name=SOURCE_NAME,
        start_date=start,
        expiry_date=end,
        is_evergreen=bool(post.get("is_evergreen")),
    )


def scrape_social_media_offers(
    registry_malls: list[dict],
    *,
    posts_path: Path | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    default_path = posts_path or DEFAULT_POSTS_PATH
    posts = _load_posts(default_path)
    seen_paths = {default_path.resolve()}
    if sources:
        for src in sources:
            if not src.get("enabled"):
                continue
            if str(src.get("channel") or "").strip() not in {"social_media", "social_media_parser"}:
                continue
            feed = src.get("structured_posts_path") or src.get("posts_path")
            if feed:
                path = (ROOT / str(feed)).resolve()
                if path not in seen_paths:
                    seen_paths.add(path)
                    posts.extend(_load_posts(path))
            for row in src.get("posts") or []:
                if isinstance(row, dict):
                    posts.append({**row, "source_url": row.get("source_url") or src.get("url")})
    offers: list[dict[str, Any]] = []
    for post in posts:
        offer = parse_post_to_offer(post, registry_malls)
        if offer:
            offers.append(offer)
    kept = filter_authentic(offers, label="social")
    print(f"[social] posts={len(posts)} authentic_offers={len(kept)}")
    return kept
