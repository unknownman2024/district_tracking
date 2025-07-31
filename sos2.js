const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

const CONFIG = {
  date: dayjs().tz("Asia/Kolkata").format("YYYY-MM-DD"),
  contentId: "194117",
  movieCode: "MJ0RB1ZpBw",
  cutoffMins: 5
};

(async () => {
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districtdata/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // 🔁 Load existing data (if exists)
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

  const tasks = cities.map(city => (async () => {
    const url = `https://district.text2025mail.workers.dev/?city=${city.citycode}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;

    try {
const res = await fetch(url, {
  headers: {
    "User-Agent": "BOXOFFICE24"
  }
});
      const json = await res.json();

      const cinemas = [...(json.pageData?.nearbyCinemas || []), ...(json.pageData?.farCinemas || [])];

      for (const cinema of cinemas) {
        const venueName = cinema.cinemaInfo.name;
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
            city: city.RegionName,
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

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify({ date: CONFIG.date, venues: result }, null, 2));
  console.log(`✅ Done. Final total shows stored: ${result.length} → ${filePath}`);
})();
