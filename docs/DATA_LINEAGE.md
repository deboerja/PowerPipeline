# PowerPipeline — Data Lineage

## Per-source lineage

### SPP load / load-forecast (`mtlf-vs-actual`)

```
portal.spp.org file-browser-api
  → raw/spp/mtlf/{YYYY}/{MM}/{DD}/OP-MTLF-{YYYYMMDDHHmm}.csv   (immutable)
    → schema validation (contracts/spp_mtlf.py)
      pass → normalized/spp/load_forecast_actual.parquet (UTC, typed, deduped)
      fail → quarantine/spp/mtlf/{run_id}.parquet + reason
    → curated: fact_spp_load_forecast_actual (DuckDB table)
      → view: v_spp_load_forecast_accuracy (forecast error metrics)
        → ResidentAI: read_spp_load_conditions, read_spp_load_forecast_accuracy
        → reports/spp_load_forecast_accuracy.html
```

Provenance recorded per row: `source_file`, `source_system=SPP`,
`ingested_at`, `pipeline_run_id`. Every curated row traces back to exactly one
raw file.

### Household solar (Enphase, reused)

```
homelab/scripts Enphase pipeline (external, not owned by PowerPipeline)
  → snapshots/enphase/daily-summary/{date}.json   (external curated output)
    → raw/enphase/{date}.json (PowerPipeline's own immutable copy-on-read)
      → schema validation (contracts/enphase_summary.py)
        pass → normalized/enphase/daily_summary.parquet
        fail → quarantine/enphase/{run_id}.parquet + reason
      → curated: fact_household_solar (DuckDB table)
        → joined against household solar forecast for accuracy view
          → ResidentAI: read_household_solar_history,
            read_household_forecast_accuracy
```

PowerPipeline re-validates data it reads from an already-curated upstream
file — it does not assume the upstream is correct, since PowerPipeline's own
quarantine/quality guarantees must hold regardless of source.

### Household solar forecast (existing `solar_projection_model.py`, reused)

```
homelab/scripts weather pipeline
  → state/latest/solar_production_projection.json  (overwritten each run)
    → raw/solar_forecast/{captured_at}.json (PowerPipeline snapshots the
      overwritten file on each read, since upstream doesn't keep history)
      → normalized/household_solar_forecast.parquet
        → curated: fact_household_solar_forecast
          → joined against fact_household_solar (actual) for accuracy
```

### Weather actual / forecast (reused)

```
homelab/scripts weather pipeline
  → snapshots/weather/daily-actual/{date}.json
    → raw/weather/{date}.json → normalized → curated: fact_weather_actual
  → state/latest/weather_current_snapshot.json
    → raw/weather_forecast/{captured_at}.json → normalized → curated:
      fact_weather_forecast
```

## Cross-cutting metadata

Every ingestion run writes one row to `pipeline_runs` (run_id, source,
started_at, finished_at, status, records_in, records_accepted,
records_quarantined, watermark_before, watermark_after) regardless of
success or failure, and one row per validation check to
`data_quality_results` (run_id, check_name, status, detail). These two tables
are what `read_pipeline_health` and `read_data_quality_summary` expose to
ResidentAI, and what the interview demo's monitoring view is built from.
