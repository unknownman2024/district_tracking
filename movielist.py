import json
import requests
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# =====================================================
# CONFIG
# =====================================================
BASE_URL = "https://district24.pages.dev/Daily%20Advance"
OUTPUT_FILE = "movielist.json"

IST = timezone(timedelta(hours=5, minutes=30))

# =====================================================
# TIME HELPERS
# =====================================================
def today_ist():
    return datetime.now(IST).date()

# =====================================================
# FETCH JSON
# =====================================================
def fetch_daily_json(date_str):
    url = f"{BASE_URL}/{quote(date_str)}.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

# =====================================================
# MOVIE KEY PARSER (OLD + NEW)
# =====================================================
def parse_movie_key(key):
    """
    Supports:
    1) Dhurandhar | Hindi
    2) Avatar: Fire and Ash [3D | Hindi]
    3) Movie [Hindi]
    """

    key = key.strip()

    # New format → Movie [Format | Language]
    if "[" in key and "]" in key:
        base = key.split("[", 1)[0].strip()
        inside = key.split("[", 1)[1].split("]", 1)[0]
        parts = [p.strip() for p in inside.split("|")]
        lang = parts[-1]  # always LAST → ignore format
        return base, lang

    # Old format → Movie | Language
    if "|" in key:
        base, lang = [p.strip() for p in key.split("|", 1)]
        return base, lang

    return key, "Unknown"

# =====================================================
# MAIN BUILDER
# =====================================================
def build_movielist(start_date="2025-09-01"):

    # ---------------------------------------------
    # LOAD EXISTING FILE (SAFE MERGE)
    # ---------------------------------------------
    movie_dict = {}

    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
                for m in old.get("movies", []):
                    key = f'{m["movie"]}__{",".join(m["languages"])}'
                    movie_dict[key] = {
                        "movie": m["movie"],
                        "languages": set(m["languages"]),
                        "start": m["dates"][0],
                        "end": m["dates"][1],
                    }
        except Exception:
            pass

    # ---------------------------------------------
    # DATE RANGE
    # ---------------------------------------------
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = today_ist() + timedelta(days=5)

    current = start
    while current <= end:
        date_str = current.isoformat()

        data = fetch_daily_json(date_str)
        if not data:
            current += timedelta(days=1)
            continue

        for raw_key in data.keys():
            if raw_key in ("date", "lastUpdated"):
                continue

            movie, lang = parse_movie_key(raw_key)
            dict_key = f"{movie}__{lang}"

            if dict_key not in movie_dict:
                movie_dict[dict_key] = {
                    "movie": movie,
                    "languages": {lang},
                    "start": date_str,
                    "end": date_str,
                }
            else:
                movie_dict[dict_key]["start"] = min(
                    movie_dict[dict_key]["start"], date_str
                )
                movie_dict[dict_key]["end"] = max(
                    movie_dict[dict_key]["end"], date_str
                )

        current += timedelta(days=1)

    # ---------------------------------------------
    # FINAL LIST
    # ---------------------------------------------
    movies = []
    for info in movie_dict.values():
        movies.append({
            "movie": info["movie"],
            "languages": sorted(info["languages"]),
            "dates": [info["start"], info["end"]],
        })

    # ---------------------------------------------
    # SORTING (SMART)
    # ---------------------------------------------
    def sort_key(item):
        first = datetime.strptime(item["dates"][0], "%Y-%m-%d")
        last = datetime.strptime(item["dates"][1], "%Y-%m-%d")
        return (
            -first.year,
            -first.month,
            -len(item["languages"]),
            -(last - first).days
        )

    movies.sort(key=sort_key)

    # ---------------------------------------------
    # SAVE
    # ---------------------------------------------
    final = {
        "last_updated": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "movies": movies
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved {OUTPUT_FILE} | Movies: {len(movies)}")

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    build_movielist(start_date="2025-09-01")
