# PowerPipeline — Operations

## Start / stop / restart / status

```bash
cd /srv/compose/powerpipeline
docker compose up -d           # start
docker compose down            # stop
docker compose restart         # restart
docker compose ps              # status
docker compose logs -f ingest  # tail logs
```

(These are the planned commands for the deployed system — see the
Deployment Status section of `implementation/CURRENT_STATUS.yaml` for
whether they've been executed yet on Odin.)

## Scheduled jobs

systemd user timers (installed under `~/.config/systemd/user/`, matching the
existing ResidentAI convention):

| Timer | Cadence | Action |
|---|---|---|
| `powerpipeline-spp-ingest.timer` | hourly, :10 | pull latest `mtlf-vs-actual` file |
| `powerpipeline-household-bridge.timer` | every 30 min | read latest Enphase/weather curated files |
| `powerpipeline-quality-check.timer` | hourly, :25 | full-table completeness + source-freshness sweep, independent of the per-run checks that fire inline with each ingest |
| `powerpipeline-report.timer` | daily | regenerate the static report |

There is no separate "recompute forecast-vs-actual" job -- the accuracy
tables (`v_spp_load_forecast_accuracy`, `v_household_solar_forecast_accuracy`)
are plain SQL views, not materialized tables, so they're always current as
of the last ingest with no scheduled recomputation step needed.

```bash
systemctl --user status powerpipeline-spp-ingest.timer
systemctl --user list-timers 'powerpipeline-*'
journalctl --user -u powerpipeline-spp-ingest.service -n 100
```

## Backup and restore

The entire curated state is one DuckDB file plus a Parquet tree — backup is a
file copy, not a database dump/restore procedure.

```bash
# backup (safe while writers are idle; ingestion is not continuously writing)
cp /srv/powerpipeline/database/powerpipeline.duckdb \
   /srv/powerpipeline/backups/powerpipeline-$(date -u +%Y%m%dT%H%M%SZ).duckdb

# restore
systemctl --user stop powerpipeline-*.timer
cp /srv/powerpipeline/backups/powerpipeline-<timestamp>.duckdb \
   /srv/powerpipeline/database/powerpipeline.duckdb
systemctl --user start powerpipeline-*.timer
```

## Rebuild curated data from raw

Because raw landing is immutable and normalized/curated are derived, the
entire curated layer can be rebuilt from raw alone:

```bash
python -m powerpipeline.rebuild --from-raw --source all
```

This is the recovery path after a corrupted DuckDB file, a bad curated
migration, or a quarantine-logic bug fix that needs to be replayed against
history.

## Upstream failure behavior

If SPP, Enphase, or weather is unreachable/stale, ingestion for that source
records a failed `pipeline_runs` row and a `source_freshness` staleness
entry, and **does not touch existing curated data** — the last-good curated
state remains queryable and is reported as stale, not silently replaced or
deleted. See `FAILURE_SCENARIOS.md` for the specific tested scenarios.

## Health checks

`read_pipeline_health()` (also exposed as a plain HTTP health endpoint bound
to localhost only) reports, per source: last successful run time, last
attempted run time, current watermark, and freshness status (fresh / stale /
failing).
