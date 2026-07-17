# PowerPipeline — Operations

## Start / stop / restart / status

PowerPipeline runs as systemd user timers on Odin, not a Docker Compose
stack — there's no long-running server process to containerize, just
scheduled batch jobs (see `docs/ARCHITECTURE.md` for why).

```bash
systemctl --user status powerpipeline-spp-ingest.timer powerpipeline-household-bridge.timer powerpipeline-quality-check.timer
systemctl --user stop powerpipeline-*.timer      # stop all scheduling
systemctl --user start powerpipeline-*.timer     # resume scheduling
systemctl --user restart powerpipeline-*.service # not needed for oneshot services; re-run manually instead:
systemctl --user start powerpipeline-spp-ingest.service  # trigger one immediate run
journalctl --user -u powerpipeline-spp-ingest.service -n 50 --no-pager
```

Deployed and running on Odin as of 2026-07-17 — see
`implementation/CURRENT_STATUS.yaml` for current status and
`implementation/EXECUTION_HISTORY.yaml` for the deployment record.

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
cp /srv/apps/powerpipeline/database/powerpipeline.duckdb \
   /srv/apps/powerpipeline/backups/powerpipeline-$(date -u +%Y%m%dT%H%M%SZ).duckdb

# restore
systemctl --user stop powerpipeline-*.timer
cp /srv/apps/powerpipeline/backups/powerpipeline-<timestamp>.duckdb \
   /srv/apps/powerpipeline/database/powerpipeline.duckdb
systemctl --user start powerpipeline-*.timer
```

## Rebuild curated data from raw

Because raw landing is immutable and normalized/curated are derived, the
entire curated layer can be rebuilt from raw alone -- **this is the designed
recovery path, not yet implemented as a single command.** Today, rebuilding
means: delete `database/powerpipeline.duckdb`, then re-run
`db.init_db()` (recreates schema/views) and re-process each file already
present under `raw/` through the same `ingest_file`/bridge functions used
for normal ingestion (they're idempotent, so replaying all of history is
safe). A dedicated `python -m powerpipeline.rebuild` entrypoint that
automates this walk is tracked as a follow-up
(`implementation/CURRENT_STATUS.yaml` not_started list) -- flagged here
rather than left as a documented command that doesn't actually exist.

## Upstream failure behavior

If SPP, Enphase, or weather is unreachable/stale, ingestion for that source
records a failed `pipeline_runs` row and a `source_freshness` staleness
entry, and **does not touch existing curated data** — the last-good curated
state remains queryable and is reported as stale, not silently replaced or
deleted. See `FAILURE_SCENARIOS.md` for the specific tested scenarios.

## Health checks

`read_pipeline_health()` (via `ResidentAiReadOnlyTool` or the ResidentAI
OpenWebUI tool's `read_pipeline_health` method) reports, per source: last
successful run time, last attempted run time, current watermark, and
freshness status (fresh / stale / failing). No separate HTTP health
endpoint exists -- this was originally planned but the DuckDB-backed tool
and the OpenWebUI JSON export already cover the same need, so a third
interface wasn't built (avoiding an unused code path).

## ResidentAI integration: status, disable, and rollback

Registered 2026-07-17 as OpenWebUI tool id `residentai_powerpipeline` (see
`docs/DECISION_LOG.md` for exactly how).

**Check it's registered and see its parsed method specs** (confirmed working):

```bash
TOKEN=$(grep '^OPENWEBUI_API_KEY=' ~/.config/residentai/memory-extraction.env | cut -d= -f2-)
curl -s http://localhost:3001/api/v1/tools/id/residentai_powerpipeline \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Disable or remove it:** attempted via the API (`DELETE .../id/{id}/delete`)
and got HTTP 401 -- the route exists but this token's permission set
(`workspace.tools: false`, despite `role: admin`) blocks delete via API,
even though it was sufficient to create the tool. Rather than guess at a
workaround for a token permission boundary, the confirmed working path is
the OpenWebUI web UI: **Admin Panel → Tools → "ResidentAI PowerPipeline
(SPP + Household Energy)" → disable or delete.**

**Fastest actual kill-switch, confirmed to require no permission beyond what
was already used:** remove the mount so the tool has nothing to read --
every method then fails closed with `export_not_available` rather than
returning stale or wrong data:

```bash
cp /srv/compose/ai/docker-compose.yml.bak.20260717T003816Z /srv/compose/ai/docker-compose.yml
cd /srv/compose/ai && docker compose up -d --no-deps openwebui
```

This does not affect the `ollama` service or any other mount, and doesn't
require touching OpenWebUI's tool registration at all.
