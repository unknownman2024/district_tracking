const fs = require("fs");
const fetch = require("node-fetch");

const OUTPUT_FILE = "districtmovies.json";
const BACKUP_FILE = `backup_districtmovies_${Date.now()}.json`;
const API_URL = "https://paytmmovies.text2024mail.workers.dev";

// Parse city string into unique sorted array
function parseCities(cityString) {
  if (!cityString) return [];
  const cities = cityString
    .split(",")
    .map(c => c.trim())
    .filter(Boolean);
  return [...new Set(cities)]; // remove duplicates
}

// Load existing data if available
function loadExistingData() {
  if (fs.existsSync(OUTPUT_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(OUTPUT_FILE, "utf-8"));
    } catch (err) {
      console.error("⚠️ Error reading existing file, starting fresh:", err);
      return [];
    }
  }
  return [];
}

// Merge new movies into existing dataset with strict uniqueness
function mergeMovies(existing, fresh) {
  const map = new Map();

  // index existing by id+language
  existing.forEach(movie => {
    const key = `${movie.id}_${movie.language}`;
    map.set(key, movie);
  });

  // update/add fresh
  fresh.forEach(movie => {
    const key = `${movie.id}_${movie.language}`;

    if (map.has(key)) {
      // check if same movie name → update
      if (map.get(key).movie === movie.movie) {
        const cities = parseCities(movie.city);
        map.set(key, {
          ...movie,
          city: cities.join(", "),
          cityCount: cities.length
        });
      } else {
        // different movie name for same id+language → ignore
        console.warn(
          `⚠️ Skipped conflicting entry: id=${movie.id}, lang=${movie.language}, name=${movie.movie}`
        );
      }
    } else {
      // new entry → add
      const cities = parseCities(movie.city);
      map.set(key, {
        ...movie,
        city: cities.join(", "),
        cityCount: cities.length
      });
    }
  });

  return Array.from(map.values());
}

// Sort by city count (desc), then movie name (asc)
function sortMovies(movies) {
  return movies.sort((a, b) => {
    if (b.cityCount !== a.cityCount) {
      return b.cityCount - a.cityCount;
    }
    return a.movie.localeCompare(b.movie);
  });
}

async function main() {
  try {
    console.log("🌐 Fetching data from API...");
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`API fetch failed: ${res.status}`);
    const freshData = await res.json();

    console.log("📂 Loading existing movies...");
    const existingData = loadExistingData();

    console.log("🔄 Merging movies...");
    let merged = mergeMovies(existingData, freshData);

    console.log("📊 Sorting movies...");
    merged = sortMovies(merged);

    // Backup old file
    if (fs.existsSync(OUTPUT_FILE)) {
      fs.copyFileSync(OUTPUT_FILE, BACKUP_FILE);
      console.log(`📦 Backup saved as ${BACKUP_FILE}`);
    }

    console.log("💾 Saving to", OUTPUT_FILE);
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(merged, null, 2), "utf-8");

    console.log("✅ Done! Total movies:", merged.length);
  } catch (err) {
    console.error("❌ Error:", err.message);
  }
}

main();
