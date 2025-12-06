import json, os, requests, pytz
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Chain Daily Breakdown"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHAIN_LIST = [
    "PVR", "INOX", "Cinepolis", "Movietime Cinemas", "Wave Cinemas",
    "Miraj Cinemas", "Rajhans Cinemas", "Asian Mukta",
    "MovieMax", "Mythri Cinemas", "Maxus Cinemas"
]

def log(msg):
    print(f"➡ {msg}")

def detect_chain(venue):
    venue = venue.lower()
    for chain in CHAIN_LIST:
        if chain.lower() in venue:
            return chain
    return None

def fetch(date):
    url = f"{BASE_URL}/{date}_Detailed.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            log(f"📥 Loaded {date}")
            return r.json()
    except:
        pass
    log(f"⚠ No data for {date}")
    return None


def process(shows):
    # Track unique venues, total seats only for occupancy calc
    chain_data = defaultdict(lambda: {"sold": 0, "gross": 0, "seats": 0, "shows": 0, "venues": set()})

    for s in shows:
        venue = s.get("venue", "").strip()
        chain = detect_chain(venue)
        if not chain:
            continue

        chain_data[chain]["shows"] += 1
        chain_data[chain]["sold"] += s.get("sold", 0) or 0
        chain_data[chain]["gross"] += s.get("gross", 0) or 0
        chain_data[chain]["seats"] += s.get("totalSeats", 0) or 0
        chain_data[chain]["venues"].add(venue)

    # Calculate occupancy with SEATS but output VENUE_COUNT
    for c, v in chain_data.items():
        v["occ"] = round((v["sold"] / v["seats"] * 100), 2) if v["seats"] else 0
        v["venue_count"] = len(v["venues"])  # final output count

    return chain_data


def save(filepath, data):
    ist = pytz.timezone("Asia/Kolkata")
    data["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log(f"💾 Saved → {filepath}")


def process_current_month(year, month):
    fname = f"{year}-{month:02d}.json"
    path = os.path.join(OUTPUT_DIR, fname)

    # Load existing
    if os.path.exists(path):
        log(f"🔁 Updating existing current month → {fname}")
        with open(path, "r", encoding="utf-8") as f:
            month_data = json.load(f)
    else:
        log(f"🆕 Creating new current month file → {fname}")
        month_data = {}

    today = datetime.now().date()
    start = datetime(year, month, 1)

    cur = start
    while cur.date() <= today:
        date = cur.strftime("%Y-%m-%d")

        # Skip past dates already processed
        if date in month_data and cur.date() < today:
            log(f"⏭ Skipping existing {date}")
            cur += timedelta(days=1)
            continue

        daily = fetch(date)
        if daily:
            for movie, shows in daily.items():
                if not isinstance(shows, list): continue

                stats = process(shows)
                if stats:
                    month_data.setdefault(movie, {})[date] = {
                        c: [v["shows"], v["sold"], v["venue_count"], v["gross"], v["occ"]]
                        for c, v in stats.items()
                    }
                    log(f"✔ Updated {movie} → {date}")

        cur += timedelta(days=1)

    save(path, month_data)


def process_old_month(year, month):
    fname = f"{year}-{month:02d}.json"
    path = os.path.join(OUTPUT_DIR, fname)

    if os.path.exists(path):
        log(f"⏭ Skipping past month (already exists): {fname}")
        return

    log(f"📅 Creating past month file → {fname}")
    month_data = {}
    
    start = datetime(year, month, 1)
    end = (start.replace(day=28) + timedelta(days=5)).replace(day=1) - timedelta(days=1)

    cur = start
    while cur.date() <= end.date():
        date = cur.strftime("%Y-%m-%d")
        daily = fetch(date)

        if daily:
            for movie, shows in daily.items():
                if not isinstance(shows, list): continue

                stats = process(shows)
                if stats:
                    month_data.setdefault(movie, {})[date] = {
                        c: [v["shows"], v["sold"], v["venue_count"], v["gross"], v["occ"]]
                        for c, v in stats.items()
                    }

        cur += timedelta(days=1)

    save(path, month_data)


def main():
    today = datetime.now()
    start_month = 9
    start_year = today.year if today.month >= 9 else today.year - 1

    y, m = start_year, start_month

    while (y < today.year) or (m <= today.month):
        if y == today.year and m == today.month:
            process_current_month(y, m)
        else:
            process_old_month(y, m)

        m += 1
        if m > 12:
            m = 1
            y += 1


if __name__ == "__main__":
    main()
