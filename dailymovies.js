const fs = require("fs");
const fetch = require("node-fetch");

const OUTPUT_FILE = "districtmovies.json";
const API_URL = "https://paytmmovies.text2024mail.workers.dev";

// Helper: parse city string into array
function parseCities(cityString) {
  if (!cityString) return [];
  return cityString.split(",").map(c => c.trim()).filter(Boolean);
}

// Load existing data if file exists
function loadExistingData() {
  if (fs.existsSync(OUTPUT_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(OUTPUT_FILE, "utf-8"));
    } catch (err) {
      console.error("Error reading existing file, starting fresh:", err);
      return [];
    }
  }
  return [];
}

// Merge new movies into existing dataset
function mergeMovies(existing, fresh) {
  const map = new Map();

  // put existing in map first
  existing.forEach(movie => {
    map.set(`${movie.id}_${movie.language}`, movie);
  });

  // update/add fresh
  fresh.forEach(movie => {
    const key = `${movie.id}_${movie.language}`;
    map.set(key, movie);
  });

  // convert back to array
  return Array.from(map.values());
}

// Sort by number of cities (descending)
function sortMovies(movies) {
  return movies.sort((a, b) => {
    const countA = parseCities(a.city).length;
    const countB = parseCities(b.city).length;
    return countB - countA; // higher city count first
  });
}

async function main() {
  try {
    console.log("Fetching data from API...");
    const res = await fetch(API_URL);
    const freshData = await res.json();

    console.log("Loading existing movies...");
    const existingData = loadExistingData();

    console.log("Merging movies...");
    let merged = mergeMovies(existingData, freshData);

    console.log("Sorting by city count...");
    merged = sortMovies(merged);

    console.log("Saving to", OUTPUT_FILE);
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(merged, null, 2), "utf-8");

    console.log("✅ Done! Total movies:", merged.length);
  } catch (err) {
    console.error("❌ Error:", err);
  }
}

main();
