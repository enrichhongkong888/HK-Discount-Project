"""Mall-name aliases and fuzzy matching against the 74-mall registry."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.casefold()
    text = text.replace("／", "/").replace("‧", "").replace("·", "")
    text = re.sub(r"[\s\-–—_·•、，,（）()【】\[\]『』「」\"']+", "", text)
    return text


# Common directory / brand-locator variants -> registry mall_name.
MALL_ALIASES: dict[str, str] = {
    "newtownplaza": "新城市廣場",
    "新城市廣場": "新城市廣場",
    "新城巿廣場": "新城市廣場",
    "沙田新城市廣場": "新城市廣場",
    "yohomall": "YOHO MALL 形點",
    "yohomall形點": "YOHO MALL 形點",
    "形點": "YOHO MALL 形點",
    "yoho mall": "YOHO MALL 形點",
    "yoho mall i": "YOHO MALL 形點",
    "yoho mall ii": "YOHO MALL 形點",
    "形點i": "YOHO MALL 形點",
    "形點ii": "YOHO MALL 形點",
    "festivalwalk": "又一城",
    "又一城": "又一城",
    "apm": "apm",
    "創紀之城五期apm": "apm",
    "harbourcity": "海港城",
    "海港城": "海港城",
    "海洋中心": "海港城",
    "港威商場": "海港城",
    "langhamplace": "朗豪坊",
    "朗豪坊": "朗豪坊",
    "olympiancity": "奧海城",
    "奧海城": "奧海城",
    "cityplaza": "太古城中心",
    "太古城中心": "太古城中心",
    "pacificplace": "太古廣場",
    "太古廣場": "太古廣場",
    "metroplaza": "新都會廣場",
    "新都會廣場": "新都會廣場",
    "maritimesquare": "青衣城",
    "青衣城": "青衣城",
    "popcorn": "PopCorn",
    "vcity": "V city",
    "v city": "V city",
    "tmtp": "屯門市廣場",
    "屯門市廣場": "屯門市廣場",
    "telfordplaza": "德福廣場",
    "德福廣場": "德福廣場",
    "plazahollywood": "荷里活廣場",
    "荷里活廣場": "荷里活廣場",
    "homesquare": "HomeSquare",
    "thewai": "圍方 The Wai",
    "圍方": "圍方 The Wai",
    "圍方thewai": "圍方 The Wai",
    "airside": "AIRSIDE",
    "megabox": "MegaBox",
    "theone": "THE ONE",
    "the one": "THE ONE",
    "timesquare": "時代廣場",
    "時代廣場": "時代廣場",
    "tsuenwanplaza": "荃灣廣場",
    "荃灣廣場": "荃灣廣場",
    "citywalk": "荃新天地",
    "荃新天地": "荃新天地",
    "eastpointcity": "東港城",
    "東港城": "東港城",
    "lokfuplace": "樂富廣場",
    "樂富廣場": "樂富廣場",
    "kornhillplaza": "康怡廣場",
    "康怡廣場": "康怡廣場",
    "whampoa": "黃埔天地",
    "黃埔天地": "黃埔天地",
    "黃埔新天地": "黃埔天地",
    "黃埔花園": "黃埔天地",
    "hysanplace": "Hysan Place",
    "landmarknorth": "上水廣場",
    "上水廣場": "上水廣場",
    "taipomegamall": "大埔超級城",
    "大埔超級城": "大埔超級城",
    "mostown": "新港城中心 MOSTown",
    "新港城中心": "新港城中心 MOSTown",
    "metrocity": "新都城中心",
    "新都城中心": "新都城中心",
    "parkcentral": "將軍澳中心 Park Central",
    "將軍澳中心": "將軍澳中心 Park Central",
    "vwalk": "V Walk",
    "elements": "ELEMENTS 圓方",
    "圓方": "ELEMENTS 圓方",
    "k11musea": "K11 MUSEA",
    "thesouthside": "THE SOUTHSIDE",
    "citygate": "東薈城名店倉",
    "東薈城": "東薈城名店倉",
    "東薈城名店倉": "東薈城名店倉",
    "windsorhouse": "皇室堡",
    "皇室堡": "皇室堡",
    # Link / Hang Lung / strata / Watsons locator shop-name variants
    "stanleyplaza": "赤柱廣場",
    "赤柱廣場": "赤柱廣場",
    "templemall": "黃大仙中心",
    "黃大仙中心": "黃大仙中心",
    "黃大仙中心北館": "黃大仙中心",
    "黃大仙中心南館": "黃大仙中心",
    "kwai chung plaza": "葵涌廣場",
    "葵涌廣場": "葵涌廣場",
    "taipo plaza": "大埔廣場",
    "大埔廣場": "大埔廣場",
    "opmall": "OP Mall 海之戀商場",
    "海之戀": "OP Mall 海之戀商場",
    "海之戀商場": "OP Mall 海之戀商場",
    "置富嘉湖": "+WOO 嘉湖",
    "+woo嘉湖": "+WOO 嘉湖",
    "+woo": "+WOO 嘉湖",
    "粉嶺名都廣場": "粉嶺名都商場",
    "名都廣場": "粉嶺名都商場",
    "愉景新城": "D·PARK 愉景新城",
    "dpark": "D·PARK 愉景新城",
    "海怡半島": "海怡廣場",
    "海怡廣場": "海怡廣場",
    "香港仔中心": "香港仔中心商場",
    "香港仔中心商場": "香港仔中心商場",
    "dbplaza": "愉景灣廣場 DB Plaza",
    "愉景灣商場": "愉景灣廣場 DB Plaza",
    "愉景灣廣場": "愉景灣廣場 DB Plaza",
    "db north": "愉景灣北商場 DB North Plaza",
    "愉景灣北商場": "愉景灣北商場 DB North Plaza",
    "合和中心": "合和中心",
    "合和商場": "合和商場",
    "沙田中心": "沙田中心",
    "西九龍中心": "西九龍中心",
    "fashionwalk": "利東街",  # legacy alias; prefer Lee Tung Avenue tenants only
    "利東街": "利東街",
    "lee tung avenue": "利東街",
    "囍滙": "利東街",
    # Fashion Walk (Causeway Bay) is NOT 利東街 — do not alias hanglung Fashion Walk here.
    "綠楊坊": "綠楊坊",
    "t town": "T Town",
    "天水圍t town": "T Town",
    "錦薈坊": "錦薈坊",
    "昇悅商場": "昇悅商場",
    "碧海藍天": "碧海藍天商場",
    "碧海藍天商場": "碧海藍天商場",
    "數碼港": "數碼港商場",
    "數碼港商場": "數碼港商場",
    "中環街市": "中環街市",
    "置地廣場": "置地廣場",
    "ifc": "國際金融中心商場",
    "國際金融中心": "國際金融中心商場",
}


@dataclass(frozen=True)
class RegistryMall:
    district: str
    mall_name: str


def build_registry_index(malls: list[dict]) -> dict[str, RegistryMall]:
    index: dict[str, RegistryMall] = {}
    for raw in malls:
        name = str(raw.get("mall_name") or "").strip()
        district = str(raw.get("district") or "").strip()
        if not name or not district:
            continue
        item = RegistryMall(district=district, mall_name=name)
        index[_norm(name)] = item
        # also register short aliases without English suffix
        short = re.sub(r"[a-z0-9 ·‧.]+$", "", name, flags=re.I).strip()
        if short and _norm(short) not in index:
            index[_norm(short)] = item
    for alias, canonical in MALL_ALIASES.items():
        key = _norm(alias)
        # resolve canonical via name match
        for nkey, item in list(index.items()):
            if item.mall_name == canonical or _norm(item.mall_name) == _norm(canonical):
                index[key] = item
                break
    return index


def match_mall(
    index: dict[str, RegistryMall],
    *,
    mall_hint: str = "",
    address: str = "",
) -> RegistryMall | None:
    blob = f"{mall_hint} {address}".strip()
    if not blob:
        return None
    direct = index.get(_norm(mall_hint))
    if direct:
        return direct
    # longest alias / registry key contained in blob
    candidates: list[tuple[int, RegistryMall]] = []
    norm_blob = _norm(blob)
    for key, item in index.items():
        if len(key) < 2:
            continue
        if key in norm_blob or norm_blob in key:
            candidates.append((len(key), item))
    if not candidates:
        # try alias table against blob
        for alias, canonical in MALL_ALIASES.items():
            akey = _norm(alias)
            if akey and akey in norm_blob:
                hit = index.get(_norm(canonical))
                if hit:
                    candidates.append((len(akey), hit))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
