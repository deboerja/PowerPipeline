# PowerPipeline — Failure Scenarios

Each scenario below is exercised by the offline demonstration
(`docs/INTERVIEW_DEMO.md`) using fixtures, not live network calls, so it
reproduces identically without internet access.

## 1. Duplicate input

**Setup:** the same raw SPP file (or an overlapping-interval re-pull) is fed
through ingestion twice.

**Expected:** raw landing gets both copies (raw is append-only/immutable by
design — that's not a bug). Normalization's upsert-by-natural-key collapses
them; the curated row count is unchanged after the second run.
`pipeline_runs` records both runs; the second shows `records_accepted` equal
to `records_deduplicated` for the overlapping rows.

## 2. Invalid record → quarantine

**Setup:** a fixture with a malformed row injected (e.g. non-numeric `MTLF`,
a `BAA` value outside `{SPP, SWPW}`, a timestamp that doesn't parse).

**Expected:** the malformed row is written to `quarantine/spp/mtlf/<run_id>.parquet`
with a `rejection_reason`. The rest of the file's valid rows still load
normally. Curated tables contain zero rows from the rejected record.

## 3. Missing interval detection

**Setup:** a fixture with an hour's file deleted from the sequence.

**Expected:** the completeness check in `data_quality_results` flags the gap
by comparing expected hourly cadence against what's present, without
guessing or interpolating a value for the missing hour.

## 4. Simulated source failure + retry/backfill recovery

**Setup:** the SPP endpoint fixture returns HTTP 503 (or times out) for one
scheduled run.

**Expected:** the run is recorded as failed in `pipeline_runs` (not silently
skipped), the existing curated data is untouched, and the next scheduled run
performs a bounded backfill (re-pulls the missed window, not the entire
history) that fills the gap once the source recovers. The completeness check
shows the gap during the outage and shows it closed after backfill.

## 5. Preservation of valid curated data during failure

**Setup:** a run fails partway through (e.g. crash after writing some
normalized rows but before the curated upsert commits).

**Expected:** the curated upsert is transactional (DuckDB single-file ACID
transaction) — a partial failure never leaves curated tables in a half-
written state. Previously-committed curated data from prior successful runs
is never touched by a failed run.

## 6. ResidentAI boundary enforcement

**Setup:** the interview demo issues a raw `SELECT * FROM fact_spp_load_forecast_actual`
string and a `DELETE FROM fact_household_solar` string directly at the
ResidentAI-facing tool object.

**Expected:** both are rejected — there is no code path in the tool that
accepts or executes a SQL string at all; only the named, parameterized
methods listed in `SECURITY_AND_AUTHORITY.md` exist. This is a structural
test (the method literally isn't there), not a permissions check that could
be bypassed.
