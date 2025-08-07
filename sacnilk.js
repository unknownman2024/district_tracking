const fs = require("fs");
const path = require("path");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");
dayjs.extend(utc);
dayjs.extend(timezone);

const BASE_URL = "https://www.sacnilk.com";
const MAIN_URL = `${BASE_URL}/metasection/box_office`;
const OUTPUT_DIR = "data";
const OUTPUT_FILE = path.join(OUTPUT_DIR, "data.json");
const HTML_DUMP = path.join(OUTPUT_DIR, "debug.html");

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR);
}

function normalizeTitle(title) {
  const cleaned = title.replace(/\b(19|20)\d{2}\b/, "");
  return cleaned.toLowerCase().replace(/[^a-z0-9]+/gi, " ").trim();
}

function cleanMovieTitle(title) {
  return title.replace(/\s+Box Office.*$/i, "").trim();
}

function getDayFromTitle(title) {
  const match = title.match(/Day\s+(\d+)/i);
  return match ? `Day ${match[1]}` : "Unknown Day";
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchHTML(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" }
  });
  if (!res.ok) throw new Error(`Failed to fetch ${url}`);
  return await res.text();
}

async function extractMovieLinks() {
  const html = await fetchHTML(MAIN_URL);
  fs.writeFileSync(HTML_DUMP, html); // ✅ Save full HTML dump for debugging

  const movieMap = {};
  const regex = /<a\s+href="(\/quicknews\/[^"]+)"\s+title="([^"]*Box Office Collection Day\s+\d+)"/gi;

  let match;
  while ((match = regex.exec(html))) {
    const href = match[1];
    const fullTitle = match[2].trim();

    const dayMatch = fullTitle.match(/^(.*?) Box Office Collection Day (\d+)/i);
    if (dayMatch) {
      const rawTitle = dayMatch[1].trim();
      const day = parseInt(dayMatch[2], 10);
      const normalized = normalizeTitle(rawTitle);

      if (!movieMap[normalized]) movieMap[normalized] = [];
      movieMap[normalized].push({
        name: fullTitle,
        link: BASE_URL + href,
        day
      });
    }
  }

  const finalMovies = [];
  Object.values(movieMap).forEach(entries => {
    entries.sort((a, b) => b.day - a.day);
    if (entries[0].day <= 30) {
      finalMovies.push(entries[0]);
    }
  });

  return finalMovies;
}

async function extractAmountCr(url) {
  try {
    const html = await fetchHTML(url);
    const hrIndex = html.indexOf('<hr id="hrstart">');
    if (hrIndex === -1) return null;

    const snippet = html.slice(hrIndex, hrIndex + 1000);
    const match = snippet.match(/around\s+([\d.]+)\s+Cr/i);
    if (match) return parseFloat(match[1]);
  } catch (e) {
    console.error("❌ Error fetching amount from:", url, e.message);
  }

  return null;
}

async function main() {
  console.log("🔍 Scraping Sacnilk without cheerio...");
  const movies = await extractMovieLinks();

  let existing = [];
  if (fs.existsSync(OUTPUT_FILE)) {
    try {
      existing = JSON.parse(fs.readFileSync(OUTPUT_FILE));
    } catch {
      console.warn("⚠️ Could not parse existing data.json, starting fresh.");
    }
  }

  const existingMap = {};
  for (const entry of existing) {
    existingMap[entry.movie] = entry.data;
  }

  for (const movie of movies) {
    const amount = await extractAmountCr(movie.link);
    const movieName = cleanMovieTitle(movie.name);

    if (!amount) {
      console.log(`⚠️ Failed to extract amount for ${movieName} → ${movie.link}`);
      continue;
    }

const now = dayjs().tz("Asia/Kolkata");
const dateStr = now.format("YYYY-MM-DD");
const timeStr = now.format("HH:mm:ss");


    const dataPoint = {
      date: dateStr,
      day: getDayFromTitle(movie.name),
      time: timeStr,
      amount_cr: amount
    };

    if (!existingMap[movieName]) existingMap[movieName] = [];

    const currentHour = now.format("HH");
const isDuplicate = existingMap[movieName].some(
  d => d.date === dataPoint.date && d.time.startsWith(currentHour + ":")
);


    if (!isDuplicate) {
      console.log(`✅ ${movieName} (${dataPoint.day}) - ₹${amount} Cr`);
      existingMap[movieName].push(dataPoint);
    }

    await sleep(1000);
  }

  const finalOutput = Object.entries(existingMap).map(([movie, data]) => ({
    movie,
    data
  }));

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(finalOutput, null, 2));
  console.log(`📁 Saved ${finalOutput.length} movies to ${OUTPUT_FILE}`);
}

main().catch(err => {
  console.error("❌ Script crashed:", err.message);
  process.exit(1);
});
