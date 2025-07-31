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

(async () => {
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districtdata/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // 🔁 Load existing data (optional if fresh run)
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
    const url = `https://district.text2024mail.workers.dev/?city=${city.citycode}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;

    try {
      const res = await fetch(url);
      const json = await res.json();

      const cinemas = [...(json.pageData?.nearbyCinemas || []), ...(json.pageData?.farCinemas || [])];

      for (const cinema of cinemas) {
        const venueName = cinema.cinemaInfo.name;
        const shows = cinema.sessions || [];

        for (const session of shows) {
          const showTime = dayjs(session.showTime).tz("Asia/Kolkata");
          const minutesLeft = showTime.diff(now, "minute");

          if (minutesLeft > CONFIG.cutoffMins) continue;

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

          // ✅ Deduplicate by venue + time only
          const sig = `${venueName}_${timeStr}`;
          if (seenKeys.has(sig)) continue;
          seenKeys.add(sig);

          result.push({
            city: city.RegionName,
            venue: venueName,
            time: timeStr,
            totalSeats: total,
            available: avail,
            sold: sold,
            gross: gross,
            occupancy: occ,
            minsLeft: minutesLeft
          });

          console.log(`[${city.RegionName}] ${venueName} → ${timeStr} = ${minutesLeft} mins left`);
        }
      }

    } catch (err) {
      console.error(`❌ ${city.RegionName} failed: ${err.message}`);
    }
  })());

  await Promise.all(tasks);

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify({ date: CONFIG.date, venues: result }, null, 2));
  console.log(`✅ Done. Added ${result.length} unique shows → ${filePath}`);
})();
