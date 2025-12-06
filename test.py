import os
import json
from datetime import datetime

BASE_DIR = "./Daily Boxoffice"

def rebuild_summary_from_detailed(detailed):
    summary = {}

    for movie, shows in detailed.items():
        if movie in ["date", "lastUpdated"]:
            continue
        if not isinstance(shows, list):
            continue

        summary[movie] = {
            "shows": 0,
            "gross": 0,
            "sold": 0,
            "totalSeats": 0,
            "venues": set(),
            "cities": set(),
            "fastfilling": 0,
            "housefull": 0
        }

        for s in shows:
            total = int(s.get("totalSeats", 0) or 0)
            sold = int(s.get("sold", 0) or 0)
            gross = float(s.get("gross", 0) or 0)
            occ = (sold / total * 100) if total else 0

            summary[movie]["shows"] += 1
            summary[movie]["gross"] += gross
            summary[movie]["sold"] += sold
            summary[movie]["totalSeats"] += total
            summary[movie]["venues"].add(s.get("venue"))
            summary[movie]["cities"].add(s.get("city"))

            if 50 <= occ < 98:
                summary[movie]["fastfilling"] += 1
            if occ >= 98:
                summary[movie]["housefull"] += 1

    final = {}
    for movie, v in summary.items():
        final[movie] = {
            "shows": v["shows"],
            "gross": round(v["gross"], 2),
            "sold": v["sold"],
            "totalSeats": v["totalSeats"],
            "venues": len(v["venues"]),
            "cities": len(v["cities"]),
            "fastfilling": v["fastfilling"],
            "housefull": v["housefull"],
            "occupancy": round((v["sold"] / v["totalSeats"]) * 100, 2) if v["totalSeats"] else 0
        }

    return final


def main():
    files = os.listdir(BASE_DIR)
    json_files = [f for f in files if f.endswith(".json") and not f.endswith("_Detailed.json")]

    fixed = 0
    skipped = 0

    for file in sorted(json_files):
        date_part = file.replace(".json", "")
        detailed_file = f"{date_part}_Detailed.json"

        summary_path = os.path.join(BASE_DIR, file)
        detailed_path = os.path.join(BASE_DIR, detailed_file)

        if not os.path.exists(detailed_path):
            print(f"⚠️ Skipping {file} (No detailed file found)")
            skipped += 1
            continue

        try:
            with open(detailed_path, "r", encoding="utf-8") as f:
                detailed_data = json.load(f)

            rebuilt_summary = rebuild_summary_from_detailed(detailed_data)

            new_summary = {
                "date": detailed_data.get("date", date_part),
                "lastUpdated": detailed_data.get("lastUpdated", ""),
                **rebuilt_summary
            }

            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(new_summary, f, indent=2, ensure_ascii=False)

            print(f"✅ Fixed: {file}")
            fixed += 1

        except Exception as e:
            print(f"❌ Error fixing {file}: {e}")

    print("\n==============================")
    print("AUTO CORRECTION COMPLETE")
    print("==============================")
    print(f"✅ Fixed Files  : {fixed}")
    print(f"⚠️ Skipped Files: {skipped}")


if __name__ == "__main__":
    main()
