# -*- coding: utf-8 -*-
"""Site-wide JSON URL health check + auto-repair.

Scans JSON under data/ (skips data/cache by default) and root malls.json.
Checks http(s) fields whose keys contain url/link/affiliate_url/official_url,
replaces dead links with safe platform/mall fallbacks, writes JSON back, and
prints a console report.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OFFICIAL_HUBS_PATH = DATA / "mall_official_offers.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 5.0
SOFT_OK = {200, 201, 204, 301, 302, 303, 307, 308, 401, 403, 405, 429}
DEAD_STATUS = {404, 410, 500, 502, 503, 504}
SOFT_404_MARKERS = (
    "/errorpage",
    "errorpage=",
    "/404",
    "/404/",
    "404.html",
    "not-found",
    "notfound",
    "page-not-found",
    "pagenotfound",
)
SKIP_KEY_PARTS = ("image", "photo", "facade", "logo", "icon", "avatar", "thumbnail", "img", "lat", "lng")
URL_KEY_HINTS = ("url", "link", "affiliate_url", "official_url")

PLATFORM_HOME = {
    "kkday": "https://www.kkday.com/zh-hk",
    "klook": "https://www.klook.com/zh-HK/",
    "openrice": "https://www.openrice.com/zh/hongkong",
}


def load_hubs() -> dict[str, dict[str, str]]:
    if not OFFICIAL_HUBS_PATH.exists():
        return {}
    try:
        raw = json.loads(OFFICIAL_HUBS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    hubs = raw.get("hubs") if isinstance(raw, dict) else {}
    return hubs if isinstance(hubs, dict) else {}


def is_url_field(key: str) -> bool:
    k = str(key or "").lower()
    if any(part in k for part in SKIP_KEY_PARTS):
        return False
    return any(hint in k for hint in URL_KEY_HINTS)


def looks_like_url(value: Any) -> bool:
    text = str(value or "").strip()
    return text.startswith(("http://", "https://"))


def soft_404(final_url: str) -> bool:
    lowered = str(final_url or "").lower()
    return any(marker in lowered for marker in SOFT_404_MARKERS)


def platform_of_url(url: str, platform_hint: str = "") -> str:
    hint = str(platform_hint or "").lower()
    host = (urlparse(url).netloc or "").lower()
    if "kkday" in hint or "kkday.com" in host:
        return "kkday"
    if "klook" in hint or "klook.com" in host:
        return "klook"
    if "openrice" in hint or "openrice.com" in host:
        return "openrice"
    if "官網" in hint or hint == "official":
        return "official"
    return ""


def fallback_url(
    url: str,
    *,
    platform_hint: str = "",
    place_name: str = "",
    hubs: dict[str, dict[str, str]] | None = None,
) -> str:
    hubs = hubs or {}
    place = str(place_name or "").strip()
    platform = platform_of_url(url, platform_hint)
    q = quote(place or "Hong Kong", safe="")

    if platform == "kkday":
        return f"https://www.kkday.com/zh-hk/product/productlist?keyword={q}" if place else PLATFORM_HOME["kkday"]
    if platform == "klook":
        return f"https://www.klook.com/zh-HK/search/?query={q}" if place else PLATFORM_HOME["klook"]
    if platform == "openrice":
        return (
            f"https://www.openrice.com/zh/hongkong/restaurants?where={q}"
            if place
            else PLATFORM_HOME["openrice"]
        )

    hub = hubs.get(place) if place else None
    if isinstance(hub, dict):
        if hub.get("happenings"):
            return str(hub["happenings"])
        if hub.get("home"):
            return str(hub["home"])

    # Domain-specific official hubs
    host = (urlparse(url).netloc or "").lower()
    if "pacificplace.com.hk" in host:
        return "https://www.pacificplace.com.hk/zh-hk/entertainment/happenings"
    if "elementshk.com" in host:
        return "https://www.elementshk.com/tch/whats-on"
    if "the-one.com.hk" in host:
        return "https://www.the-one.com.hk/tc/whats-on"
    if "yohomall.com" in host or "yohomall.hk" in host:
        return "https://www.yohomall.com/tc/whats-on"
    if "ifcmall.com.hk" in host:
        return "https://www.ifcmall.com.hk/tc/whats-happening"
    if "newtownplaza.com.hk" in host:
        return "https://www.newtownplaza.com.hk/happenings"
    if "facebook.com" in host or "fb.com" in host:
        if place and isinstance(hubs.get(place), dict) and hubs[place].get("happenings"):
            return str(hubs[place]["happenings"])
        if place:
            return f"https://www.openrice.com/zh/hongkong/restaurants?where={q}"
        return "https://www.openrice.com/zh/hongkong"

    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        pass
    return PLATFORM_HOME["klook"]


def check_url(url: str) -> tuple[bool, str, int | None]:
    """Return (ok, note, status). Each call uses its own client (thread-safe)."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}
    status: int | None = None
    try:
        with httpx.Client(follow_redirects=True, timeout=TIMEOUT, headers=headers) as client:
            try:
                response = client.head(url)
                status = int(response.status_code)
                final = str(response.url)
                if status in DEAD_STATUS or soft_404(final):
                    return False, f"head:{status}:soft404={soft_404(final)}", status
                if status in SOFT_OK or 200 <= status < 400:
                    return True, f"head:{status}", status
            except Exception:
                pass

            response = client.get(url)
            status = int(response.status_code)
            final = str(response.url)
            if status in DEAD_STATUS or soft_404(final):
                return False, f"get:{status}:soft404={soft_404(final)}", status
            if status in SOFT_OK or 200 <= status < 400:
                return True, f"get:{status}", status
            return False, f"get:{status}", status
    except Exception as exc:
        return False, f"error:{type(exc).__name__}", status


def collect_json_files(*, include_cache: bool) -> list[Path]:
    files: list[Path] = []
    if (ROOT / "malls.json").exists():
        files.append(ROOT / "malls.json")
    if DATA.exists():
        for path in sorted(DATA.rglob("*.json")):
            if not include_cache and "cache" in path.parts:
                continue
            # skip huge binary-ish / schema samples still ok as json
            if path.name.startswith("_") and path.parent.name == "cache":
                continue
            files.append(path)
    # de-dupe preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def walk_collect(
    node: Any,
    *,
    path: str,
    place_name: str,
    platform_hint: str,
    found: list[dict[str, Any]],
) -> None:
    if isinstance(node, dict):
        place = str(
            node.get("mall_name")
            or node.get("name")
            or node.get("place_name")
            or node.get("hotel_name")
            or place_name
            or ""
        )
        platform = str(node.get("platform") or node.get("source_type") or platform_hint or "")
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            if is_url_field(str(key)) and looks_like_url(value):
                found.append(
                    {
                        "path": child_path,
                        "key": str(key),
                        "url": str(value).strip(),
                        "place_name": place,
                        "platform_hint": platform,
                        "holder": node,
                    }
                )
            else:
                walk_collect(
                    value,
                    path=child_path,
                    place_name=place,
                    platform_hint=platform,
                    found=found,
                )
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            walk_collect(
                item,
                path=f"{path}[{idx}]",
                place_name=place_name,
                platform_hint=platform_hint,
                found=found,
            )


def apply_fixes(
    payload: Any,
    *,
    dead_map: dict[str, str],
    hubs: dict[str, dict[str, str]],
) -> tuple[Any, list[dict[str, str]]]:
    """Replace dead URLs in-place; return (payload, fix_rows)."""
    found: list[dict[str, Any]] = []
    walk_collect(payload, path="$", place_name="", platform_hint="", found=found)
    fixes: list[dict[str, str]] = []
    for item in found:
        url = item["url"]
        if url not in dead_map:
            continue
        replacement = dead_map[url]
        if replacement == url:
            continue
        holder = item["holder"]
        key = item["key"]
        if holder.get(key) == url:
            holder[key] = replacement
            fixes.append(
                {
                    "path": item["path"],
                    "old": url,
                    "new": replacement,
                    "place": item.get("place_name") or "",
                }
            )
    return payload, fixes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check & repair URLs across project JSON files")
    parser.add_argument("--include-cache", action="store_true", help="Also scan data/cache/**/*.json")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Limit unique URLs checked (0=all)")
    args = parser.parse_args(argv)

    if httpx is None:
        print("[check_all_urls] httpx is required: pip install httpx")
        return 1

    hubs = load_hubs()
    files = collect_json_files(include_cache=args.include_cache)
    print(f"[check_all_urls] scanning {len(files)} JSON files…")

    # Load all JSON once
    loaded: dict[Path, Any] = {}
    all_hits: list[dict[str, Any]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  skip {path.relative_to(ROOT)}: {exc}")
            continue
        loaded[path] = payload
        found: list[dict[str, Any]] = []
        walk_collect(payload, path="$", place_name="", platform_hint="", found=found)
        for item in found:
            item["file"] = path
            all_hits.append(item)

    unique_urls = sorted({item["url"] for item in all_hits})
    if args.limit and args.limit > 0:
        unique_urls = unique_urls[: args.limit]
    print(f"[check_all_urls] unique URLs to check: {len(unique_urls)}")

    results: dict[str, tuple[bool, str, int | None]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(check_url, url): url for url in unique_urls}
        done = 0
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                results[url] = fut.result()
            except Exception as exc:  # pragma: no cover
                results[url] = (False, f"error:{type(exc).__name__}", None)
            done += 1
            if done % 25 == 0 or done == len(futures):
                print(f"  checked {done}/{len(futures)}")

    alive = [u for u, (ok, _n, _s) in results.items() if ok]
    dead = [u for u, (ok, _n, _s) in results.items() if not ok]

    # Build replacement map with context from first occurrence
    context_by_url: dict[str, dict[str, str]] = {}
    for item in all_hits:
        context_by_url.setdefault(
            item["url"],
            {"place_name": item.get("place_name") or "", "platform_hint": item.get("platform_hint") or ""},
        )

    dead_map: dict[str, str] = {}
    for url in dead:
        ctx = context_by_url.get(url, {})
        dead_map[url] = fallback_url(
            url,
            platform_hint=ctx.get("platform_hint", ""),
            place_name=ctx.get("place_name", ""),
            hubs=hubs,
        )

    # Apply per file
    all_fixes: list[dict[str, str]] = []
    changed_files = 0
    for path, payload in loaded.items():
        fixed_payload, fixes = apply_fixes(payload, dead_map=dead_map, hubs=hubs)
        if not fixes:
            continue
        changed_files += 1
        for row in fixes:
            row["file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            all_fixes.append(row)
        if not args.dry_run:
            path.write_text(json.dumps(fixed_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Console report
    print("\n========== URL CHECK REPORT ==========")
    print(f"Files scanned      : {len(loaded)}")
    print(f"URL fields found   : {len(all_hits)}")
    print(f"Unique URLs checked: {len(results)}")
    print(f"Alive / OK         : {len(alive)}")
    print(f"Dead / failed      : {len(dead)}")
    print(f"Fixes applied      : {len(all_fixes)} across {changed_files} file(s)")
    print(f"Mode               : {'DRY-RUN' if args.dry_run else 'WRITE'}")
    if all_fixes:
        print("\n--- Fixed dead links ---")
        for row in all_fixes[:80]:
            print(f"* [{row['file']}] {row['path']}")
            print(f"    OLD: {row['old']}")
            print(f"    NEW: {row['new']}")
        if len(all_fixes) > 80:
            print(f"... and {len(all_fixes) - 80} more")
    elif dead:
        print("\nDead URLs detected but no in-file replacements matched (deduped / dry context).")
        for url in dead[:30]:
            ok, note, status = results[url]
            print(f"  DEAD [{status}] {note} :: {url}")
            print(f"       fallback => {dead_map.get(url)}")
    print("======================================\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
