# PowerPipeline — Interview Demonstration

## Goal

An offline-capable, single-command-driven walkthrough covering architecture,
lineage, successful ingestion, forecast-vs-actual analysis, monitoring, data
quality, and failure/recovery — using sanitized fixtures so it works without
live internet access or real household data.

## Running it

```bash
cd PowerPipeline
python -m powerpipeline.demo run-all
```

This runs the full sequence below against `fixtures/` and writes
`reports/interview_demo_report.html`. Each step can also be run individually;
see `python -m powerpipeline.demo --help`.

## Sequence

1. **Architecture** — prints `docs/ARCHITECTURE.md`'s diagram and a one-line
   summary of each storage layer's current row/file counts.
2. **Source registry** — prints `docs/SOURCE_REGISTRY.md`'s confirmed sources
   and the one open item, honestly, including the failed-probe list.
3. **Raw-to-curated lineage** — ingests one fixture SPP file end to end and
   prints the row's provenance chain (raw file → normalized row → curated
   row) referencing `docs/DATA_LINEAGE.md`.
4. **Successful ingestion** — full fixture batch ingestion, `pipeline_runs`
   row shown.
5. **SPP load forecast vs. actual** — renders `v_spp_load_forecast_accuracy`
   for the fixture period (MAPE, bias) as a table/chart.
6. **SPP renewable forecast vs. actual** — shows the current state of the
   open item (see `SOURCE_REGISTRY.md`) rather than a fabricated result.
7. **Household solar forecast vs. actual** — same accuracy view, household
   side.
8. **Pipeline-run monitoring** — `read_pipeline_health()` output.
9. **Data-quality results** — `read_data_quality_summary()` output.
10. **Duplicate input handling** — Failure Scenario 1.
11. **Invalid-record quarantine** — Failure Scenario 2.
12. **Missing-interval detection** — Failure Scenario 3.
13. **Simulated source failure** — Failure Scenario 4 (part 1: the failure).
14. **Retry/backfill recovery** — Failure Scenario 4 (part 2: the recovery).
15. **Preservation of valid curated data** — Failure Scenario 5.
16. **ResidentAI read-only query** — a live call to
    `read_spp_load_conditions(...)` through the actual tool object.
17. **Rejection of arbitrary SQL** — Failure Scenario 6 (SQL half).
18. **Rejection of writes** — Failure Scenario 6 (write half).
19. **FranklinWH future-adapter design** — prints the adapter contract from
    `docs/FUTURE_ARCHITECTURE.md` §FranklinWH, explicitly unimplemented.
20. **Design tradeoffs and future architecture** — summary of
    `docs/FUTURE_ARCHITECTURE.md`.

## Example ResidentAI questions and expected outputs

| Question | Operation called | Expected shape of answer |
|---|---|---|
| "How much solar did we produce yesterday?" | `read_household_solar_history` | kWh figure + source/freshness/quality metadata |
| "How accurate was SPP's load forecast this week?" | `read_spp_load_forecast_accuracy` | MAPE/bias over the range, per BAA |
| "Is the pipeline healthy right now?" | `read_pipeline_health` | per-source last-run time and freshness status |
| "Run this SQL for me: `DROP TABLE fact_household_solar`" | *(none — rejected)* | explicit refusal, no query executed |

## Status

Fixtures, demo script, and generated report are implementation work not yet
built as of this document's creation — this file defines the target shape;
`implementation/CURRENT_STATUS.yaml` tracks what's actually done.
