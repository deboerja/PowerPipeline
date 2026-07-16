# PowerPipeline — Source Registry

Every external data source PowerPipeline depends on, how it was validated, and
its current status. Validated 2026-07-16 by direct HTTP probing from Odin.

## Southwest Power Pool (SPP) — public marketplace portal

Base: `https://portal.spp.org`. No authentication required for the datasets
below. The portal is a single-page app backed by two internal APIs discovered
by inspecting the app bundle and probing the file-browser API directly (no
credentials, no ToS bypass — these are the same public files a human would
download by clicking through the portal UI):

- `GET /file-browser-api/?fsName=<dataset>&name=<dataset>&path=<path>&type=folder`
  — directory listing, JSON
- `GET /file-browser-api/download/<dataset>?path=<file-path>` — raw file
  download

### `mtlf-vs-actual` — Mid-Term Load Forecast vs. Actual — PRIMARY, CONFIRMED

- Status: **validated, in use**
- Cadence: hourly files, one per hour, named `OP-MTLF-YYYYMMDDHHmm.csv`, path
  `/{year}/{month}/{day}/OP-MTLF-....csv`
- Coverage confirmed: `/2013` through `/2026/07/16` (today), no gaps observed
  in the day-listing for the current month
- Schema: `Interval, GMTIntervalEnd, MTLF, Averaged Actual, BAA` where `BAA`
  is `SPP` (Eastern Interconnect) or `SWPW` (Western Interconnect) — both
  balancing areas present in every file
- Forward-looking rows (near-term future intervals) have an empty
  `Averaged Actual` until the actual is published, which is itself a useful,
  real signal for a freshness/completeness check rather than a defect to
  paper over
- Satisfies MVP requirements: "one reliable SPP load dataset" AND "one SPP
  load forecast-versus-actual dataset" from a single source

### `stlf-vs-actual` — Short-Term Load Forecast vs. Actual — SECONDARY, CONFIRMED

- Status: **validated, not yet ingested** (available as a higher-frequency
  alternative/reconciliation source if MTLF's hourly cadence proves
  insufficient)
- Same file-browser mechanism, confirmed listable back to 2013

### `generation-mix-historical` — Actual Generation Mix by Fuel Type — CONFIRMED

- Status: **validated, planned for the generation-mix stretch goal**
- Two tiers: yearly historical CSVs at the dataset root (`GenMix_2011.csv` …),
  and near-real-time 5-minute-interval files under `/SPP/` and `/SWPW/`
  (`GenMix2Hour_SPP.csv`, `GenMixYTD_SPP.csv`, `GenMix365_SPP.csv`)
- Schema includes per-fuel Market/Self generation (Coal, Natural Gas, Nuclear,
  Solar, Wind, Hydro, Waste Disposal, Waste Heat, Other) plus total `Load`
- This is **actuals only** — no forecast component. Useful for "historical
  generation mix" and "renewable generation" subject areas; does not by
  itself satisfy a forecast-vs-actual requirement.

### Renewable forecast vs. actual — **OPEN ITEM, NOT YET LOCATED**

- Status: **unresolved as of 2026-07-16**
- SPP's Tableau-embedded dashboard pages reference chart names
  (`weis-forecast-vs-actual`, `gen-mix`, `gen-mix-swpw`, etc.) that live in a
  *different* subsystem (`/chart-api/dashboard/`) than the file-browser CSVs
  used above, and none of them are renewable-specific — `weis-forecast-vs-actual`
  is a Western Energy Imbalance Service *load* forecast, not a VER
  (variable energy resource) forecast.
- Attempted and failed (HTTP 404 against `file-browser-api`, ~25 combined
  guesses): `mtrf-vs-actual`, `mtrf`, `mtrf-vsa`, `strf-vs-actual`,
  `mtwf-vs-actual`, `stwf-vs-actual`, `wgrpp`, `vgrpp`, `wind-vs-actual`,
  `wind-forecast-vs-actual`, `wind-solar-forecast`, `wind-solar-vs-actual`,
  `ver-forecast`, `ver-forecast-vs-actual`, `ver-vs-actual`,
  `renewable-forecast-vs-actual`, `vsa-vs-actual`, `res-vs-actual`,
  `resource-vs-actual`, `vgrf-vs-actual`, `solar-forecast-vs-actual`, and
  several more (full list and commands: `implementation/BLOCKERS.yaml`,
  item `spp-renewable-forecast-vs-actual`).
- The portal's page-to-dataset mapping is not statically present in the JS
  bundle (likely fetched from a runtime config endpoint not identified from
  static analysis alone) — resolving this fully likely requires either (a)
  loading the actual dashboard page in a real browser and observing the
  network request it makes (see `claude-in-chrome` as a follow-up tool), or
  (b) directly asking SPP/checking their published Business Practices
  documentation for the current public product name.
- **This does not block the rest of the MVP.** Per the user's own governance
  in `MVP_AUTONOMY_PROFILE.md`, EIA-930 SWPP data may serve as a documented
  fallback only for specific, named functions (reconciliation, backfill,
  availability fallback, gap filling, validation) — but EIA-930 publishes
  actuals only, not forecasts, so it **cannot** substitute for a renewable
  *forecast*. The honest options, recorded in `DECISION_LOG.md`, are: keep
  investigating the correct dataset name/endpoint, treat generation-mix
  actuals + a naive persistence-forecast baseline as an interim substitute
  (clearly labeled as such, never presented as SPP's own forecast), or scope
  this requirement down for the MVP with the gap explicitly disclosed in the
  interview demo. No option that hides the gap is acceptable.

## Household sources (reused, not owned by PowerPipeline)

See `EXISTING_COMPONENT_REUSE.md` for full detail. Summary:

| Source | Owner | Interface PowerPipeline reads |
|---|---|---|
| Enphase solar production | `homelab/scripts` Enphase pipeline | `snapshots/enphase/daily-summary/<date>.json`, `state/latest/enphase_energy_summary.json` |
| Weather observations (actual) | `homelab/scripts` weather pipeline | `snapshots/weather/daily-actual/<date>.json` |
| Weather forecast | `homelab/scripts` weather pipeline | `state/latest/weather_current_snapshot.json`, `state/latest/weather_gridpoint_raw.json` |
| Household solar forecast | `homelab/scripts` `solar_projection_model.py` | `state/latest/solar_production_projection.json` |

PowerPipeline does not re-authenticate to Enphase or NWS/IEM directly for
these; it reads the already-curated JSON these existing pipelines produce.

## EIA-930 (fallback source, not yet activated)

Not currently ingested. Reserved for the documented fallback functions listed
above, if and when a specific gap requires it. Any future activation must be
recorded here and in `DECISION_LOG.md` before use, and must never silently
replace an SPP-sourced value.
