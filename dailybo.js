const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

// Today +0 day (IST)
const DATE = dayjs().tz("Asia/Kolkata").add(0, "day").format("YYYY-MM-DD");

const API_URL = "https://districtvenues.text2026mail.workers.dev/?cinema_id={cid}&date={date}";
const VENUES = JSON.parse(fs.readFileSync("districtvenues.json", "utf-8"));

// ---- Helpers ----
function formatState(stateStr) {
  if (!stateStr || typeof stateStr !== "string") return "Unknown";
  return stateStr.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatChain(chainStr) {
  if (!chainStr || typeof chainStr !== "string") return "Unknown";
  return chainStr.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---- Fetch per cinema ----
async function fetchVenueData(venue) {
  const url = API_URL.replace("{cid}", venue.id).replace("{date}", DATE);
  const cid = venue.id;
  try {
    console.log(`➡️ Fetching cinema_id=${cid} (${venue.name})...`);
    const resp = await fetch(url, { timeout: 20000 });
    if (!resp.ok) {
      console.log(`⚠️ Failed: cinema_id=${cid} (status=${resp.status})`);
      return null;
    }
    const data = await resp.json();

    // check if DATE available
    const sessionDates = (data?.data?.sessionDates) || [];
    if (!sessionDates.includes(DATE)) {
      console.log(`⏭️ Skipped: cinema_id=${cid} (date ${DATE} not available)`);
      return null;
    }

    console.log(`✅ Success: cinema_id=${cid}`);
    return { venue, data };
  } catch (err) {
    console.log(`❌ Error for cinema_id=${cid}: ${err.message}`);
    return null;
  }
}

// ---- Main ----
async function main() {
  const summary = {};
  const detailedOutput = {};

  // Current IST time
  const now = dayjs().tz("Asia/Kolkata");

  // -------- Load old data (to preserve shows) --------
  const outDir = "./Daily Boxoffice";
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  const detailedPath = `${outDir}/${DATE}_Detailed.json`;
  let oldDetailed = {};
  if (fs.existsSync(detailedPath)) {
    try {
      oldDetailed = JSON.parse(fs.readFileSync(detailedPath, "utf-8"));
    } catch (e) {
      console.log("⚠️ Failed to parse old detailed file:", e.message);
    }
  }

  const results = await Promise.all(VENUES.map(fetchVenueData));

  for (const res of results) {
    if (!res) continue;
    const { venue, data } = res;

    const city = venue.city;
    const state = formatState(venue.state);
    const chain = formatChain(venue.chainKey);
    const v_id = venue.id;

    const moviesMap = {};
    (data.meta?.movies || []).forEach((m) => (moviesMap[m.id] = m));

    for (const session of data.pageData?.sessions || []) {
      const movie = moviesMap[session.mid];
      if (!movie) continue;

      // --- Minutes Left Logic ---
      const showTime = dayjs.utc(session.showTime).tz("Asia/Kolkata");
      const minutesLeft = showTime.diff(now, "minute");

      // cutoff check (example: 200 mins)
      const cutoffMins = 200;
      if (minutesLeft >= cutoffMins) continue;

      const name = movie.name;
      const lang = session.lang || movie.lang || "";
      const key = `${name} | ${lang}`;

      // ---------- SUMMARY ----------
      if (!summary[key]) {
        summary[key] = {
          shows: 0,
          gross: 0,
          sold: 0,
          totalSeats: 0,
          venues: new Set(),
          cities: new Set(),
          fastfilling: 0,
          housefull: 0,
          details: {},
          Chain_details: {}
        };
      }
      const msum = summary[key];

      const total = session.total || 0;
      const avail = session.avail || 0;
      const sold = total - avail;

      // gross from areas
      let gross = 0;
      (session.areas || []).forEach((a) => {
        gross += (a.sTotal - a.sAvail) * (a.price || 0);
      });

      const occupancy = total ? (sold / total) * 100 : 0;
      const fastfilling = occupancy >= 50 && occupancy < 98 ? 1 : 0;
      const housefull = occupancy >= 98 ? 1 : 0;

      // update totals
      msum.shows++;
      msum.gross += gross;
      msum.sold += sold;
      msum.totalSeats += total;
      msum.venues.add(v_id);
      msum.cities.add(city);
      msum.fastfilling += fastfilling;
      msum.housefull += housefull;

      // ---- City/State details update ----
      const detKey = `${city}|${state}`;
      if (!msum.details[detKey]) {
        msum.details[detKey] = {
          city,
          state,
          venues: new Set(),
          shows: 0,
          gross: 0,
          sold: 0,
          totalSeats: 0,
          fastfilling: 0,
          housefull: 0
        };
      }
      const det = msum.details[detKey];
      det.venues.add(v_id);
      det.shows++;
      det.gross += gross;
      det.sold += sold;
      det.totalSeats += total;
      det.fastfilling += fastfilling;
      det.housefull += housefull;

      // ---- Chain details update ----
      if (!msum.Chain_details[chain]) {
        msum.Chain_details[chain] = {
          chain,
          venues: new Set(),
          shows: 0,
          gross: 0,
          sold: 0,
          totalSeats: 0,
          fastfilling: 0,
          housefull: 0
        };
      }
      const cdet = msum.Chain_details[chain];
      cdet.venues.add(v_id);
      cdet.shows++;
      cdet.gross += gross;
      cdet.sold += sold;
      cdet.totalSeats += total;
      cdet.fastfilling += fastfilling;
      cdet.housefull += housefull;

      // ---------- DETAILED (with update logic) ----------
      if (!detailedOutput[key]) detailedOutput[key] = oldDetailed[key] ? [...oldDetailed[key]] : [];

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
  e => e.venue === venue.name && e.time === timeStr && e.audi === (session.audi || "")
);

if (existingIndex !== -1) {
  // ✅ Always update with latest values
  detailedOutput[key][existingIndex] = newEntry;
} else {
  detailedOutput[key].push(newEntry);
}
    }
  }

  // ---------- FINALIZE SUMMARY ----------
  const output = {};
  for (const [movie, vals] of Object.entries(summary)) {
    const out = {
      shows: vals.shows,
      gross: vals.gross,
      sold: vals.sold,
      totalSeats: vals.totalSeats,
      venues: vals.venues.size,
      cities: vals.cities.size,
      fastfilling: vals.fastfilling,
      housefull: vals.housefull,
      occupancy: vals.totalSeats ? +(vals.sold / vals.totalSeats * 100).toFixed(2) : 0,
      details: [],
      Chain_details: []
    };

    for (const d of Object.values(vals.details)) {
      out.details.push({
        city: d.city,
        state: d.state,
        venues: d.venues.size,
        shows: d.shows,
        gross: d.gross,
        sold: d.sold,
        totalSeats: d.totalSeats,
        fastfilling: d.fastfilling,
        housefull: d.housefull,
        occupancy: d.totalSeats ? +(d.sold / d.totalSeats * 100).toFixed(2) : 0
      });
    }

    for (const d of Object.values(vals.Chain_details)) {
      out.Chain_details.push({
        chain: d.chain,
        venues: d.venues.size,
        shows: d.shows,
        gross: d.gross,
        sold: d.sold,
        totalSeats: d.totalSeats,
        fastfilling: d.fastfilling,
        housefull: d.housefull,
        occupancy: d.totalSeats ? +(d.sold / d.totalSeats * 100).toFixed(2) : 0
      });
    }

    output[movie] = out;
  }

  // Add metadata
  const nowIST = dayjs().tz("Asia/Kolkata");
  const formattedLastUpdated = nowIST.format("hh:mm A, DD MMMM YYYY");

  // Wrap summary output
  const finalSummary = {
    date: DATE,
    lastUpdated: formattedLastUpdated,
    ...output
  };

  // Wrap detailed output
  const finalDetailed = {
    date: DATE,
    lastUpdated: formattedLastUpdated,
    ...detailedOutput
  };

  // ---------- SAVE FILES ----------
  const outPath = `${outDir}/${DATE}.json`;
  fs.writeFileSync(outPath, JSON.stringify(finalSummary, null, 2), "utf-8");

  fs.writeFileSync(detailedPath, JSON.stringify(finalDetailed, null, 2), "utf-8");

  console.log(`✅ Saved summary: ${outPath}`);
  console.log(`✅ Saved detailed: ${detailedPath}`);
}

main();
