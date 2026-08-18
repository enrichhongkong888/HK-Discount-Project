import json
import os
from datetime import datetime
from pathlib import Path

possible_files = [Path("data/malls.json"), Path("malls.json"), Path("discounts.json"), Path("data/discounts.json")]
DATA_FILE = next((p for p in possible_files if p.exists()), None)
STORES_IMG_DIR = Path("frontend/images/stores")

def audit_and_cleanup():
    if not DATA_FILE:
        print("❌ 找不到資料庫 JSON 檔案")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 相容 List 與 Dict 資料結構
    malls_list = []
    if isinstance(data, list):
        malls_list = data
    elif isinstance(data, dict):
        if "malls" in data and isinstance(data["malls"], list):
            malls_list = data["malls"]
        else:
            malls_list = [v for v in data.values() if isinstance(v, dict)]

    today = datetime.now().strftime("%Y-%m-%d")
    total_cleaned_offers = 0
    missing_images = []

    print(f"🔍 開始每日審查 (審查日期: {today})...\n")

    for mall in malls_list:
        if not isinstance(mall, dict):
            continue
        
        shops = mall.get("shops", []) or mall.get("stores", []) or []
        for shop in shops:
            if not isinstance(shop, dict):
                continue

            # 1. 清理過期優惠資料
            discounts = shop.get("discounts", []) or []
            valid_discounts = []
            for d in discounts:
                if not isinstance(d, dict):
                    continue
                end_date = d.get("end_date") or d.get("valid_until")
                if end_date and end_date < today:
                    total_cleaned_offers += 1
                else:
                    valid_discounts.append(d)
            shop["discounts"] = valid_discounts

            # 2. 審查門面圖是否存在
            img_url = shop.get("image_url") or shop.get("facade_image") or ""
            if img_url:
                filename = Path(img_url).name
                if not (STORES_IMG_DIR / filename).exists():
                    missing_images.append(f"[{mall.get('name', '未知商場')}] {shop.get('name', '未知店家')}")

    # 寫回更新後的資料庫
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ 審查與清理完成！")
    print(f"🧹 已自動刪除過期優惠：{total_cleaned_offers} 項")
    print(f"🖼️ 門面圖缺失店家：{len(missing_images)} 間")
    if missing_images:
        print("   缺失清單（將交由 Google Places API 自動補抓）：")
        for item in missing_images[:5]:
            print(f"   - {item}")

if __name__ == "__main__":
    audit_and_cleanup()
