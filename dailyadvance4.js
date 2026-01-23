const fs = require("fs");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

// Today +3 day (IST)
const DATE = dayjs().tz("Asia/Kolkata").add(4, "day").format("YYYY-MM-DD");
const DATECustom = "2025-09-25";

const API_URL = "https://districtvenues.text2025mail.workers.dev/?cinema_id={cid}&date={date}";
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

      const name = movie.name;
      const lang = session.lang || movie.lang || "";
      const format = session.scrnFmt || "";
      const formattedFormat = format ? format.replace(/-/g, " | ") : "";
      const key = formattedFormat ? `${name} [${formattedFormat} | ${lang}]` : `${name} | ${lang}`;

      // ---------- SUMMARY ----------
      if (!summary[key]) {
        summary[key] = {
          shows: 0, gross: 0, sold: 0, totalSeats: 0,
          venues: new Set(), cities: new Set(),
          fastfilling: 0, housefull: 0,
          details: {}, Chain_details: {}
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

      // ---------- DETAILED ----------
      if (!detailedOutput[key]) detailedOutput[key] = [];
      detailedOutput[key].push({
        city,
        state,
        venue: venue.name,
        chain,   // ✅ add this
        time: session.showTime 
          ? dayjs.utc(session.showTime).tz("Asia/Kolkata").format("hh:mm A")
          : "",
        audi: session.audi || "",
        totalSeats: total,
        available: avail,
        sold,
        gross,
        occupancy: total ? `${((sold / total) * 100).toFixed(2)}%` : "0%"
      });
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

  const nowIST = dayjs().tz("Asia/Kolkata");
  const formattedLastUpdated = nowIST.format("hh:mm A, DD MMMM YYYY");

  // Wrap detailed output — ✅ ADD THIS BLOCK
  const finalDetailed = {
    date: DATE,
    lastUpdated: formattedLastUpdated,
    ...detailedOutput
  };
  
// ---------- MERGE WITH EXISTING FILES ----------
const outDir = "./Daily Advance";
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

const outPath = `${outDir}/${DATE}.json`;
const detailedPath = `${outDir}/${DATE}_Detailed.json`;

let existingSummary = {};
let existingDetailed = {};

if (fs.existsSync(outPath)) {
  existingSummary = JSON.parse(fs.readFileSync(outPath, "utf-8"));
}

if (fs.existsSync(detailedPath)) {
  existingDetailed = JSON.parse(fs.readFileSync(detailedPath, "utf-8"));
}

// ---------- 1) MERGE DETAILED DATA ----------
for (const [movie, sessions] of Object.entries(finalDetailed)) {
  if (movie === "date" || movie === "lastUpdated") continue; // ✅ skip metadata

  if (!Array.isArray(sessions)) continue; // ✅ extra safety

  if (!existingDetailed[movie]) {
    existingDetailed[movie] = sessions;
  } else {
    const existingSessions = existingDetailed[movie];

    sessions.forEach(newSession => {
      const matchIndex = existingSessions.findIndex(
        s =>
          s.venue === newSession.venue &&
          s.time === newSession.time &&
          s.audi === newSession.audi
      );

      if (matchIndex !== -1) {
        existingSessions[matchIndex] = newSession;
      } else {
        existingSessions.push(newSession);
      }
    });

    const seen = new Set();
    existingDetailed[movie] = existingSessions.filter(s => {
      const key = `${s.venue}|${s.time}|${s.audi}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
}

// ---------- 2) REBUILD SUMMARY FROM MERGED DETAILED ----------
const rebuiltSummary = {};
for (const [movie, sessions] of Object.entries(existingDetailed)) {
  if (movie === "date" || movie === "lastUpdated") continue; // skip metadata

  if (!rebuiltSummary[movie]) {
    rebuiltSummary[movie] = {
      shows: 0, gross: 0, sold: 0, totalSeats: 0,
      venues: new Set(), cities: new Set(),
      fastfilling: 0, housefull: 0,
      details: {}, Chain_details: {}
    };
  }

  const msum = rebuiltSummary[movie];

  sessions.forEach(s => {
    const total = s.totalSeats || 0;
    const sold = s.sold || 0;
    const gross = s.gross || 0;
    const occupancy = total ? (sold / total) * 100 : 0;
    const fastfilling = occupancy >= 50 && occupancy < 98 ? 1 : 0;
    const housefull = occupancy >= 98 ? 1 : 0;

    msum.shows++;
    msum.gross += gross;
    msum.sold += sold;
    msum.totalSeats += total;
    msum.venues.add(s.venue);
    msum.cities.add(s.city);
    msum.fastfilling += fastfilling;
    msum.housefull += housefull;

    // city/state
    const detKey = `${s.city}|${s.state}`;
    if (!msum.details[detKey]) {
      msum.details[detKey] = {
        city: s.city,
        state: s.state,
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
    det.venues.add(s.venue);
    det.shows++;
    det.gross += gross;
    det.sold += sold;
    det.totalSeats += total;
    det.fastfilling += fastfilling;
    det.housefull += housefull;

    // chain
    if (!msum.Chain_details[s.chain]) {
      msum.Chain_details[s.chain] = {
        chain: s.chain,
        venues: new Set(),
        shows: 0,
        gross: 0,
        sold: 0,
        totalSeats: 0,
        fastfilling: 0,
        housefull: 0
      };
    }
    const cdet = msum.Chain_details[s.chain];
    cdet.venues.add(s.venue);
    cdet.shows++;
    cdet.gross += gross;
    cdet.sold += sold;
    cdet.totalSeats += total;
    cdet.fastfilling += fastfilling;
    cdet.housefull += housefull;
  });
}

// flatten rebuilt summary
const finalSummary = {};
for (const [movie, vals] of Object.entries(rebuiltSummary)) {
  finalSummary[movie] = {
    shows: vals.shows,
    gross: vals.gross,
    sold: vals.sold,
    totalSeats: vals.totalSeats,
    venues: vals.venues.size,
    cities: vals.cities.size,
    fastfilling: vals.fastfilling,
    housefull: vals.housefull,
    occupancy: vals.totalSeats ? +(vals.sold / vals.totalSeats * 100).toFixed(2) : 0,
    details: Object.values(vals.details).map(d => ({
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
    })),
    Chain_details: Object.values(vals.Chain_details).map(c => ({
      chain: c.chain,
      venues: c.venues.size,
      shows: c.shows,
      gross: c.gross,
      sold: c.sold,
      totalSeats: c.totalSeats,
      fastfilling: c.fastfilling,
      housefull: c.housefull,
      occupancy: c.totalSeats ? +(c.sold / c.totalSeats * 100).toFixed(2) : 0
    }))
  };
}

// ---------- 3) ADD METADATA ----------
finalSummary.date = DATE;
finalSummary.lastUpdated = formattedLastUpdated;
existingDetailed.date = DATE;
existingDetailed.lastUpdated = formattedLastUpdated;

// ---------- 4) SAVE ----------
fs.writeFileSync(outPath, JSON.stringify(finalSummary, null, 2), "utf-8");
fs.writeFileSync(detailedPath, JSON.stringify(existingDetailed, null, 2), "utf-8");

  console.log(`✅ Updated summary: ${outPath}`);
  console.log(`✅ Updated detailed: ${detailedPath}`);
}

main();
