const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

// ✅ Fixed release date in IST
const RELEASE_DATE = dayjs("2025-08-14").tz("Asia/Kolkata");
// Get today's date/time in IST
const todayIST = dayjs().tz("Asia/Kolkata");

// Decide target date
let targetDate;
if (todayIST.isBefore(RELEASE_DATE, "day")) {
  targetDate = RELEASE_DATE;
} else {
  targetDate = todayIST.add(1, "day");
}

const CONFIG = {
  name: "War 2 Telugu",
  date: targetDate.format("YYYY-MM-DD"),
  contentId: "161358",
  movieCode: "zfRPkPvClVf",
  cutoffMins: 60
};

console.log(`🎯 Tracking date: ${CONFIG.date} (today: ${todayIST.format("YYYY-MM-DD")})`);

(async () => {
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districtdata/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // 🔁 Load existing data safely
  if (fs.existsSync(filePath)) {
    try {
      const fileContent = fs.readFileSync(filePath, "utf-8");
      if (fileContent.trim()) {
        const existing = JSON.parse(fileContent);
        for (const v of existing.venues || []) {
          const sig = `${v.venue}_${v.time}`;
          seenKeys.add(sig);
          result.push(v);
        }
        console.log(`📂 Loaded ${result.length} existing entries from ${filePath}`);
      } else {
        console.warn(`⚠ File exists but empty: ${filePath}`);
      }
    } catch (err) {
      console.warn(`⚠ Could not parse existing JSON (${filePath}): ${err.message}`);
    }
  }

  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json", {
    headers: { "User-Agent": "BOXOFFICE24" }
  }).then(res => res.json());

  const tasks = cities.map(city => (async () => {
    if (!city.citycode) return;

    const url = `https://district.text2025mail.workers.dev/?city=${city.citycode}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;

    try {
      const res = await fetch(url, {
        headers: { "User-Agent": "BOXOFFICE24" }
      });

    const json = await res.json();

// 🚫 Skip this city if target date not in showDates
if (!json?.meta?.showDates?.includes(CONFIG.date)) {
  console.log(`⏭ Skipping ${city.RegionName} — ${CONFIG.date} not in showDates`);
  return;
}

const cinemas = [...(json.pageData?.nearbyCinemas || []), ...(json.pageData?.farCinemas || [])];

for (const cinema of cinemas) {
  const venueName = cinema.cinemaInfo.name;
  const venueAddress = cinema.cinemaInfo.address || "";
  const shows = cinema.sessions || [];

  for (const session of shows) {
    const showTime = dayjs(session.showTime).tz("Asia/Kolkata");
    const minutesLeft = showTime.diff(now, "minute");

    if (minutesLeft < CONFIG.cutoffMins) continue;

    const total = session.total;
    const avail = session.avail;
    const sold = total - avail;

    let gross = 0;
    for (const area of session.areas || []) {
      const soldSeats = area.sTotal - area.sAvail;
      gross += soldSeats * area.price;
    }

    const occ = total ? ((sold / total) * 100).toFixed(2) + "%" : "0.00%";
    const timeStr = showTime.format("hh:mm A");
    const sig = `${venueName}_${timeStr}`;

    const newEntry = {
      source: "district",
      city: city.RegionName,
      state: city.StateName,
      venue: venueName,
      address: venueAddress,
      time: timeStr,
      audi: session.audi || "", // 🎯 Added audi field here
      totalSeats: total,
      available: avail,
      sold: sold,
      gross: gross,
      occupancy: occ,
      minsLeft: minutesLeft
    };

    const existingIndex = result.findIndex(
  e => e.venue === venueName && e.time === timeStr && e.audi === (session.audi || "")
);

    if (existingIndex !== -1) {
      const existing = result[existingIndex];
      if (newEntry.gross > existing.gross || newEntry.sold > existing.sold) {
        result[existingIndex] = newEntry;
        console.log(`🔁 Updated: [${city.RegionName}] ${venueName} → ${timeStr} (gross/sold increased)`);
      }
    } else {
      seenKeys.add(sig);
      result.push(newEntry);
      console.log(`➕ Added: [${city.RegionName}] ${venueName} → ${timeStr}`);
    }
  }
}


    } catch (err) {
      console.error(`❌ ${city.RegionName} failed: ${err.message}`);
    }
  })());

  await Promise.all(tasks);

// 🧹 Deduplicate shows across all cities
const uniqueShowsMap = new Map();
for (const show of result) {
  const key = `${show.venue}__${show.address}__${show.time}__${show.audi}`;
  if (!uniqueShowsMap.has(key)) {
    uniqueShowsMap.set(key, show);
  } else {
    // Optionally keep the one with higher gross/sold
    const existing = uniqueShowsMap.get(key);
    if (show.gross > existing.gross || show.sold > existing.sold) {
      uniqueShowsMap.set(key, show);
    }
  }
}
const dedupedResult = Array.from(uniqueShowsMap.values());
console.log(`🧹 Deduplicated shows: ${result.length} → ${dedupedResult.length}`);

  // ✅ Prepare output
  const output = {
    date: CONFIG.date,
    lastUpdated: now.format("hh:mm A, DD MMMM YYYY"),
    venues: result // you'll replace with dedupedResult later
  };

  fs.mkdirSync(folder, { recursive: true });

  // ✨ Atomic write to avoid corrupt files
  const tmpPath = `${filePath}.tmp`;
  fs.writeFileSync(tmpPath, JSON.stringify(output, null, 2));
  fs.renameSync(tmpPath, filePath);

  console.log(`✅ Done. Final total shows stored: ${result.length} → ${filePath}`);
})();
