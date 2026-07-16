# PowerPipeline — Architecture

## Shape

```
                 ┌─────────────────────────────────────────────┐
                 │                  SOURCES                     │
                 │  SPP public portal   Enphase (reused)        │
                 │  (mtlf-vs-actual,    weather (reused)        │
                 │   generation-mix)    solar forecast (reused) │
                 └───────────────┬───────────────────────────────┘
                                 │  ingestion (Python, scheduled via systemd timers)
                                 ▼
                 ┌─────────────────────────────────────────────┐
                 │  RAW  (immutable landing, one file per pull) │
                 │  /srv/powerpipeline/raw/{source}/{date}/...  │
                 └───────────────┬───────────────────────────────┘
                                 │  schema validation (Pandera/Pydantic)
                         pass    │    fail
                    ┌────────────┴───────────┐
                    ▼                        ▼
        ┌───────────────────────┐  ┌───────────────────────┐
        │      NORMALIZED       │  │      QUARANTINE        │
        │  UTC-normalized,      │  │  invalid records +      │
        │  typed, deduplicated  │  │  reason, never promoted │
        └───────────┬───────────┘  └───────────────────────┘
                    │  incremental load (idempotent, watermarked)
                    ▼
        ┌───────────────────────────────────────────┐
        │            DuckDB (curated layer)          │
        │  fact tables + curated views                │
        │  + pipeline_runs, data_quality_results,      │
        │    source_freshness (metadata/observability) │
        └───────────────┬─────────────────────────────┘
                        │  read-only, named operations only
                        ▼
        ┌───────────────────────────────────────────┐
        │   ResidentAI read-only interface            │
        │   (OpenWebUI Tool, fixed queries,            │
        │    row limits, audit logging)                │
        └───────────────────────────────────────────┘
```

Reports (static HTML / DuckDB-driven) and the interview demo read from the
curated layer the same way ResidentAI does — no separate code path.

## Storage layers

- **Raw** — exactly what was pulled, unmodified, one immutable file per pull,
  content-addressed or timestamp-named so a re-pull never overwrites history.
- **Quarantine** — raw records that failed schema/range validation, with the
  specific failure reason attached. Never promoted downstream. Retained so a
  human (or a later re-processing run) can inspect exactly what was rejected
  and why.
- **Normalized** — validated records with UTC timestamps, explicit local-time
  columns where relevant, deduplicated, typed. Still one row per source
  record — no aggregation yet.
- **Curated** — the DuckDB tables and views actually queried by reports and
  ResidentAI: fact tables (load, load-forecast, household-solar,
  weather-actual, weather-forecast) plus derived accuracy views
  (forecast-vs-actual error metrics).
- **Metadata** — `pipeline_runs` (one row per ingestion run: started_at,
  finished_at, status, records_in, records_accepted, records_quarantined,
  watermark_before, watermark_after), `data_quality_results` (per-run
  completeness/range/freshness check outcomes), `source_freshness` (per-source
  last-successful-pull timestamp and staleness).
- **Logs** — structured JSON, one line per event, to
  `/srv/powerpipeline/logs/`.
- **Reports** — generated HTML/artifacts under `/srv/powerpipeline/reports/`.

## Idempotency and incremental loading

Each source ingestion tracks a **watermark** (the latest source-timestamp
successfully loaded) in the metadata layer. A run re-pulls from
`watermark - overlap_window` (a small bounded overlap, not the full history)
to catch late-arriving/corrected upstream data, and upserts into normalized
storage keyed on `(source, natural_key, source_timestamp)` — so re-running an
ingestion for a period already loaded is a no-op on the curated result, not a
duplicate-producing append. Duplicate raw pulls are still landed (raw is
immutable/append-only by design) but collapse during the normalize step.

## Why DuckDB + Parquet, not Postgres/Kafka/Airflow/dbt

Single-operator homelab scale, single-host deployment, batch (not streaming)
cadence measured in minutes-to-hours, and an interview goal of demonstrating
engineering judgment about *fit*, not resume-driven tool adoption. DuckDB
gives real SQL, real ACID within a single file, and trivial backup (copy the
file); Parquet gives a durable, portable raw/normalized format that doesn't
require a running server process. See `FUTURE_ARCHITECTURE.md` for what would
actually justify moving off this stack.

## Scheduling

systemd user timers, matching the existing ResidentAI convention exactly
(see `EXISTING_COMPONENT_REUSE.md`) — not cron, not an in-process scheduler.
