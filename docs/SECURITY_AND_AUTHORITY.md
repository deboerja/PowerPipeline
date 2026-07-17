# PowerPipeline — Security and Authority

## What ResidentAI can do with PowerPipeline data

Named, fixed operations only, over curated views, through a read-only DuckDB
connection:

- `read_household_solar_history(start_date, end_date)`
- `read_household_solar_forecast(start_date, end_date)`
- `read_household_forecast_accuracy(start_date, end_date)`
- `read_spp_load_conditions(start_date, end_date, baa)`
- `read_spp_load_forecast_accuracy(start_date, end_date, baa)`
- `read_spp_renewable_conditions(start_date, end_date)` *(pending resolution
  of the open renewable-forecast source gap — see `SOURCE_REGISTRY.md`)*
- `read_pipeline_health()`
- `read_data_quality_summary()`

Every operation:
- takes parameterized, validated inputs (dates parsed and range-checked
  before use — never interpolated into SQL text)
- enforces a maximum date range and a maximum row limit
- runs against a **read-only** DuckDB connection (opened `read_only=True`;
  the process holding the writable connection is the ingestion pipeline, a
  separate process that never runs inside the ResidentAI-facing tool)
- has a query timeout
- reads curated views only, never raw/normalized/quarantine tables directly
- returns a structured result that always includes: source, observation
  period, source timestamp, ingestion timestamp, freshness, quality status,
  record count, and known limitations
- writes a structured audit record for the call

## What ResidentAI explicitly cannot do

No arbitrary SQL endpoint exists, full stop — there is no code path that
accepts a SQL string from the model and executes it. No write access — the
read-only connection cannot `INSERT`/`UPDATE`/`DELETE`/`CREATE` even if asked.
No shell execution, no unrestricted filesystem access, no secret access, no
equipment-control authority, no general Home Assistant write access. These
are structural (the connection is opened read-only; the tool has no shell
import; no credential file is mounted into the tool's environment), not just
policy statements — the interview demo (`INTERVIEW_DEMO.md`) includes a live
test that submits an arbitrary `SELECT` and a `DELETE` against the tool and
shows both rejected.

## Runtime isolation

PowerPipeline owns exactly `/srv/apps/powerpipeline/` and its own Compose
project/systemd units. It does not touch unrelated `/srv` paths, does not
restart unrelated services, does not modify the existing `ai` Compose
project's file directly (a new `docker-compose.yml` under
`/srv/compose/powerpipeline/` instead), does not change Firewalla/DNS/
reverse-proxy/auth configuration, and binds nothing to a
non-localhost/non-trusted-internal address. No internet-accessible port is
opened.

## Secrets

SPP's data sources currently require no credentials at all (public,
unauthenticated). If a future source needs one, it follows the existing
`~/.config/residentai/<service>.env` convention (mode 600, owner-only, never
git-tracked) documented in `EXISTING_COMPONENT_REUSE.md` — no new convention
invented. Nothing resembling an API key, token, password, private key,
session cookie, home address, account identifier, or unsanitized household
telemetry is ever committed to this repository; only sanitized fixtures are
committed (see `fixtures/`).

## Data integrity guarantees

- Missing source data is reported as missing (a recorded freshness/
  completeness failure), never fabricated.
- A failed validation is recorded in `data_quality_results`, never hidden.
- Curated tables never contain a record that failed validation — rejected
  records live in quarantine only.
- ResidentAI-facing results always disclose freshness and quality status, so
  stale data is never presented as current without saying so.
- EIA-930 is never used as a silent substitute for an SPP-sourced value — any
  use is explicit, logged, and restricted to the documented fallback
  functions in `SOURCE_REGISTRY.md`.
