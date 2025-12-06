const fs = require("fs");
const crypto = require("crypto");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

const KEY_FILE = "districttrack/key.json";
const DISTRICT_DIR = "districttrack";
const ROTATE_INTERVAL_DAYS = 99999999999999; // change if needed

function loadKeyData() {
  if (!fs.existsSync(KEY_FILE)) {
    console.log("🔑 No key found — generating new one.");
    const keyData = {
      key: crypto.randomBytes(32).toString("hex"),
      lastRotated: dayjs().toISOString()
    };
    fs.mkdirSync(DISTRICT_DIR, { recursive: true });
    fs.writeFileSync(KEY_FILE, JSON.stringify(keyData, null, 2));
    return keyData;
  }
  return JSON.parse(fs.readFileSync(KEY_FILE, "utf-8"));
}

function saveKeyData(keyData) {
  fs.writeFileSync(KEY_FILE, JSON.stringify(keyData, null, 2));
}

function encryptData(key, data) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-cbc", Buffer.from(key, "hex"), iv);
  let encrypted = cipher.update(JSON.stringify(data), "utf8", "hex");
  encrypted += cipher.final("hex");
  return { iv: iv.toString("hex"), data: encrypted };
}

function decryptData(key, encrypted) {
  const iv = Buffer.from(encrypted.iv, "hex");
  const decipher = crypto.createDecipheriv("aes-256-cbc", Buffer.from(key, "hex"), iv);
  let decrypted = decipher.update(encrypted.data, "hex", "utf8");
  decrypted += decipher.final("utf8");
  return JSON.parse(decrypted);
}

function rotateKeyIfNeeded() {
  let keyData = loadKeyData();
  const lastRotated = dayjs(keyData.lastRotated);
  const now = dayjs();

  if (now.diff(lastRotated, "day") >= ROTATE_INTERVAL_DAYS) {
    console.log(`🔄 Rotating key after ${now.diff(lastRotated, "day")} days...`);
    const oldKey = keyData.key;
    const newKey = crypto.randomBytes(32).toString("hex");

    const files = fs.readdirSync(DISTRICT_DIR).filter(f => f.endsWith(".json") && f !== "key.json");
    for (const file of files) {
      const filePath = `${DISTRICT_DIR}/${file}`;
      try {
        const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        const decrypted = decryptData(oldKey, content);
        const reEncrypted = encryptData(newKey, decrypted);
        fs.writeFileSync(filePath, JSON.stringify(reEncrypted, null, 2));
        console.log(`♻ Re-encrypted: ${file}`);
      } catch (e) {
        console.error(`❌ Failed to re-encrypt ${file}: ${e.message}`);
      }
    }

    keyData = { key: newKey, lastRotated: now.toISOString() };
    saveKeyData(keyData);
    console.log(`✅ Key rotation complete.`);
  } else {
    console.log(`⏩ Key not due for rotation. Last rotated ${now.diff(lastRotated, "day")} days ago.`);
  }

  return keyData.key;
}

// ------------------ TRACKER LOGIC ------------------
const todayIST = dayjs().tz("Asia/Kolkata");

// List of movies
const MOVIES = [

     {
    name: "Param Sundari Hindi",
    language: "hindi",
    releaseDate: "2025-08-29",
    movieCode: "qVNQxUQJl9",
    contentId: "186420",
    cutoffMins: 100
  },
    {
    name: "War 2 Hindi",
    language: "hindi",
    releaseDate: "2025-08-14",
    movieCode: "sbGuGSyELy",
    contentId: "161358",
    cutoffMins: 100
  },
  
    {
    name: "Hridayapoorvam Malayalam",
    language: "malayalam",
    releaseDate: "2025-08-28",
    contentId: "202567",
    movieCode: "A4r89MNoYJ",
    cutoffMins: 100
  },
];


// Main tracker for a single movie
async function runTrackerForMovie(CONFIG, key) {
  console.log(`\n🎯 Tracking ${CONFIG.name} — Date: ${CONFIG.date}`);
  const now = dayjs().tz("Asia/Kolkata");
  const folder = `${DISTRICT_DIR}/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // Load old data if exists
  if (fs.existsSync(filePath)) {
    try {
      const existing = decryptData(key, JSON.parse(fs.readFileSync(filePath, "utf-8")));
      for (const v of existing.venues || []) {
        const sig = `${v.venue}_${v.time}`;
        seenKeys.add(sig);
        result.push(v);
      }
    } catch (e) {
      console.error(`⚠ Failed to decrypt existing file for ${CONFIG.name}: ${e.message}`);
    }
  }

  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json", {
    headers: { "User-Agent": "BOXOFFICE24" }
  }).then(res => res.json());

  const tasks = cities.map(city => (async () => {
    if (!city.citycode) return;

    const url = `https://district.text2025mail.workers.dev/?city=${city.citycode}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;
    console.log(`🌐 Requesting: ${url}`);

    try {
      const res = await fetch(url, { headers: { "User-Agent": "BOXOFFICE24" } });
      const json = await res.json();

      const allowedLangs = json?.meta?.movie?.languages || [];
      const expectedLang = CONFIG.language?.toLowerCase();
      if (!json?.meta?.showDates?.includes(CONFIG.date)) return;
      if (expectedLang && !allowedLangs.map(l => l.toLowerCase()).includes(expectedLang)) return;

      const cinemas = [...(json.pageData?.nearbyCinemas || []), ...(json.pageData?.farCinemas || [])];
      for (const cinema of cinemas) {
        const venueName = cinema.cinemaInfo.name;
        const venueAddress = cinema.cinemaInfo.address || "";
        const shows = cinema.sessions || [];

        for (const session of shows) {
          const showTime = dayjs(session.showTime).tz("Asia/Kolkata");
          const minutesLeft = showTime.diff(now, "minute");
          if (minutesLeft >= CONFIG.cutoffMins) continue;

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
            }
          } else {
            seenKeys.add(sig);
            result.push(newEntry);
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
    const keyStr = `${show.venue}__${show.address}__${show.time}__${show.audi}`;
    if (!uniqueShowsMap.has(keyStr)) {
      uniqueShowsMap.set(keyStr, show);
    } else {
      const existing = uniqueShowsMap.get(keyStr);
      if (show.gross > existing.gross || show.sold > existing.sold) {
        uniqueShowsMap.set(keyStr, show);
      }
    }
  }
  const dedupedResult = Array.from(uniqueShowsMap.values());

  const output = {
    date: CONFIG.date,
    lastUpdated: now.format("hh:mm A, DD MMMM YYYY"),
    venues: dedupedResult
  };

  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(encryptData(key, output), null, 2));
  console.log(`✅ ${CONFIG.name} — Shows stored: ${dedupedResult.length}`);
}
// Run all movies with single key rotation
async function runAllMovies(movies) {
  console.log("🎬 Starting tracker for multiple movies...");
  const key = rotateKeyIfNeeded();
  const now = dayjs().tz("Asia/Kolkata");

  for (const movie of movies) {
    const releaseDate = dayjs(movie.releaseDate).tz("Asia/Kolkata");

    // Skip movies that haven't released yet
    if (now.isBefore(releaseDate, "day")) {
      console.log(`⏩ Skipping ${movie.name} — releasing on ${releaseDate.format("DD MMM YYYY")}`);
      continue;
    }

    // On release day → run for release date
    // After release day → run for today
    const targetDate = now.isSame(releaseDate, "day")
      ? releaseDate
      : now;

    await runTrackerForMovie(
      { ...movie, date: targetDate.format("YYYY-MM-DD") },
      key
    );
  }
}

runAllMovies(MOVIES);
