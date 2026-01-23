const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

// ---- DATE SETUP (IST) ----
const nowIST = dayjs().tz("Asia/Kolkata");
const DATE = nowIST.format("YYYY-MM-DD");
const MONTH_YEAR = nowIST.format("MM-YYYY");

// ---- PATHS ----
const outDir = "./Daily Boxoffice";
const logsDir = `${outDir}/logs`;

if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
if (!fs.existsSync(logsDir)) fs.mkdirSync(logsDir, { recursive: true });

const detailedPath = `${outDir}/${DATE}_Detailed.json`;
const summaryPath  = `${outDir}/${DATE}.json`;
const monthlyLogPath = `${logsDir}/${MONTH_YEAR}.json`;

// ---- CONFIG ----
const API_URL = "https://districtvenues.text2026mail.workers.dev/?cinema_id={cid}&date={date}";
const VENUES = JSON.parse(fs.readFileSync("districtvenues.json", "utf-8"));
const CUTOFF_MINS = 200;

// ------------ HELPERS ------------
function formatState(stateStr) {
  if (!stateStr || typeof stateStr !== "string") return "Unknown";
  return stateStr.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// Your rounding rule
function roundToHourLabel(timeObj) {
  const mins = timeObj.minute();
  let hour = timeObj.hour();
  if (mins > 45) hour += 1;
  return dayjs(timeObj).hour(hour).minute(0).format("hA");
}

// ------------ FETCH PER CINEMA ------------
async function fetchVenueData(venue) {
  const url = API_URL.replace("{cid}", venue.id).replace("{date}", DATE);
  try {
    const resp = await fetch(url, { timeout: 20000 });
    if (!resp.ok) return null;

    const data = await resp.json();
    const sessionDates = data?.data?.sessionDates || [];
    if (!sessionDates.includes(DATE)) return null;

    return { venue, data };
  } catch {
    return null;
  }
}

// ------------ MAIN ------------
async function main() {

  // ---- LOAD OLD DETAILED (NEVER DELETE SHOWS) ----
  let detailedOutput = {};
  if (fs.existsSync(detailedPath)) {
    try {
      detailedOutput = JSON.parse(fs.readFileSync(detailedPath, "utf-8"));
    } catch {
      detailedOutput = {};
    }
  }

  const results = await Promise.all(VENUES.map(fetchVenueData));

  // ------------ UPDATE DETAILED FROM LIVE API ------------
  for (const res of results) {
    if (!res) continue;
    const { venue, data } = res;

    const city = venue.city;
    const state = formatState(venue.state);

    const moviesMap = {};
    (data.meta?.movies || []).forEach(m => (moviesMap[m.id] = m));

    for (const session of data.pageData?.sessions || []) {
      const movie = moviesMap[session.mid];
      if (!movie) continue;

      const showTime = dayjs.utc(session.showTime).tz("Asia/Kolkata");
      const minutesLeft = showTime.diff(nowIST, "minute");
      if (minutesLeft >= CUTOFF_MINS) continue;

      const name = movie.name;
      const lang = session.lang || movie.lang || "";
      const key = `${name} | ${lang}`;

      if (!detailedOutput[key]) detailedOutput[key] = [];

      const total = session.total || 0;
      const avail = session.avail || 0;
      const sold = total - avail;

      let gross = 0;
      (session.areas || []).forEach(a => {
        gross += (a.sTotal - a.sAvail) * (a.price || 0);
      });

      const timeStr = showTime.format("hh:mm A");

      const newEntry = {
        city,
        state,
        venue: venue.name,
        time: timeStr,
        audi: session.audi || "",
        totalSeats: total,
        available: avail,
        sold,
        gross,
        occupancy: total ? `${((sold / total) * 100).toFixed(2)}%` : "0%",
        minsLeft: minutesLeft
      };

      const existingIndex = detailedOutput[key].findIndex(
        e => e.venue === venue.name &&
             e.time === timeStr &&
             e.audi === (session.audi || "")
      );

      if (existingIndex !== -1) {
        detailedOutput[key][existingIndex] = newEntry;
      } else {
        detailedOutput[key].push(newEntry);
      }
    }
  }

  // ------------ REBUILD SUMMARY + CITY FROM DETAILED ------------
  const summary = {};

  for (const [movieKey, shows] of Object.entries(detailedOutput)) {
    if (movieKey === "date" || movieKey === "lastUpdated") continue;
    if (!Array.isArray(shows)) continue;

    summary[movieKey] = {
      shows: 0,
      gross: 0,
      sold: 0,
      totalSeats: 0,
      venues: new Set(),
      cities: new Set(),
      fastfilling: 0,
      housefull: 0,
      cityDetails: {}
    };

    for (const s of shows) {
      const total = Number(s.totalSeats || 0);
      const sold = Number(s.sold || 0);
      const gross = Number(s.gross || 0);
      const occ = total ? (sold / total) * 100 : 0;

      summary[movieKey].shows++;
      summary[movieKey].gross += gross;
      summary[movieKey].sold += sold;
      summary[movieKey].totalSeats += total;
      summary[movieKey].venues.add(s.venue);
      summary[movieKey].cities.add(s.city);

      if (occ >= 50 && occ < 98) summary[movieKey].fastfilling++;
      if (occ >= 98) summary[movieKey].housefull++;

      const cityStateKey = `${s.city} | ${s.state}`;

      if (!summary[movieKey].cityDetails[cityStateKey]) {
        summary[movieKey].cityDetails[cityStateKey] = {
          city: s.city,
          state: s.state,
          shows: 0,
          gross: 0,
          sold: 0,
          totalSeats: 0,
          fastfilling: 0,
          housefull: 0
        };
      }

      const c = summary[movieKey].cityDetails[cityStateKey];

      c.shows++;
      c.gross += gross;
      c.sold += sold;
      c.totalSeats += total;
      if (occ >= 50 && occ < 98) c.fastfilling++;
      if (occ >= 98) c.housefull++;
    }
  }

  // ------------ FINAL SUMMARY OBJECT ------------
  const finalSummaryData = {};
  for (const [movie, vals] of Object.entries(summary)) {
    finalSummaryData[movie] = {
      shows: vals.shows,
      gross: +vals.gross.toFixed(2),
      sold: vals.sold,
      totalSeats: vals.totalSeats,
      venues: vals.venues.size,
      cities: vals.cities.size,
      fastfilling: vals.fastfilling,
      housefull: vals.housefull,
      occupancy: vals.totalSeats
        ? +(vals.sold / vals.totalSeats * 100).toFixed(2)
        : 0,
      details: Object.values(vals.cityDetails).map(d => {
        const cityVenues = new Set();

        // collect venues for this city
        detailedOutput[movie].forEach(s => {
          if (s.city === d.city && s.state === d.state) {
            cityVenues.add(s.venue);
          }
        });

        return {
          city: d.city,
          state: d.state,
          shows: d.shows,
          gross: +d.gross.toFixed(2),
          sold: d.sold,
          venues: cityVenues.size,   // ✅ NEW FIELD
          fastfilling: d.fastfilling,
          housefull: d.housefull,
          occupancy: d.totalSeats
            ? +(d.sold / d.totalSeats * 100).toFixed(2)
            : 0
        };
      })
    };
  }

  // ------------ MONTHLY LOGS (TOP 50 ONLY) ------------
  let monthlyLogs = {};
  if (fs.existsSync(monthlyLogPath)) {
    try {
      monthlyLogs = JSON.parse(fs.readFileSync(monthlyLogPath, "utf-8"));
    } catch {
      monthlyLogs = {};
    }
  }

  const roundedLabel = roundToHourLabel(nowIST);
  const stamp = `${roundedLabel}, ${nowIST.format("DD/MM/YYYY")}`;

  const top50 = Object.entries(finalSummaryData)
    .sort((a, b) => b[1].gross - a[1].gross)
    .slice(0, 50);

  for (const [movie, data] of top50) {
    if (!monthlyLogs[movie]) monthlyLogs[movie] = {};
    // ✅ overwrite if same rounded hour exists
    monthlyLogs[movie][stamp] = {
      gross: data.gross,
      tickets: data.sold,
      occ: `${data.occupancy}%`,
      shows: data.shows
    };
  }

  // ------------ WRAP & SAVE FILES ------------
  // ---- REMOVE OLD META INSIDE DETAILED TO FORCE FRESH lastUpdated ----
  delete detailedOutput.date;
  delete detailedOutput.lastUpdated;

  const formattedLastUpdated = nowIST.format("hh:mm A, DD MMMM YYYY");

  const outputSummary = {
    date: DATE,
    lastUpdated: formattedLastUpdated,
    ...finalSummaryData
  };


  const outputDetailed = {
    date: DATE,
    lastUpdated: formattedLastUpdated,
    ...detailedOutput
  };

  fs.writeFileSync(summaryPath, JSON.stringify(outputSummary, null, 2), "utf-8");
  fs.writeFileSync(detailedPath, JSON.stringify(outputDetailed, null, 2), "utf-8");
  fs.writeFileSync(monthlyLogPath, JSON.stringify(monthlyLogs, null, 2), "utf-8");
  console.log(`✅ Saved summary: ${summaryPath}`);
  console.log(`✅ Saved detailed: ${detailedPath}`);
  console.log(`✅ Updated logs: ${monthlyLogPath}`);
}

main();
