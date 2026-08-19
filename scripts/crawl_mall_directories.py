import os
import json
import re
import requests
from bs4 import BeautifulSoup

# 更新精準網址與 URL 庫
MALL_SOURCES = [
    {"id": "apm", "name": "創紀之城五期 (apm)", "district": "觀塘區", "group": "SHKP", "url": "https://www.hkmalls.com/mall/apm"},
    {"id": "new_town_plaza", "name": "沙田新城市廣場", "district": "沙田區", "group": "SHKP", "url": "https://www.newtownplaza.com.hk/hk/promotions"},
    {"id": "tmtp", "name": "屯門市廣場", "district": "屯門區", "group": "Sino", "url": "https://www.tmtp.com.hk/tc/Promotions"},
    {"id": "citywalk", "name": "荃灣荃新天地", "district": "荃灣區", "group": "Sino", "url": "https://www.citywalk.com.hk/tc/Promotions"},
    {"id": "taikoo_place", "name": "太古城中心", "district": "東區", "group": "Swire", "url": "https://www.cityplaza.com/zh-hk/events"},
    {"id": "moko", "name": "MOKO 新世紀廣場", "district": "油尖旺區", "group": "SHKP", "url": "https://www.moko.com.hk/hk/events"},
    {"id": "popcorn", "name": "PopCorn", "district": "西貢區", "group": "MTR", "url": "https://www.popcornmall.com.hk/cht/promotions"},
    {"id": "harbour_city", "name": "海港城", "district": "油尖旺區", "group": "Wharf", "url": "https://www.harbourcity.com.hk/tc/happening/"},
    {"id": "chain_mannings", "name": "萬寧 Mannings", "district": "全港連鎖", "group": "Chain", "url": "https://www.mannings.com.hk/offers"},
    {"id": "chain_watsons", "name": "屈臣氏 Watsons", "district": "全港連鎖", "group": "Chain", "url": "https://www.watsons.com.hk/offers"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

def parse_generic_offers(mall):
    offers = []
    try:
        response = requests.get(mall["url"], headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[SKIP] {mall['name']} HTTP {response.status_code}")
            return offers

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all(class_=re.compile(r"(promo|event|offer|card|item|deal)", re.I))
        
        for card in cards[:8]:
            title_node = card.find(["h2", "h3", "h4", "strong", "a"])
            if not title_node:
                continue
            
            title = title_node.get_text(strip=True)
            if len(title) < 4:
                continue

            link = ""
            a_tag = card.find("a") if card.name != "a" else card
            if a_tag and a_tag.get("href"):
                href = a_tag["href"]
                link = href if href.startswith("http") else mall["url"].rstrip("/") + "/" + href.lstrip("/")

            desc_node = card.find(["p", "span"])
            desc = desc_node.get_text(strip=True) if desc_node else "詳情請參閱官方頁面"

            offers.append({
                "title": title,
                "description": desc,
                "link": link or mall["url"],
                "source": mall["name"]
            })
    except Exception as e:
        print(f"[ERROR] Parsing {mall['name']}: {e}")

    return offers

def run_crawler():
    print("🚀 開始執行 18 區商場與連鎖店熱門優惠爬蟲...")
    results = {}

    for mall in MALL_SOURCES:
        print(f"🔍 抓取中: [{mall['district']}] {mall['name']}...")
        offers = parse_generic_offers(mall)
        
        results[mall["id"]] = {
            "mall_id": mall["id"],
            "name": mall["name"],
            "district": mall["district"],
            "group": mall["group"],
            "url": mall["url"],
            "offers_count": len(offers),
            "offers": offers
        }

    os.makedirs("data", exist_ok=True)
    output_path = "data/malls.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 爬蟲修正版執行完成！已更新 {len(results)} 個商場/連鎖源至 {output_path}")

if __name__ == "__main__":
    run_crawler()
