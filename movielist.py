import json
import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import quote

# ---------------------
# CONFIG
# ---------------------
BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_FILE = "movielist.json"

# ---------------------
# Helper Functions
# ---------------------
def date_range(start_date_str, end_date_str):
    s = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    e = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    current = s
    while current <= e:
        yield current.isoformat()
        current += timedelta(days=1)

def fetch_daily_json(date_str):
    url = f"{BASE_URL}/{quote(date_str)}_Detailed.json"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def summarize_movie_list(movie_data, movie_name, language):
    shows = len(movie_data)
    sold = sum(float(s.get("sold",0) or 0) for s in movie_data)
    gross = sum(float(s.get("gross",0) or 0) for s in movie_data)
    return {
        "movie": movie_name,
        "language": language,
        "shows": shows,
        "sold": sold,
        "gross": gross
    }

# ---------------------
# Main Logic
# ---------------------
def build_movielist(start_date="2025-01-01"):
    # load existing movielist if exists
    movielist = {"last_updated": "", "movies": []}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                movielist = json.load(f)
        except Exception:
            pass

    # build dict for easy lookup
    movie_dict = {}
    for m in movielist.get("movies", []):
        key = m["movie"]
        if key not in movie_dict:
            movie_dict[key] = {
                "languages": set(m["languages"]),
                "dates": [m["dates"][0], m["dates"][-1]]
            }

    # determine dates to check
    today = datetime.now().date()
    earliest_date = start_date
    if movielist.get("movies"):
        # skip dates already covered except today
        all_dates = [d for m in movie_dict.values() for d in m["dates"]]
        earliest_date = min(all_dates)
    current_date = datetime.strptime(earliest_date, "%Y-%m-%d").date()
    end_date = today

    while current_date <= end_date:
        date_str = current_date.isoformat()
        # skip date if not today and already recorded
        if current_date != today:
            already = any(date_str >= m["dates"][0] and date_str <= m["dates"][-1] for m in movie_dict.values())
            if already:
                current_date += timedelta(days=1)
                continue

        data = fetch_daily_json(date_str)
        if not data:
            current_date += timedelta(days=1)
            continue

        for key, shows in data.items():
            if key in ("date","lastUpdated"):
                continue
            parts = [p.strip() for p in key.split("|")]
            base = parts[0]
            lang = parts[1] if len(parts) > 1 else "Unknown"

            if base not in movie_dict:
                movie_dict[base] = {"languages": set(), "dates":[date_str,date_str]}
            movie_dict[base]["languages"].add(lang)
            # update dates
            movie_dict[base]["dates"][0] = min(movie_dict[base]["dates"][0], date_str)
            movie_dict[base]["dates"][1] = max(movie_dict[base]["dates"][1], date_str)

        current_date += timedelta(days=1)

    # convert movie_dict to list
    movies_list = []
    for name, info in movie_dict.items():
        movies_list.append({
            "movie": name,
            "languages": sorted(list(info["languages"])),
            "dates": [info["dates"][0], info["dates"][1]]
        })

    # sort: latest release month first, then most languages, then release date
    def sort_key(item):
        # 1️⃣ Latest month of first available date
        min_month = int(item["dates"][0].split("-")[1])

        # 2️⃣ Number of languages descending
        lang_count = len(item["languages"])

        # 3️⃣ Most days available
        first_date = datetime.strptime(item["dates"][0], "%Y-%m-%d")
        last_date = datetime.strptime(item["dates"][-1], "%Y-%m-%d")
        days_available = (last_date - first_date).days

        return (-min_month, -lang_count, -days_available)

    movies_list.sort(key=sort_key)

    # save
    movielist = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "movies": movies_list}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(movielist, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved {OUTPUT_FILE} ({len(movies_list)} movies)")

if __name__ == "__main__":
    build_movielist(start_date="2025-09-01")
