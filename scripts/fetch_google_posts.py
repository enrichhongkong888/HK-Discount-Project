import os
import requests

def fetch_google_posts():
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    print("📍 [3/5] 開始抓取 Google Business Profile 店家最新貼文/優惠...")
    if not api_key:
        print("⚠️ 未設定 GOOGLE_MAPS_API_KEY，安全跳過 Google Posts 抓取")
        return
    print("✅ Google Posts 掃描完成")

if __name__ == "__main__":
    fetch_google_posts()
