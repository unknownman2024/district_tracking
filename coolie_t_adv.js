// districtFetcher.js
const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");
const crypto = require("crypto");

dayjs.extend(utc);
dayjs.extend(timezone);


// ✅ Fixed release date in IST
const RELEASE_DATE = dayjs("2025-08-14").tz("Asia/Kolkata");
// Get today's date/time in IST
const todayIST = dayjs().tz("Asia/Kolkata");
// Decide target date
let targetDate;
if (todayIST.isBefore(RELEASE_DATE, "day")) {
  // Before release day → track for release day
  targetDate = RELEASE_DATE;
} else {
  // On or after release day → track for next day
  targetDate = todayIST.add(1, "day");
}

const CONFIG = {
  name: "Coolie Tamil",
  language: "tamil",
  date: targetDate.format("YYYY-MM-DD"), // dynamic target
  contentId: "172677",
  movieCode: "ZcW3aqXSzc",
  cutoffMins: 60
};


function randomIP() {
  return Array(4).fill(0).map(() => Math.floor(Math.random() * 256)).join(".");
}

async function fetchDistrictData(movieCode, cityKey, contentId, date) {
  const latitude = "17.39784178559756";
  const longitude = "78.47682085228203";

  const deviceId = crypto.randomUUID();
  const guestToken = `${Date.now()}_${Math.floor(Math.random() * 1e18)}_ax${Math.random().toString(36).substring(2, 10)}`;
  const spoofedIP = randomIP();

  const userAgents = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-M115F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.210 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
  ];
  const userAgent = userAgents[Math.floor(Math.random() * userAgents.length)];

  const url = `https://www.district.in/gw/consumer/movies/v5/movie?version=3&site_id=1&channel=ANDROIDAPPINSIDER&child_site_id=1&platform=district&latitude=${latitude}&longitude=${longitude}&cinemaOrderLogic=3&movieCode=${movieCode}&city_key=${cityKey}&content_id=${contentId}&date=${date}`;

  const headers = {
    "accept": "*/*",
    "accept-language": "en-GB,en;q=0.9",
    "api_source": "district",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": `https://www.district.in/movies/movie-tickets-in-${cityKey}-MV${contentId}?frmtid=${movieCode}`,
    "user-agent": userAgent,
    "x-app-type": "ed_mweb",
    "x-guest-token": guestToken,
    "x-device-id": deviceId,
    "x-forwarded-for": spoofedIP,
    "cookie": [
      `x-device-id=${deviceId}`,
      `location=%7B%22city_key%22%3A%22${cityKey}%22%2C%22lat%22%3A${latitude}%2C%22long%22%3A${longitude}%7D`
    ].join("; ")
  };

  const start = Date.now();
  const res = await fetch(url, { headers });
  const data = await res.json();
  data._debug = { fetched_in_ms: Date.now() - start };

  return data;
}


console.log(`🎯 Tracking date: ${CONFIG.date} (today: ${todayIST.format("YYYY-MM-DD")})`);

(async () => {
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districtdata/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  if (fs.existsSync(filePath)) {
    const existing = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    for (const v of existing.venues || []) {
      const sig = `${v.venue}_${v.time}`;
      seenKeys.add(sig);
      result.push(v);
    }
  }

  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json", {
    headers: { "User-Agent": "BOXOFFICE24" }
  }).then(res => res.json());

  const tasks = cities.map(city => (async () => {
    if (!city.citycode) return;
    console.log(`🌐 Fetching directly for: ${city.RegionName}`);

    try {
      const json = await fetchDistrictData(CONFIG.movieCode, city.citycode, CONFIG.contentId, CONFIG.date);

      const allowedLangs = json?.meta?.movie?.languages || [];
      const expectedLang = CONFIG.language?.toLowerCase();

      if (!json?.meta?.showDates?.includes(CONFIG.date)) {
        console.log(`⏭ Skipping ${city.RegionName} — ${CONFIG.date} not in showDates`);
        return;
      }

      if (expectedLang && !allowedLangs.map(l => l.toLowerCase()).includes(expectedLang)) {
        console.log(`⛔ Skipping ${city.RegionName} — Expected "${CONFIG.language}", got: ${allowedLangs.join(", ") || "none"}`);
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
            audi: session.audi || "",
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
              console.log(`🔁 Updated: [${city.RegionName}] ${venueName} → ${timeStr}`);
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

  const uniqueShowsMap = new Map();
  for (const show of result) {
    const key = `${show.venue}__${show.address}__${show.time}__${show.audi}`;
    if (!uniqueShowsMap.has(key)) {
      uniqueShowsMap.set(key, show);
    } else {
      const existing = uniqueShowsMap.get(key);
      if (show.gross > existing.gross || show.sold > existing.sold) {
        uniqueShowsMap.set(key, show);
      }
    }
  }

  const dedupedResult = Array.from(uniqueShowsMap.values());
  console.log(`🧹 Deduplicated: ${result.length} → ${dedupedResult.length}`);

  const output = {
    date: CONFIG.date,
    lastUpdated: now.format("hh:mm A, DD MMMM YYYY"),
    venues: dedupedResult
  };

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(output, null, 2));
  console.log(`✅ Done: ${dedupedResult.length} shows → ${filePath}`);
})();
