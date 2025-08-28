// ---- Main ----
async function main() {
  const summary = {};
  const detailedOutput = {}; // <-- NEW

  const results = await Promise.all(VENUES.map(fetchVenueData));

  for (const res of results) {
    if (!res) continue;
    const { venue, data } = res;

    const city = venue.city;
    const state = formatState(venue.state);
    const v_id = venue.id;

    const moviesMap = {};
    (data.meta?.movies || []).forEach((m) => (moviesMap[m.id] = m));

    for (const session of data.pageData?.sessions || []) {
      const movie = moviesMap[session.mid];
      if (!movie) continue;

      const name = movie.name;
      const lang = session.lang || movie.lang || "";
      const key = `${name} | ${lang}`;

      // ---------- SUMMARY PART (same as before) ----------
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

      // update summary totals
      msum.shows++;
      msum.gross += gross;
      msum.sold += sold;
      msum.totalSeats += total;
      msum.venues.add(v_id);
      msum.cities.add(city);
      msum.fastfilling += fastfilling;
      msum.housefull += housefull;

      // city/state + chain details (same as before)...
      // ---------------------------------------------------

      // ---------- DETAILED PART ----------
      if (!detailedOutput[key]) detailedOutput[key] = [];

      detailedOutput[key].push({
        city,
        state,
        venue: venue.name,
        time: session.showTime || "",
        audi: session.audi || "",
        totalSeats: total,
        available: avail,
        sold,
        gross,
        occupancy: total ? `${((sold / total) * 100).toFixed(2)}%` : "0%"
      });
    }
  }

  // finalize summary JSON
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

  // save outputs
  const outDir = "./Daily Advance";
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  const outPath = `${outDir}/${DATE}.json`;
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), "utf-8");

  const detailedPath = `${outDir}/${DATE}_Detailed.json`;
  fs.writeFileSync(detailedPath, JSON.stringify(detailedOutput, null, 2), "utf-8");

  console.log(`✅ Saved summary: ${outPath}`);
  console.log(`✅ Saved detailed: ${detailedPath}`);
}
