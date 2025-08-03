// Required packages: axios, fs/promises, p-limit
// Install via: npm install axios p-limit

const axios = require('axios');
const fs = require('fs/promises');
const path = require('path');
const pLimit = require('p-limit');

const CONFIG = {
  DATE: '2025-08-13',
  TARGET_MOVIE_ID: 240770,
  ZIP_FILE: 'zipcodessmall.txt',
  OUTPUT_FILE: 'newSeatData.json',
  ERROR_FILE: 'errored_seats.json',
  AUTHORIZATION_TOKEN: '<your-auth-token>',
  SESSION_ID: '<your-session-id>',
  CONCURRENCY: 10
};

const HEADERS = {
  authority: 'tickets.fandango.com',
  accept: 'application/json',
  Authorization: CONFIG.AUTHORIZATION_TOKEN,
  'X-Fd-Sessionid': CONFIG.SESSION_ID,
  Referer: 'https://tickets.fandango.com/mobileexpress/seatselection',
  'User-Agent': 'Mozilla/5.0'
};

async function getTheaters(zip, date) {
  const url = 'https://www.fandango.com/napi/theaterswithshowtimes';
  const params = {
    zipCode: zip,
    date,
    page: 1,
    limit: 40,
    filter: 'open-theaters',
    filterEnabled: 'true'
  };
  try {
    const res = await axios.get(url, { params });
    return res.data;
  } catch (err) {
    console.warn(`ZIP ${zip} failed: ${err.message}`);
    return {};
  }
}

function extractLanguage(amenities) {
  const known = ['English', 'Hindi', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi', 'Gujarati', 'Marathi', 'Bengali'];
  for (const item of amenities) {
    const lower = item.toLowerCase();
    for (const lang of known) {
      if (lower.includes(`${lang.toLowerCase()} language`)) return lang;
      if (lower.includes(lang.toLowerCase())) return lang;
    }
  }
  return 'Unknown';
}

function extractFormat(amenities, defFormat) {
  const keywords = ['RPX', 'D-Box', 'IMAX', 'EMX', 'Sony Digital Cinema', '4DX', 'ScreenX', 'Dolby Cinema'];
  for (const keyword of keywords) {
    if (amenities.some(a => a.toLowerCase().includes(keyword.toLowerCase()))) return keyword;
  }
  return defFormat;
}

function prepareShowtimes(movie) {
  const result = [];
  for (const variant of movie.variants || []) {
    const format = variant.formatName || 'Standard';
    for (const ag of variant.amenityGroups || []) {
      const amenities = ag.amenities?.map(a => a.name) || [];
      const language = extractLanguage(amenities);
      const fmt = extractFormat(amenities, format);
      for (const s of ag.showtimes || []) {
        result.push({
          showtime_id: s.id,
          date: s.ticketingDate,
          format: fmt,
          language
        });
      }
    }
  }
  return result;
}

async function fetchSeat(show) {
  const url = `https://tickets.fandango.com/checkoutapi/showtimes/v2/${show.showtime_id}/seat-map/`;
  try {
    const res = await axios.get(url, { headers: HEADERS });
    const d = res.data.data || {};
    const area = (d.areas || [{}])[0];
    const available = d.totalAvailableSeatCount || 0;
    const total = d.totalSeatCount || 0;
    const sold = total - available;
    show.totalSeatSold = sold;
    show.occupancy = total ? +(sold / total * 100).toFixed(2) : 0.0;
    show.totalAvailableSeatCount = available;
    show.totalSeatCount = total;
    show.adultTicketPrice = 0.0;
    show.grossRevenueUSD = 0.0;

    const ticketInfo = area.ticketInfo || [];
    for (const t of ticketInfo) {
      if (t.desc?.toLowerCase().includes('adult')) {
        const price = parseFloat(t.price || '0');
        show.adultTicketPrice = price;
        show.grossRevenueUSD = +(price * sold).toFixed(2);
        break;
      }
    }
  } catch (err) {
    show.error = { status: err.response?.status || 0, message: err.message };
  }
}

async function main() {
  const zipcodes = (await fs.readFile(CONFIG.ZIP_FILE, 'utf-8')).split('\n').filter(Boolean);
  console.log(`Loaded ${zipcodes.length} ZIPs.`);

  const allShowtimes = [];
  for (const zip of zipcodes) {
    const data = await getTheaters(zip, CONFIG.DATE);
    const theaters = data.theaters || [];
    for (const t of theaters) {
      for (const m of t.movies || []) {
        if (m.id === CONFIG.TARGET_MOVIE_ID) {
          const showtimes = prepareShowtimes(m);
          for (const s of showtimes) {
            allShowtimes.push({
              state: t.state,
              city: t.city,
              zip: t.zip,
              theater_name: t.name,
              chainName: t.chainName,
              chainCode: t.chainCode,
              ...s
            });
          }
        }
      }
    }
  }

  console.log(`Found ${allShowtimes.length} showtimes.`);
  const limit = pLimit(CONFIG.CONCURRENCY);
  await Promise.all(allShowtimes.map(show => limit(() => fetchSeat(show))));

  const cleaned = allShowtimes.filter(s => !s.error);
  const errored = allShowtimes.filter(s => s.error);

  await fs.writeFile(CONFIG.OUTPUT_FILE, JSON.stringify(cleaned, null, 2));
  await fs.writeFile(CONFIG.ERROR_FILE, JSON.stringify(errored, null, 2));

  console.log(`✅ Saved ${cleaned.length} to ${CONFIG.OUTPUT_FILE}`);
  console.log(`⚠️  Errors: ${errored.length} entries saved to ${CONFIG.ERROR_FILE}`);
}

main().catch(console.error);
