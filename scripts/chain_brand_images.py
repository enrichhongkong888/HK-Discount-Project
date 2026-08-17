# -*- coding: utf-8 -*-
"""Hong Kong chain retail brand image mapping and local placard generation.

When mall directories lack a facade photo, crawl_mall_directories uses this module
to download (when possible) or render a brand-coloured logo placard into
frontend/images/brands/{brand_id}.jpg, then copies it onto each store_key.
"""

from __future__ import annotations

import io
import re
import shutil
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND_IMG_DIR = ROOT / "frontend" / "images" / "brands"
DEFAULTS_DIR = ROOT / "images" / "defaults"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

# brand_id -> aliases (matched case-insensitive / substring), label, colours, optional remote URLs
CHAIN_BRANDS: dict[str, dict[str, Any]] = {
    "watsons": {
        "label": "屈臣氏 Watsons",
        "aliases": ("屈臣氏", "watsons", "watson"),
        "bg": (0, 115, 74),
        "fg": (255, 255, 255),
        "domains": ("watsons.com.hk", "watsons.com"),
    },
    "muji": {
        "label": "無印良品 MUJI",
        "aliases": ("無印良品", "muji", "café & meal muji", "cafe & meal muji"),
        "bg": (120, 120, 120),
        "fg": (255, 255, 255),
        "domains": ("muji.com", "muji.com.hk"),
    },
    "mannings": {
        "label": "萬寧 Mannings",
        "aliases": ("萬寧", "mannings"),
        "bg": (0, 133, 66),
        "fg": (255, 255, 255),
        "domains": ("mannings.com.hk",),
    },
    "uniqlo": {
        "label": "UNIQLO",
        "aliases": ("uniqlo", "優衣庫"),
        "bg": (255, 0, 0),
        "fg": (255, 255, 255),
        "domains": ("uniqlo.com",),
    },
    "fortress": {
        "label": "豐澤 Fortress",
        "aliases": ("豐澤", "fortress"),
        "bg": (0, 82, 155),
        "fg": (255, 255, 255),
        "domains": ("fortress.com.hk",),
    },
    "gu": {
        "label": "GU",
        "aliases": ("gu hong kong", " gu ", "ｇｕ"),
        "bg": (0, 90, 160),
        "fg": (255, 255, 255),
        "domains": ("gu-global.com",),
    },
    "hm": {
        "label": "H&M",
        "aliases": ("h&m", "h & m", "hm "),
        "bg": (232, 17, 35),
        "fg": (255, 255, 255),
        "domains": ("hm.com",),
    },
    "zara": {
        "label": "ZARA",
        "aliases": ("zara",),
        "bg": (20, 20, 20),
        "fg": (255, 255, 255),
        "domains": ("zara.com",),
    },
    "ikea": {
        "label": "IKEA 宜家",
        "aliases": ("ikea", "宜家"),
        "bg": (0, 88, 163),
        "fg": (255, 219, 0),
        "domains": ("ikea.com.hk", "ikea.com"),
    },
    "decathlon": {
        "label": "Decathlon",
        "aliases": ("decathlon", "迪卡儂"),
        "bg": (0, 131, 62),
        "fg": (255, 255, 255),
        "domains": ("decathlon.com.hk", "decathlon.hk"),
    },
    "adidas": {
        "label": "adidas",
        "aliases": ("adidas", "阿迪達斯"),
        "bg": (0, 0, 0),
        "fg": (255, 255, 255),
        "domains": ("adidas.com.hk", "adidas.com"),
    },
    "nike": {
        "label": "NIKE",
        "aliases": ("nike", "耐克"),
        "bg": (17, 17, 17),
        "fg": (255, 255, 255),
        "domains": ("nike.com",),
    },
    "apple": {
        "label": "Apple",
        "aliases": ("apple store", "apple ", "蘋果"),
        "bg": (29, 29, 31),
        "fg": (245, 245, 247),
        "domains": ("apple.com",),
    },
    "samsung": {
        "label": "Samsung",
        "aliases": ("samsung", "三星"),
        "bg": (20, 40, 160),
        "fg": (255, 255, 255),
        "domains": ("samsung.com",),
    },
    "eslite": {
        "label": "誠品 eslite",
        "aliases": ("誠品", "eslite"),
        "bg": (180, 40, 40),
        "fg": (255, 255, 255),
        "domains": ("eslite.com",),
    },
    "logon": {
        "label": "LOG-ON",
        "aliases": ("log-on", "logon", "log on"),
        "bg": (240, 90, 40),
        "fg": (255, 255, 255),
        "domains": ("logon.com.hk",),
    },
    "g2000": {
        "label": "G2000",
        "aliases": ("g2000",),
        "bg": (0, 70, 140),
        "fg": (255, 255, 255),
        "domains": ("g2000.com.hk",),
    },
    "giordano": {
        "label": "Giordano",
        "aliases": ("giordano", "佐丹奴"),
        "bg": (0, 90, 170),
        "fg": (255, 255, 255),
        "domains": ("giordano.com",),
    },
    "bossini": {
        "label": "bossini",
        "aliases": ("bossini", "堡獅龍"),
        "bg": (200, 16, 46),
        "fg": (255, 255, 255),
        "domains": ("bossini.com",),
    },
    "toysrus": {
        "label": "玩具反斗城",
        "aliases": ("玩具反斗城", "toys\"r\"us", "toys r us", "toysrus"),
        "bg": (0, 70, 170),
        "fg": (255, 210, 0),
        "domains": ("toysrus.com.hk",),
    },
    "wellcome": {
        "label": "惠康 Wellcome",
        "aliases": ("惠康", "wellcome"),
        "bg": (228, 0, 43),
        "fg": (255, 255, 255),
        "domains": ("wellcome.com.hk",),
    },
    "parknshop": {
        "label": "百佳 PNS",
        "aliases": ("百佳", "park'n shop", "parknshop", "park n shop"),
        "bg": (0, 128, 96),
        "fg": (255, 255, 255),
        "domains": ("pns.hk", "parknshop.com"),
    },
    "aeon": {
        "label": "AEON",
        "aliases": ("aeon", "永旺"),
        "bg": (0, 90, 170),
        "fg": (255, 255, 255),
        "domains": ("aeonstores.com.hk",),
    },
    "seveneleven": {
        "label": "7-Eleven",
        "aliases": ("7-eleven", "7eleven", "7-11", "seven eleven"),
        "bg": (0, 133, 66),
        "fg": (255, 210, 0),
        "domains": ("7-eleven.com.hk",),
    },
    "circlek": {
        "label": "Circle K",
        "aliases": ("circle k", "ok便利店", "circlek"),
        "bg": (220, 40, 40),
        "fg": (255, 255, 255),
        "domains": ("circlek.hk",),
    },
    "bestmart360": {
        "label": "優品360",
        "aliases": ("優品360", "best mart 360", "bestmart360"),
        "bg": (230, 70, 30),
        "fg": (255, 255, 255),
        "domains": ("bestmart360.com",),
    },
    "japanhome": {
        "label": "Japan Home",
        "aliases": ("japan home", "日居家品"),
        "bg": (200, 30, 40),
        "fg": (255, 255, 255),
        "domains": ("japanhome.com.hk",),
    },
    "marks": {
        "label": "Marks & Spencer",
        "aliases": ("marks & spencer", "馬莎", "m&s"),
        "bg": (0, 120, 70),
        "fg": (255, 255, 255),
        "domains": ("marksandspencer.com.hk",),
    },
    "lululemon": {
        "label": "lululemon",
        "aliases": ("lululemon",),
        "bg": (212, 32, 39),
        "fg": (255, 255, 255),
        "domains": ("lululemon.com",),
    },
    "newbalance": {
        "label": "New Balance",
        "aliases": ("new balance", "nb "),
        "bg": (190, 20, 40),
        "fg": (255, 255, 255),
        "domains": ("newbalance.com.hk",),
    },
}


def _norm_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def resolve_chain_brand(store_name: Any) -> str | None:
    name = _norm_name(store_name)
    if not name:
        return None
    # Prefer longer alias hits to avoid GU matching inside other words awkwardly
    best_id: str | None = None
    best_len = 0
    for brand_id, meta in CHAIN_BRANDS.items():
        for alias in meta["aliases"]:
            a = alias.casefold().strip()
            if len(a) < 2:
                continue
            if a in name and len(a) > best_len:
                best_id = brand_id
                best_len = len(a)
    return best_id


def default_image_for_vertical(vertical: Any) -> str:
    v = str(vertical or "").strip().casefold()
    if v in {"dining", "餐飲", "food", "restaurant"} or "dining" in v or "餐" in v:
        return "images/defaults/restaurant_default.png"
    if v in {"retail", "零售", "shopping"} or "retail" in v or "零售" in v:
        return "images/defaults/retail_default.png"
    return "images/defaults/store_default.png"


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\seguiemj.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_placard(label: str, bg: tuple[int, int, int], fg: tuple[int, int, int], size=(540, 375)) -> Image.Image:
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    # subtle texture bands
    band = tuple(max(0, min(255, c + 18)) for c in bg)
    for y in range(0, size[1], 18):
        draw.rectangle((0, y, size[0], y + 8), fill=band)
    # inner frame
    inset = 18
    draw.rounded_rectangle(
        (inset, inset, size[0] - inset, size[1] - inset),
        radius=28,
        outline=fg,
        width=3,
    )
    font = _font(42)
    small = _font(22)
    text = label
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size[0] - tw) // 2
    y = (size[1] - th) // 2 - 8
    draw.text((x, y), text, fill=fg, font=font)
    sub = "香港連鎖品牌"
    sb = draw.textbbox((0, 0), sub, font=small)
    sx = (size[0] - (sb[2] - sb[0])) // 2
    draw.text((sx, y + th + 14), sub, fill=fg, font=small)
    return img


def _try_fetch_favicon(domains: tuple[str, ...]) -> Image.Image | None:
    with httpx.Client(timeout=12.0, follow_redirects=True, headers=UA) as client:
        for domain in domains:
            url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            try:
                r = client.get(url)
                if r.status_code >= 400 or len(r.content) < 200:
                    continue
                icon = Image.open(io.BytesIO(r.content)).convert("RGBA")
                return icon
            except Exception:  # noqa: BLE001
                continue
    return None


def render_brand_image(brand_id: str, *, force: bool = False) -> Path | None:
    meta = CHAIN_BRANDS.get(brand_id)
    if not meta:
        return None
    BRAND_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest = BRAND_IMG_DIR / f"{brand_id}.jpg"
    if dest.exists() and dest.stat().st_size > 2000 and not force:
        return dest

    img = _draw_placard(str(meta["label"]), tuple(meta["bg"]), tuple(meta["fg"]))
    icon = _try_fetch_favicon(tuple(meta.get("domains") or ()))
    if icon is not None:
        icon = icon.resize((96, 96), Image.Resampling.LANCZOS)
        # white circle behind icon
        badge = Image.new("RGBA", (112, 112), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(badge)
        bdraw.ellipse((0, 0, 111, 111), fill=(255, 255, 255, 230))
        badge.paste(icon, (8, 8), icon)
        canvas = img.convert("RGBA")
        canvas.paste(badge, ((img.width - 112) // 2, 42), badge)
        img = canvas.convert("RGB")

    img.save(dest, format="JPEG", quality=88, optimize=True)
    return dest


def ensure_all_brand_images(*, force: bool = False) -> int:
    ok = 0
    for brand_id in CHAIN_BRANDS:
        if render_brand_image(brand_id, force=force):
            ok += 1
    return ok


def apply_brand_to_store(brand_id: str, dest: Path) -> bool:
    src = render_brand_image(brand_id)
    if not src or not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest.exists() and dest.stat().st_size > 800


def ensure_category_defaults(*, force: bool = False) -> None:
    DEFAULTS_DIR.mkdir(parents=True, exist_ok=True)
    specs = {
        "restaurant_default.png": {
            "bg": (45, 74, 62),
            "fg": (232, 245, 233),
            "title": "餐飲美食",
            "sub": "Dining",
        },
        "retail_default.png": {
            "bg": (46, 74, 110),
            "fg": (232, 240, 254),
            "title": "零售購物",
            "sub": "Retail",
        },
        "store_default.png": {
            "bg": (84, 68, 52),
            "fg": (255, 244, 230),
            "title": "商店服務",
            "sub": "Store",
        },
    }
    for name, spec in specs.items():
        path = DEFAULTS_DIR / name
        if path.exists() and path.stat().st_size > 4000 and not force:
            continue
        img = _draw_placard(spec["title"], spec["bg"], spec["fg"], size=(540, 375))
        draw = ImageDraw.Draw(img)
        small = _font(26)
        sb = draw.textbbox((0, 0), spec["sub"], font=small)
        draw.text(((540 - (sb[2] - sb[0])) // 2, 300), spec["sub"], fill=spec["fg"], font=small)
        img.save(path, format="PNG", optimize=True)


if __name__ == "__main__":
    ensure_category_defaults(force=True)
    n = ensure_all_brand_images(force=True)
    print(f"[chain_brand_images] defaults ready; brands={n} dir={BRAND_IMG_DIR}")
