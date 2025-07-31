const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

const CONFIG = {
  date: dayjs().tz("Asia/Kolkata").format("YYYY-MM-DD"),
  contentId: "196147",
  movieCode: "K5ih5j~m7F",
  cutoffMins: 5
};

// Title case helper
function toTitleCase(str) {
  return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

// Clean venue name for deduplication
function cleanVenueSimple(name) {
  return name
    .replace(/[^a-zA-Z0-9]/g, "")
    .replace(/(cinemas?|movieplex|plex|theatre|theater|screen|audi)/gi, "")
    .toLowerCase();
}

// Dedupe by venue, keep consistent city name
function deduplicateSameVenueAcrossCities(data) {
  const grouped = {};
  for (const entry of data) {
    const key = cleanVenueSimple(entry.venue);
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(entry);
  }

  const final = [];
  for (const group of Object.values(grouped)) {
    const resolvedCity = group[0].city;
    const resolvedState = group[0].state || "";
    for (const entry of group) {
      entry.city = resolvedCity;
      entry.state = resolvedState;
      final.push(entry);
    }
  }
  return final;
}

(async () => {
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districtdata/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // Load existing entries
  if (fs.existsSync(filePath)) {
    const existing = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    for (const v of existing.venues || []) {
      const sig = `${v.venue}_${v.time}`;
      seenKeys.add(sig);
      result.push(v);
    }
  }

  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json")
    .then(res => res.json());

  const validCities = cities.filter(c => c.citycode);

  const tasks = validCities.map(city => (async () => {
    const cityParam = city.citycode;
    const url = `https://district.text2024mail.workers.dev/?city=${cityParam}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;

    try {
      const res = await fetch(url);
      const data = await res.json();

      const showDates = data?.meta?.showDates || [];
      if (!showDates.includes(CONFIG.date)) {
        console.log(`⛔ Skipping ${city.RegionName} — ${CONFIG.date} not in showDates`);
        return;
      }

      const cinemas = [...(data.pageData?.nearbyCinemas || []), ...(data.pageData?.farCinemas || [])];

      for (const cinema of cinemas) {
        const venueName = cinema.cinemaInfo?.name || "Unknown Venue";
        const realCity = toTitleCase((cinema.cinemaInfo?.city || "").trim());
        const realState = toTitleCase((cinema.cinemaInfo?.state || "").trim());

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
            city: realCity || city.RegionName,
            state: realState,
            venue: venueName,
            time: timeStr,
            totalSeats: total,
            available: avail,
            sold: sold,
            gross: gross,
            occupancy: occ,
            minsLeft: minutesLeft
          };

          const existingIndex = result.findIndex(
            e => e.venue === venueName && e.time === timeStr
          );

          if (existingIndex !== -1) {
            const existing = result[existingIndex];
            if (newEntry.gross > existing.gross || newEntry.sold > existing.sold) {
              result[existingIndex] = newEntry;
              console.log(`🔁 Updated: [${realCity}] ${venueName} → ${timeStr} (gross/sold increased)`);
            }
          } else {
            seenKeys.add(sig);
            result.push(newEntry);
            console.log(`➕ Added: [${realCity}] ${venueName} → ${timeStr}`);
          }
        }
      }

    } catch (err) {
      console.error(`❌ [${city.RegionName}] failed: ${err.message}`);
    }
  })());

  await Promise.all(tasks);

  const finalData = deduplicateSameVenueAcrossCities(result);

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify({ date: CONFIG.date, venues: finalData }, null, 2));
  console.log(`✅ Done. Final total shows stored: ${finalData.length} → ${filePath}`);
})();
