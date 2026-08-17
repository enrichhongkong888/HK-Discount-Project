"""Map directory / locator store names onto chain_store_offers chain_id values."""

from __future__ import annotations

import re
import unicodedata


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return text.casefold().strip()


# Ordered rules: first match wins. Keep specific names before generic ones.
BRAND_CHAIN_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"café\s*&?\s*meal\s*muji|cafe\s*&?\s*meal\s*muji", re.I), "muji_app", "Café & Meal MUJI"),
    (re.compile(r"無印良品|\bmuji\b", re.I), "muji_app", "無印良品"),
    (re.compile(r"\buniqlo\b", re.I), "uniqlo_app", "UNIQLO"),
    (re.compile(r"(?<![a-z])gu(?![a-z])|ジーユー", re.I), "gu_app", "GU"),
    (re.compile(r"豐澤|\bfortress\b", re.I), "fortress_club", "豐澤"),
    (re.compile(r"百老匯|\bbroadway\b", re.I), "broadway_club", "百老匯"),
    (re.compile(r"一田|\byata\b", re.I), "yata_app", "一田"),
    (re.compile(r"living\s*plaza", re.I), "aeon_member", "Living PLAZA by AEON"),
    (re.compile(r"aeon\s*mono\s*mono|mono\s*mono", re.I), "aeon_member", "AEON Mono Mono"),
    (re.compile(r"aeon\s*style|aeon\s*supermarket|\baeon\b|永旺", re.I), "aeon_member", "AEON"),
    (re.compile(r"莎莎|\bsa\s*sa\b|\bsasa\b", re.I), "sasa_vip", "莎莎"),
    (re.compile(r"星巴克|\bstarbucks\b", re.I), "starbucks_rewards", "星巴克"),
    (re.compile(r"麥當勞|mcdonald", re.I), "mcdonalds_app", "麥當勞"),
    (re.compile(r"譚仔三哥|sam\s*gor", re.I), "samgor_spicy_club", "譚仔三哥米線"),
    (re.compile(r"譚仔米線|tam\s*jai(?!\s*sam)", re.I), "tamjai_club", "譚仔米線"),
    (re.compile(r"market\s*place", re.I), "yuu", "Market Place"),
    (re.compile(r"惠康|\bwellcome\b", re.I), "yuu", "惠康"),
    (re.compile(r"百佳|\bparknshop\b|fusion\b|taste\b", re.I), "moneyback", "百佳"),
    (re.compile(r"萬寧|\bmannings\b", re.I), "yuu", "萬寧"),
    (re.compile(r"屈臣氏|\bwatsons\b", re.I), "moneyback", "屈臣氏"),
    (re.compile(r"7-?eleven|7-11|七十一", re.I), "yuu", "7-Eleven"),
    (re.compile(r"ok\s*便利店|\bcircle\s*k\b", re.I), "ok_stamp_it", "OK便利店"),
    (re.compile(r"大家樂|cafe\s*de\s*coral", re.I), "cafe_de_coral_club100", "大家樂"),
    (re.compile(r"大快活|\bfairwood\b", re.I), "fairwood_app", "大快活"),
    (re.compile(r"美心\s*mx|\bmx\b", re.I), "mx_eatizen", "美心 MX"),
    (re.compile(r"美心西餅|maxims?\s*cakes?", re.I), "maxims_cakes_eatizen", "美心西餅"),
    (re.compile(r"肯德基|\bkfc\b", re.I), "kfc_app", "KFC"),
    (re.compile(r"必勝客|pizza\s*hut", re.I), "pizza_hut_rewards", "必勝客"),
    (re.compile(r"太平洋咖啡|pacific\s*coffee", re.I), "pacific_coffee_perfect_cup", "太平洋咖啡"),
    (re.compile(r"貢茶|gong\s*cha", re.I), "gong_cha_members", "貢茶"),
    (re.compile(r"迷客夏|milksha|milk\s*sha", re.I), "milksha_members", "迷客夏"),
    (re.compile(r"茶湯會", re.I), "cha_tang_hui_members", "茶湯會"),
    (re.compile(r"鴻福堂|hung\s*fook\s*tong", re.I), "hung_fook_tong_vip", "鴻福堂"),
    (re.compile(r"許留山|hui\s*lau\s*shan", re.I), "hui_lau_shan_members", "許留山"),
    (re.compile(r"元氣壽司|genki", re.I), "genki_sushi_members", "元氣壽司"),
    (re.compile(r"爭鮮|sushi\s*express", re.I), "sushi_express_members", "爭鮮"),
    (re.compile(r"翠華|tsui\s*wah", re.I), "tsui_wah_members", "翠華餐廳"),
    (re.compile(r"吉野家|yoshinoya|yoshi", re.I), "yoshi_club", "吉野家"),
    (re.compile(r"東海堂|a-?1\s*bakery", re.I), "a1_bakery_members", "A-1 Bakery"),
    (re.compile(r"聖安娜|saint\s*honore|st\.?\s*honore", re.I), "saint_honore_cake_easy", "聖安娜"),
    (re.compile(r"奇華|kee\s*wah", re.I), "kee_wah_fans", "奇華餅家"),
    (re.compile(r"榮華餅家|wing\s*wah", re.I), "wing_wah_members", "榮華餅家"),
    (re.compile(r"colourmix|卡萊美", re.I), "colourmix_vip", "Colourmix"),
    (re.compile(r"japan\s*home|jhc\b|實惠", re.I), "jhc_jfun", "JHC"),
    (re.compile(r"千色|citistore|\bcu\b\s*app", re.I), "citistore_cu_app", "千色"),
    (re.compile(r"city'?s?uper|log-?on", re.I), "citysuper_super_e", "city'super"),
    (re.compile(r"donki|驚安の殿堂|驚安殿堂", re.I), "donki_dmiles", "DON DON DONKI"),
    (re.compile(r"實惠家居|pricerite|p-?coin", re.I), "pricerite_pcoin", "實惠"),
]


def match_brand(store_name: str) -> tuple[str, str] | None:
    """Return (chain_id, canonical_store_name) or None."""
    text = _norm(store_name)
    if not text:
        return None
    for pattern, chain_id, label in BRAND_CHAIN_RULES:
        if pattern.search(store_name) or pattern.search(text):
            return chain_id, label
    return None
