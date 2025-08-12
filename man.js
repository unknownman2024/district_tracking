const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

// ============================
// 🔐 Encryption Helpers
// ============================
const keyFile = path.join("districttrack", "key.json");
let AES_KEY;

function loadOrCreateKey() {
  if (fs.existsSync(keyFile)) {
    AES_KEY = Buffer.from(JSON.parse(fs.readFileSync(keyFile, "utf-8")).key, "hex");
  } else {
    AES_KEY = crypto.randomBytes(32); // 256-bit key
    fs.mkdirSync(path.dirname(keyFile), { recursive: true });
    fs.writeFileSync(keyFile, JSON.stringify({ key: AES_KEY.toString("hex") }, null, 2));
    console.log("🔑 New encryption key generated → districttrack/key.json");
  }
}

function encryptData(data) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-cbc", AES_KEY, iv);
  let encrypted = cipher.update(JSON.stringify(data), "utf8", "base64");
  encrypted += cipher.final("base64");
  return { iv: iv.toString("base64"), data: encrypted };
}

function decryptData(encObj) {
  const iv = Buffer.from(encObj.iv, "base64");
  const decipher = crypto.createDecipheriv("aes-256-cbc", AES_KEY, iv);
  let decrypted = decipher.update(encObj.data, "base64", "utf8");
  decrypted += decipher.final("utf8");
  return JSON.parse(decrypted);
}

// ============================
// 🔄 Key Rotation
// ============================
function rotateKey() {
  console.log("♻ Rotating encryption key...");
  const oldKey = AES_KEY;
  const newKey = crypto.randomBytes(32);

  const allFiles = [];
  fs.readdirSync("districttrack").forEach(dir => {
    const folderPath = path.join("districttrack", dir);
    if (fs.statSync(folderPath).isDirectory()) {
      fs.readdirSync(folderPath)
        .filter(f => f.endsWith(".json") && f !== "key.json")
        .forEach(file => allFiles.push(path.join(folderPath, file)));
    }
  });

  allFiles.forEach(filePath => {
    try {
      const enc = JSON.parse(fs.readFileSync(filePath, "utf-8"));
      // decrypt with old key
      const iv = Buffer.from(enc.iv, "base64");
      const decipher = crypto.createDecipheriv("aes-256-cbc", oldKey, iv);
      let decrypted = decipher.update(enc.data, "base64", "utf8");
      decrypted += decipher.final("utf8");
      const json = JSON.parse(decrypted);

      // encrypt with new key
      const ivNew = crypto.randomBytes(16);
      const cipher = crypto.createCipheriv("aes-256-cbc", newKey, ivNew);
      let encrypted = cipher.update(JSON.stringify(json), "utf8", "base64");
      encrypted += cipher.final("base64");

      fs.writeFileSync(filePath, JSON.stringify({ iv: ivNew.toString("base64"), data: encrypted }, null, 2));
      console.log(`🔄 Re-encrypted: ${filePath}`);
    } catch (err) {
      console.error(`❌ Failed to rotate ${filePath}: ${err.message}`);
    }
  });

  AES_KEY = newKey;
  fs.writeFileSync(keyFile, JSON.stringify({ key: AES_KEY.toString("hex") }, null, 2));
  console.log("✅ Key rotation complete!");
}

// ============================
// 📅 Date Setup
// ============================
const RELEASE_DATE = dayjs("2025-08-14").tz("Asia/Kolkata");
const todayIST = dayjs().tz("Asia/Kolkata");
let targetDate = todayIST.isBefore(RELEASE_DATE, "day") ? RELEASE_DATE : todayIST;

const CONFIG = {
  name: "MAN Hindi",
  language: "hindi",
  date: targetDate.format("YYYY-MM-DD"),
  contentId: "183788",
  movieCode: "2_WBDghspW",
  cutoffMins: 60
};

// ============================
// 🚀 Main Script
// ============================
(async () => {
  loadOrCreateKey();

  if (process.argv.includes("--rotate")) {
    rotateKey();
    return;
  }

  console.log(`🎯 Tracking date: ${CONFIG.date} (today: ${todayIST.format("YYYY-MM-DD")})`);

  const now = dayjs().tz("Asia/Kolkata");
  const folder = `districttrack/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  const seenKeys = new Set();
  const result = [];

  // Load existing data if available
  if (fs.existsSync(filePath)) {
    try {
      const existingEnc = JSON.parse(fs.readFileSync(filePath, "utf-8"));
      const existing = decryptData(existingEnc);
      for (const v of existing.venues || []) {
        seenKeys.add(`${v.venue}_${v.time}`);
        result.push(v);
      }
    } catch (err) {
      console.error(`⚠ Failed to load existing data: ${err.message}`);
    }
  }

  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json", {
    headers: { "User-Agent": "BOXOFFICE24" }
  }).then(res => res.json());

  const tasks = cities.map(city => (async () => {
    if (!city.citycode) return;
    const url = `https://district.text2026mail.workers.dev/?city=${city.citycode}&content_id=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;
    console.log(`🌐 Requesting: ${url}`);

    try {
      const res = await fetch(url, { headers: { "User-Agent": "BOXOFFICE24" } });
      const json = await res.json();

      const allowedLangs = json?.meta?.movie?.languages || [];
      const expectedLang = CONFIG.language?.toLowerCase();

      if (!json?.meta?.showDates?.includes(CONFIG.date)) {
        console.log(`⏭ Skipping ${city.RegionName} — date not in showDates`);
        return;
      }
      if (expectedLang && !allowedLangs.map(l => l.toLowerCase()).includes(expectedLang)) {
        console.log(`⛔ Skipping ${city.RegionName} — Expected "${CONFIG.language}"`);
        return;
      }

      const cinemas = [...(json.pageData?.nearbyCinemas || []), ...(json.pageData?.farCinemas || [])];
      for (const cinema of cinemas) {
        const venueName = cinema.cinemaInfo.name;
        const venueAddress = cinema.cinemaInfo.address || "";
        for (const session of cinema.sessions || []) {
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

          const existingIndex = result.findIndex(e => e.venue === venueName && e.time === timeStr && e.audi === (session.audi || ""));
          if (existingIndex !== -1) {
            const existing = result[existingIndex];
            if (newEntry.gross > existing.gross || newEntry.sold > existing.sold) {
              result[existingIndex] = newEntry;
              console.log(`🔁 Updated: [${city.RegionName}] ${venueName} → ${timeStr}`);
            }
          } else {
            seenKeys.add(`${venueName}_${timeStr}`);
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

  // Deduplicate
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

  // Save encrypted
  const output = {
    date: CONFIG.date,
    lastUpdated: now.format("hh:mm A, DD MMMM YYYY"),
    venues: dedupedResult
  };
  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(encryptData(output), null, 2));
  console.log(`✅ Done. Final shows: ${dedupedResult.length} → ${filePath}`);
})();
