# PowerPipeline — Existing Component Reuse

Components discovered in the homelab that PowerPipeline reuses rather than
rebuilds. Discovery performed 2026-07-16 across the `homelab/scripts` and
`homelab/residentai-canon` repositories.

## Enphase household solar production

- **Repository / path:** `homelab/scripts`,
  `homelab_scripts/runtime/enphase-energy/`
- **Existing responsibility:** OAuth2 authentication and token refresh against
  Enphase's cloud Monitoring API (`api.enphaseenergy.com`), nightly ingestion
  of production-meter telemetry, validation, and curated daily-summary
  generation
- **Interface used by PowerPipeline:** read-only file access to
  `snapshots/enphase/daily-summary/<date>.json` and
  `state/latest/enphase_energy_summary.json`. Schema:
  `{date, system, solar_production_kwh, source_record_count,
  accepted_record_count, rejected_record_count, duplicate_record_count,
  expected_record_count, completeness_pct, data_status, source, ingested_at}`
- **Data ownership:** owned entirely by the Enphase pipeline. PowerPipeline
  never authenticates to Enphase and never touches
  `~/.config/residentai/enphase.env`.
- **Integration method:** PowerPipeline's household-solar bridge reads these
  JSON files directly (or via a thin adapter if run inside a container without
  the same mount) and treats them as an upstream raw source for its own
  raw-landing layer — i.e. PowerPipeline still applies its own schema
  validation and quarantine to what it reads, rather than trusting the
  upstream file blindly.
- **Failure behavior:** if the file for a given date is missing or stale,
  PowerPipeline records a source-freshness failure and quarantines nothing
  (there's nothing to quarantine) — it just reports the gap. It does not
  retry the Enphase pipeline itself; that pipeline's own retry/backfill is out
  of PowerPipeline's authority.
- **Security boundary:** PowerPipeline has no path to Enphase credentials,
  the OAuth flow, or the token-refresh lock file. Read-only file access only.
- **Reason for reuse:** the Enphase pipeline is live, governed
  (`residentai-canon` decision doc marks Enphase read authority approved), and
  already handles the hard parts (token refresh, DST-aware completeness
  validation). Rebuilding it would duplicate real engineering work for no
  benefit and would require re-requesting Enphase credential access.

## Weather observations and forecast

- **Repository / path:** `homelab/scripts`,
  `homelab_scripts/runtime/weather-projection/`
- **Existing responsibility:** NWS (`api.weather.gov`) current-observation and
  gridpoint-forecast polling (every 30 min), nightly archival of the prior
  day's actual observed weather, IEM ASOS historical backfill for gaps beyond
  NWS's ~7-day retention, and a physics-based 7-day solar production
  projection calibrated against paired Enphase + weather history.
- **Interface used by PowerPipeline:** read-only file access to
  `snapshots/weather/daily-actual/<date>.json` (schema:
  `{date, station, readings: [{timestamp_local, sky_cover_pct,
  temperature_c}], readings_available, recorded_at_utc}`) and
  `state/latest/solar_production_projection.json` for the household solar
  forecast.
- **Data ownership:** owned by the weather pipeline. No credentials involved
  (NWS/IEM require none beyond a `User-Agent` header).
- **Integration method:** same pattern as Enphase — read the curated JSON,
  apply PowerPipeline's own validation/quarantine on top, never call
  `api.weather.gov` or IEM directly from PowerPipeline code for data this
  pipeline already produces.
- **Failure behavior:** missing/stale file → freshness failure recorded, no
  retry of the upstream pipeline.
- **Security boundary:** none needed; source is unauthenticated. No shared
  attack surface.
- **Reason for reuse:** live, already handles the two hardest correctness
  issues in this domain (IPv6 DNS blackhole on this host, forcing IPv4 at the
  socket layer; Chicago-local-day-boundary vs. UTC-day-boundary handling for
  the IEM backfill range) — both documented, both already fixed upstream. If
  PowerPipeline ever needs an independent NWS/IEM call for something the
  existing pipeline doesn't produce, it will copy this pattern
  (IPv4-force + buffered UTC range) rather than rediscover the same bugs.

## ResidentAI read-only wrapper convention

- **Repository / path:** `homelab/scripts`, `bin/*_status.sh`,
  `lib/resident_ai_audit.sh`, `homelab_scripts/runtime/reports/
  openwebui-safe-report-access/openwebui-tools/README.md`
- **Existing responsibility:** a documented shape for exposing a bounded,
  read-only capability to ResidentAI — either as a bash wrapper (status
  checks) or as an OpenWebUI "Tool" (Python class with `Valves` config and
  public methods with docstrings), always: allowlisted operations only,
  parameterized/validated inputs, no shell exposure, no arbitrary paths, no
  runtime writes, and an explicit "Denied behavior"/"Authority posture"
  section in its docs.
- **Interface used by PowerPipeline:** PowerPipeline's own ResidentAI
  operations (`read_household_solar_history`, etc., see
  `SECURITY_AND_AUTHORITY.md`) follow this exact shape — a Python `Tools`
  class exposed via OpenWebUI, read-only DuckDB connection, fixed queries
  only.
- **Data ownership / integration method:** PowerPipeline owns its own tool
  file; it does not modify the existing Enphase/weather tool files.
- **Reason for reuse:** consistency — a new capability that looks and behaves
  like every other ResidentAI capability is easier to review, audit, and
  trust than a bespoke one.

## Audit and secrets conventions

- **Audit:** `lib/resident_ai_audit.sh` pattern (bash wrappers) and the
  inline-YAML pattern used by the Python Enphase/weather scripts are both
  documented conventions; PowerPipeline's ResidentAI operations use the
  inline-YAML pattern (narrower field set: `execution_id, timestamp_utc,
  interface, runtime_entrypoint, action, target_date, is_error,
  result_summary`) since it's Python-native and matches the two most recently
  built capabilities.
- **Secrets:** `residentai-canon/policies/runtime/
  residentai_credential_storage_convention_v1.yaml` — `~/.config/residentai/
  <service>.env`, mode 600, owner-only, never git-tracked, consumed via
  `EnvironmentFile=` (systemd) or `set -a; source; set +a` (manual/script).
  PowerPipeline follows this exactly for any credential it needs (SPP
  currently needs none — public data, no auth).

## Scheduling convention

- **Mechanism:** systemd user timers exclusively — no cron anywhere in this
  homelab. Existing capabilities each ship a `.service.template` +
  `.timer.template` under a `systemd/` subdirectory. Cross-capability
  ordering uses real `Wants=`/`After=` dependencies (e.g. the nightly dream
  report depends on both Enphase and weather nightly services so it can
  report their staleness even on failure, rather than silently skipping).
  PowerPipeline's own timers (SPP ingestion, quality checks, forecast
  generation, reports) follow this same template shape.

## Runtime directory convention on Odin

- **Observed at:** `/srv/compose/ai/docker-compose.yml` (live, 2 services:
  `ollama`, `openwebui`)
- **Pattern:** app state under `/srv/apps/<service>/`; ResidentAI's own
  ingestion data under `/srv/apps/resident-ai/runtime/` specifically
  (`state/latest/` for current-value files, `snapshots/<source>/<category>/`
  for dated archives, individually allowlisted per container mount); credential
  files bind-mounted individually and read-only, never the whole
  `~/.config/residentai/` directory.
- **PowerPipeline's choice:** `/srv/apps/powerpipeline/`, a sibling app
  directory alongside `ollama`, `openwebui`, `forgejo`, etc. -- not nested
  under `/srv/apps/resident-ai/`, since PowerPipeline owns a materially
  larger and differently-shaped dataset (raw/normalized/curated/DuckDB) than
  ResidentAI's existing snapshot-only tree. (A top-level `/srv/powerpipeline/`
  was the original plan; revised at actual deployment time when it turned out
  to require root to create -- see `docs/DECISION_LOG.md`.)

## Not found / genuinely new ground

No existing code touches SPP, EIA-930, utility billing data, or Home
Assistant whole-home consumption/grid-import meters (only solar production is
currently wired up from HA). These are new PowerPipeline-owned
responsibilities, not reuse candidates.
