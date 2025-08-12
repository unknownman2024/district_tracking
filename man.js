const fs = require("fs");
const crypto = require("crypto");
const fetch = require("node-fetch");
const dayjs = require("dayjs");
const utc = require("dayjs/plugin/utc");
const timezone = require("dayjs/plugin/timezone");

dayjs.extend(utc);
dayjs.extend(timezone);

const DISTRICT_DIR = "districttrack";

function loadKeyData(date) {
  const keyFile = `${DISTRICT_DIR}/${date}/key.json`;
  if (!fs.existsSync(keyFile)) {
    console.log(`🔑 No key found for ${date} — generating new one.`);
    const keyData = {
      key: crypto.randomBytes(32).toString("hex"),
      lastRotated: dayjs().toISOString()
    };
    fs.mkdirSync(`${DISTRICT_DIR}/${date}`, { recursive: true });
    fs.writeFileSync(keyFile, JSON.stringify(keyData, null, 2));
    return keyData;
  }
  return JSON.parse(fs.readFileSync(keyFile, "utf-8"));
}

function saveKeyData(date, keyData) {
  const keyFile = `${DISTRICT_DIR}/${date}/key.json`;
  fs.writeFileSync(keyFile, JSON.stringify(keyData, null, 2));
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


// ------------------ TRACKER LOGIC ------------------
const todayIST = dayjs().tz("Asia/Kolkata");

// List of movies
const MOVIES = [
  {
    name: "MAN Hindi",
    language: "hindi",
    releaseDate: "2025-08-12",
    contentId: "183788",
    movieCode: "2_WBDghspW",
    cutoffMins: 60
  },
    {
    name: "Saiyaara Hindi",
    language: "hindi",
    releaseDate: "2025-07-18",
    contentId: "196147",
    movieCode: "K5ih5j~m7F",
    cutoffMins: 60
  },
  {
    name: "Coolie Tamil",
    language: "tamil",
    releaseDate: "2025-08-14",  
    contentId: "112233",
    movieCode: "4_QWEabcDE",
    cutoffMins: 60
  },
  {
    name: "War 2 Hindi",
    language: "hindi",
    releaseDate: "2025-08-14",
    movieCode: "sbGuGSyELy",
    contentId: "161358",
    cutoffMins: 60
  },
  {
    name: "Coolie Hindi",
    language: "hindi",
    releaseDate: "2025-08-14",
    movieCode: "lgqLlP0Wf6",
    contentId: "201522",
    cutoffMins: 60
  },
    {
    name: "War 2 Telugu",
    language: "telugu",
    releaseDate: "2025-08-14",
    movieCode: "Vce5NbdeI_",
    contentId: "161358",
    cutoffMins: 60
  },
  {
    name: "Coolie Telugu",
    language: "telugu",
    releaseDate: "2025-08-14",
    movieCode: "rF_IgPQApY",
    contentId: "172677",
    cutoffMins: 60
  },
];


// Main tracker for a single movie 
async function runTrackerForMovie(CONFIG) {
  console.log(`\n🎯 Tracking ${CONFIG.name} — Date: ${CONFIG.date}`);
  const nowIST = dayjs().tz("Asia/Kolkata");
  const folder = `${DISTRICT_DIR}/${CONFIG.date}`;
  const filePath = `${folder}/${CONFIG.movieCode}_${CONFIG.contentId}.json`;

  // Step 1: Load old key & old data
  const oldKeyData = loadKeyData(CONFIG.date);
  let result = [];

  if (fs.existsSync(filePath)) {
    try {
      const existing = decryptData(oldKeyData.key, JSON.parse(fs.readFileSync(filePath, "utf-8")));
      result = existing.venues || [];
    } catch (e) {
      console.error(`⚠ Failed to decrypt existing file for ${CONFIG.name}: ${e.message}`);
    }
  }

  // Step 2: Fetch latest data
  const cities = await fetch("https://boxoffice24.pages.dev/TrackIndia/matchedcities.json", {
    headers: { "User-Agent": "BOXOFFICE24" }
  }).then(res => res.json());

  const tasks = cities.map(city => (async () => {
    if (!city.citycode) return;

    const url = `https://district.text2026mail.workers.dev/?city=${city.citycode}&contentId=${CONFIG.contentId}&date=${CONFIG.date}&movieCode=${CONFIG.movieCode}`;
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
          const minutesLeft = showTime.diff(nowIST, "minute");
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

          const existingIndex = result.findIndex(
            e => e.venue === venueName && e.time === timeStr && e.audi === (session.audi || "")
          );

          if (existingIndex !== -1) {
            const existing = result[existingIndex];
            if (newEntry.gross > existing.gross || newEntry.sold > existing.sold) {
              result[existingIndex] = newEntry;
            }
          } else {
            result.push(newEntry);
          }
        }
      }
    } catch (err) {
      console.error(`❌ ${city.RegionName} failed: ${err.message}`);
    }
  })());

  await Promise.all(tasks);

  // Step 3: Deduplicate
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

  // Step 4: Always generate a new key
  const newKeyData = {
    key: crypto.randomBytes(32).toString("hex"),
    lastRotated: nowIST.toISOString()
  };

  // Step 5: Encrypt with new key
  const output = {
    date: CONFIG.date,
    lastUpdated: nowIST.format("hh:mm A, DD MMMM YYYY"),
    venues: dedupedResult
  };
  fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(encryptData(newKeyData.key, output), null, 2));

  // Step 6: Save new key
  saveKeyData(CONFIG.date, newKeyData);

  console.log(`✅ ${CONFIG.name} — Shows stored: ${dedupedResult.length}`);
}

// Updated runAllMovies — IST safe
async function runAllMovies(movies) {
  console.log("🎬 Starting tracker for multiple movies...");
  const nowIST = dayjs().tz("Asia/Kolkata").startOf("day");

  for (const movie of movies) {
    const releaseDateIST = dayjs.tz(movie.releaseDate, "Asia/Kolkata").startOf("day");

    if (nowIST.isBefore(releaseDateIST)) {
      console.log(`⏩ Skipping ${movie.name} — releasing on ${releaseDateIST.format("DD MMM YYYY")}`);
      continue;
    }

    const targetDateIST = nowIST.isSame(releaseDateIST, "day")
      ? releaseDateIST
      : nowIST;

    await runTrackerForMovie(
      { ...movie, date: targetDateIST.format("YYYY-MM-DD") }
    );
  }
}


runAllMovies(MOVIES);
