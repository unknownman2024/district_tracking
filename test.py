import os
import json

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
            "housefull": 0,
            "cityDetails": {}  # ✅ city + state breakup
        }

        for s in shows:
            total = int(s.get("totalSeats", 0) or 0)
            sold = int(s.get("sold", 0) or 0)
            gross = float(s.get("gross", 0) or 0)
            occ = (sold / total * 100) if total else 0

            city = s.get("city", "Unknown")
            state = s.get("state", "Unknown")
            venue = s.get("venue")

            summary[movie]["shows"] += 1
            summary[movie]["gross"] += gross
            summary[movie]["sold"] += sold
            summary[movie]["totalSeats"] += total
            summary[movie]["venues"].add(venue)
            summary[movie]["cities"].add(city)

            if 50 <= occ < 98:
                summary[movie]["fastfilling"] += 1
            if occ >= 98:
                summary[movie]["housefull"] += 1

            # -------- CITY + STATE DETAILS --------
            city_state_key = f"{city} | {state}"

            if city_state_key not in summary[movie]["cityDetails"]:
                summary[movie]["cityDetails"][city_state_key] = {
                    "city": city,
                    "state": state,
                    "shows": 0,
                    "gross": 0,
                    "sold": 0,
                    "totalSeats": 0,     # internal use only
                    "venues": set(),    # ✅ for unique venue count
                    "fastfilling": 0,
                    "housefull": 0
                }

            c = summary[movie]["cityDetails"][city_state_key]
            c["shows"] += 1
            c["gross"] += gross
            c["sold"] += sold
            c["totalSeats"] += total
            c["venues"].add(venue)   # ✅ city-wise venues

            if 50 <= occ < 98:
                c["fastfilling"] += 1
            if occ >= 98:
                c["housefull"] += 1

    # -------- FINAL FORMAT (MATCHES LIVE NODE OUTPUT) --------
    final = {}
    for movie, v in summary.items():
        final[movie] = {
            "shows": v["shows"],
            "gross": round(v["gross"], 2),
            "sold": v["sold"],
            "totalSeats": v["totalSeats"],   # overall still kept
            "venues": len(v["venues"]),
            "cities": len(v["cities"]),
            "fastfilling": v["fastfilling"],
            "housefull": v["housefull"],
            "occupancy": round((v["sold"] / v["totalSeats"]) * 100, 2) if v["totalSeats"] else 0,
            "details": [
                {
                    "city": d["city"],
                    "state": d["state"],
                    "shows": d["shows"],
                    "gross": round(d["gross"], 2),
                    "sold": d["sold"],
                    "venues": len(d["venues"]),   # ✅ ADDED
                    "fastfilling": d["fastfilling"],
                    "housefull": d["housefull"],
                    "occupancy": round((d["sold"] / d["totalSeats"]) * 100, 2) if d["totalSeats"] else 0
                }
                for d in v["cityDetails"].values()
            ]
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
