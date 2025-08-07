const cheerio = require("cheerio");
const fs = require("fs");
const path = require("path");

const BASE_URL = "https://www.sacnilk.com";
const MAIN_URL = `${BASE_URL}/metasection/box_office`;
const OUTPUT_DIR = "data";
const OUTPUT_FILE = path.join(OUTPUT_DIR, "data.json");

// Ensure output folder exists
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR);
}

function normalizeTitle(rawTitle) {
    const cleaned = rawTitle.replace(/\b(19|20)\d{2}\b/, '');
    return cleaned.toLowerCase().replace(/[^a-z0-9]+/gi, ' ').trim();
}

function cleanMovieTitle(title) {
    return title.replace(/\s+Box Office.*$/i, '').trim();
}

function getDayFromTitle(title) {
    const match = title.match(/Day\s+(\d+)/i);
    return match ? `Day ${match[1]}` : 'Unknown Day';
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchHTML(url) {
    const response = await fetch(url, {
        headers: {
            "User-Agent": "Mozilla/5.0"
        }
    });
    if (!response.ok) throw new Error(`Failed to fetch ${url}`);
    return await response.text();
}

async function extractMovieLinks() {
    const html = await fetchHTML(MAIN_URL);
    const $ = cheerio.load(html);
    const movieMap = {};

    $("div.relatednewssidemainshort a").each((i, el) => {
        const href = $(el).attr("href");
        const fullTitle = $(el).find("b").text().trim();

        if (href && /Box Office/i.test(fullTitle)) {
            const match = fullTitle.match(/^(.*?) Box Office Collection Day (\d+)/i);
            if (match) {
                const rawTitle = match[1].trim();
                const day = parseInt(match[2], 10);
                const normalized = normalizeTitle(rawTitle);

                if (!movieMap[normalized]) movieMap[normalized] = [];
                movieMap[normalized].push({
                    name: fullTitle,
                    link: BASE_URL + href,
                    day
                });
            }
        }
    });

    // Pick only highest day <= 10
    const finalMovies = [];
    Object.values(movieMap).forEach(entries => {
        entries.sort((a, b) => b.day - a.day);
        if (entries[0].day <= 10) {
            finalMovies.push(entries[0]);
        }
    });

    return finalMovies;
}

async function extractAmountCr(url) {
    const html = await fetchHTML(url);
    const $ = cheerio.load(html);
    const hr = $("#hrstart");

    if (hr.length === 0) return null;

    let textNode = hr[0].nextSibling;
    while (textNode && textNode.type !== "text") {
        textNode = textNode.nextSibling;
    }

    if (textNode && textNode.data) {
        const text = textNode.data.trim();
        const match = text.match(/around\s+([\d.]+)\s+Cr/i);
        if (match) return parseFloat(match[1]);
    }

    return null;
}

async function main() {
    console.log("🔍 Scraping latest Sacnilk box office data...");
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
        if (!amount) continue;

        const movieName = cleanMovieTitle(movie.name);
        const now = new Date();
        const dateStr = now.toISOString().split("T")[0];
        const timeStr = now.toTimeString().split(" ")[0];

        const dataPoint = {
            date: dateStr,
            day: getDayFromTitle(movie.name),
            time: timeStr,
            amount_cr: amount
        };

        if (!existingMap[movieName]) existingMap[movieName] = [];

        const isDuplicate = existingMap[movieName].some(
            d => d.date === dataPoint.date && d.time === dataPoint.time
        );

        if (!isDuplicate) {
            console.log(`✅ ${movieName} (${dataPoint.day}) - ₹${amount} Cr`);
            existingMap[movieName].push(dataPoint);
        }

        await sleep(1000); // rate-limiting
    }

    const finalOutput = Object.entries(existingMap).map(([movie, data]) => ({
        movie,
        data
    }));

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(finalOutput, null, 2));
    console.log(`📁 Saved ${finalOutput.length} movies to ${OUTPUT_FILE}`);
}

main().catch(err => {
    console.error("❌ Error:", err.message);
    process.exit(1);
});
