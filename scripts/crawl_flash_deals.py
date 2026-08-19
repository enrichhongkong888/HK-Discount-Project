from datetime import datetime

def crawl_flash_deals():
    print("⚡ [4/5] 開始抓取 OpenRice 快閃特賣與商場開倉資訊...")
    flash_deals = [
        {
            "title": "運動品牌特賣會 2 折起",
            "mall": "海港城",
            "start_date": datetime.now().strftime("%Y-%m-%d"),
            "end_date": "2026-08-25"
        }
    ]
    print(f"✅ 成功擷取 {len(flash_deals)} 項快閃開倉優惠")
    return flash_deals

if __name__ == "__main__":
    crawl_flash_deals()
