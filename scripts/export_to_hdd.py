import json
import os
import shutil
import sys
from pathlib import Path

target_path = sys.argv[1] if len(sys.argv) > 1 else "F:\\HK_Store_Images"
HDD_TARGET_DIR = Path(target_path)
SOURCE_IMG_DIR = Path("frontend/images/stores")

def find_all_json_files():
    json_files = []
    for p in Path(".").rglob("*.json"):
        if "node_modules" not in str(p) and ".git" not in str(p):
            json_files.append(p)
    return json_files

def build_image_map():
    img_map = {}
    for json_path in find_all_json_files():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        def parse_node(node, current_district="未分類區域", current_mall="未知商場"):
            if isinstance(node, dict):
                dist = node.get("district") or current_district
                mall = node.get("name") if ("shops" in node or "stores" in node or "discounts" in node or "district" in node) else current_mall
                
                for k, v in node.items():
                    if isinstance(v, str) and ("frontend/images/stores/" in v or v.endswith((".jpg", ".png", ".jpeg"))):
                        fname = Path(v).name
                        if fname not in img_map or dist != "未分類區域":
                            shop_name = node.get("name") or node.get("title") or "店家"
                            img_map[fname] = {
                                "district": dist,
                                "mall": mall,
                                "shop": shop_name
                            }
                    else:
                        parse_node(v, dist, mall)
            elif isinstance(node, list):
                for item in node:
                    parse_node(item, current_district, current_mall)

        parse_node(data)
    return img_map

def export_images():
    if not SOURCE_IMG_DIR.exists():
        print(f"❌ 找不到圖片來源資料夾：{SOURCE_IMG_DIR}")
        return

    image_map = build_image_map()
    all_images = list(SOURCE_IMG_DIR.glob("*.*"))
    
    copied_count = 0
    print(f"🚀 開始全量掃描並匯出門面圖片（共 {len(all_images)} 張）至：{HDD_TARGET_DIR} ...\n")

    for img_file in all_images:
        info = image_map.get(img_file.name, {"district": "未分類區域", "mall": "未知商場", "shop": img_file.stem})
        district = info["district"]
        mall_name = info["mall"]
        shop_name = info["shop"]

        district_dir = HDD_TARGET_DIR / district
        district_dir.mkdir(parents=True, exist_ok=True)

        clean_shop = str(shop_name).replace("/", "_").replace("\\", "_")
        clean_mall = str(mall_name).replace("/", "_").replace("\\", "_")
        dst_filename = f"[{clean_mall}] {clean_shop}_{img_file.name}"

        dst_file = district_dir / dst_filename
        shutil.copy2(img_file, dst_file)
        copied_count += 1

    print(f"✅ 匯出完成！")
    print(f"📊 成功複製：{copied_count} 張門面圖（已全數分區歸檔至 {HDD_TARGET_DIR}）")

if __name__ == "__main__":
    export_images()
