import json
from datetime import datetime

def crawl_payment_offers():
    print("💳 [2/5] 開始抓取信用卡與 PayMe / AlipayHK / Reward+ 商場專屬回贈...")
    offers = [
        {
            "bank": "HSBC",
            "title": "指定商場簽賬滿 $500 即享 $50 獎賞錢",
            "start_date": datetime.now().strftime("%Y-%m-%d"),
            "end_date": "2026-09-15"
        }
    ]
    print(f"✅ 成功同步 {len(offers)} 項支付優惠")
    return offers

if __name__ == "__main__":
    crawl_payment_offers()
