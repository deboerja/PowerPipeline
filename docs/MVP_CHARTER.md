# PowerPipeline — MVP Charter

## Primary objective

Deliver a working, interview-ready MVP demonstrating end-to-end data
engineering: multi-source ingestion (public API + file-based), batch
processing, raw/normalized/quarantine/curated data layers, schema validation,
idempotent incremental loading, timestamp/timezone handling,
forecast-vs-actual analysis, data lineage, data-quality monitoring, pipeline
observability, retry/backfill behavior, controlled failure and recovery,
automated scheduling, bounded read-only ResidentAI access, and reproducible
documentation.

This is the first implementation slice of the long-term platform described in
`NORTH_STAR.md` — not the complete platform.

## Business context

This project supports a Data Engineer interview with **East River Electric
Power Cooperative**. The demonstration must make visible: pipeline/ETL design,
multi-source integration, APIs and scheduled batch processing, structured
datasets, SQL and Python, data validation and integrity, documentation and
cataloging, monitoring and troubleshooting, security-conscious design,
operational reliability, communication of tradeoffs, and conversion of
technical data into analytical outputs that a non-engineer could read.

The implementation must remain a real, running ResidentAI capability — not a
disposable demo that gets deleted after the interview.

## MVP functional scope (minimum)

**Regional (SPP, public data):**
- Hourly load — via `mtlf-vs-actual`
- Load forecast vs. actual — via `mtlf-vs-actual` (same dataset; see
  `SOURCE_REGISTRY.md`)
- Renewable forecast vs. actual — **open item**, see `SOURCE_REGISTRY.md` and
  `DECISION_LOG.md` for the investigation record and fallback plan
- Generation mix (stretch, non-blocking) — via `generation-mix-historical`

**Household (reused, not rebuilt):**
- Enphase solar production history (`homelab/scripts` Enphase pipeline)
- Weather observations and forecast (`homelab/scripts` weather pipeline)
- Household solar-generation forecast (existing `solar_projection_model.py`)
- Household forecast-vs-actual

**Storage layers:** immutable raw landing, quarantine, normalized, curated,
pipeline metadata, data-quality results, operational logs, generated reports.

**ResidentAI:** named read-only operations only, over curated views, with
provenance/freshness/quality metadata on every result. No SQL, no writes.

**Presentation:** the smallest reliable option — a static HTML/DuckDB-backed
report, not a new frontend framework.

## What "done" means

The MVP is complete only when the deployed system (not just the code) passes
`implementation/MVP_ACCEPTANCE_CRITERIA.yaml`, including a live demonstration
of ingestion, quarantine, duplicate handling, missing-interval detection,
simulated failure/recovery, and a working ResidentAI read-only query — with
arbitrary SQL and writes both demonstrably rejected.

## Explicit non-goals for the MVP

Kafka, Spark, Airflow, Kubernetes, dbt, PostgreSQL, TimescaleDB, a full
observability stack, high availability, database replication, geographic
disaster recovery, a formal data catalog product, a model registry, enterprise
RBAC, multi-person review, or FranklinWH access. See `FUTURE_ARCHITECTURE.md`
for why these are deferred, not rejected.
