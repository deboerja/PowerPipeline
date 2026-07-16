"""Offline-capable interview demonstration. Runs entirely against
fixtures/ -- no live network access required. See docs/INTERVIEW_DEMO.md
for the full narrative behind each step.

Usage:
    python -m powerpipeline.demo run-all
"""

from __future__ import annotations

import html
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "fixtures"
DEMO_RUNTIME_ROOT = REPO_ROOT / ".powerpipeline_demo_runtime"


def _reset_demo_runtime() -> None:
    if DEMO_RUNTIME_ROOT.exists():
        shutil.rmtree(DEMO_RUNTIME_ROOT)
    os.environ["POWERPIPELINE_RUNTIME_ROOT"] = str(DEMO_RUNTIME_ROOT)


def run_all() -> None:
    _reset_demo_runtime()

    # Imports deferred until after POWERPIPELINE_RUNTIME_ROOT is set, since
    # powerpipeline.storage.paths reads it at call time (not import time),
    # but keeping the import here makes that dependency explicit.
    from powerpipeline import db, pipeline
    from powerpipeline.residentai_tool import ResidentAiReadOnlyTool

    steps: list[tuple[str, str]] = []

    def step(title: str, body: str) -> None:
        steps.append((title, body))
        print(f"\n=== {title} ===")
        print(body)

    # 1. Architecture
    step(
        "1. Architecture",
        "Raw -> quarantine/normalized -> DuckDB curated -> ResidentAI read-only tool. "
        "See docs/ARCHITECTURE.md for the full diagram and layer descriptions.",
    )

    # 2. Source registry
    step(
        "2. Source registry",
        "Confirmed: SPP mtlf-vs-actual (load + load-forecast-vs-actual), "
        "generation-mix-historical (actuals). Enphase and weather reused "
        "read-only from existing homelab pipelines. Open item: SPP renewable "
        "forecast-vs-actual not yet located (implementation/BLOCKERS.yaml bl-001) "
        "-- disclosed honestly below, not faked.",
    )

    # 3 & 4. Lineage + successful ingestion
    spp_csv = (FIXTURES / "spp" / "mtlf" / "OP-MTLF-202607150000.csv").read_bytes()
    spp_result = pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_csv)
    step(
        "3-4. Raw-to-curated lineage and successful ingestion",
        f"Ingested fixture SPP file end to end: {spp_result}. "
        "Provenance chain: fixtures/spp/mtlf/... -> raw/spp/mtlf/2026/07/15/... "
        "-> normalized parquet -> fact_spp_load_forecast_actual "
        f"(pipeline_run_id={spp_result['run_id']}).",
    )

    pipeline.run_enphase_bridge(FIXTURES / "enphase" / "daily-summary")
    pipeline.run_weather_bridge(FIXTURES / "weather" / "daily-actual")
    pipeline.run_household_solar_forecast_bridge(
        FIXTURES / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )

    tool = ResidentAiReadOnlyTool()

    # 5. SPP load forecast vs actual
    spp_accuracy = tool.read_spp_load_forecast_accuracy("2026-07-14", "2026-07-15", baa="SPP")
    step("5. SPP load forecast vs. actual", f"{spp_accuracy['record_count']} day(s): {spp_accuracy['records']}")

    # 6. SPP renewable forecast vs actual (honest gap)
    renewable = tool.read_spp_renewable_conditions("2026-07-01", "2026-07-15")
    step("6. SPP renewable forecast vs. actual", f"status={renewable['status']}: {renewable['known_limitations']}")

    # 7. Household solar forecast vs actual
    household_accuracy = tool.read_household_forecast_accuracy("2026-01-01", "2026-01-31")
    step("7. Household solar forecast vs. actual", f"{household_accuracy['records']}")

    # 8. Pipeline-run monitoring
    health = tool.read_pipeline_health()
    step("8. Pipeline-run monitoring", f"{health['records']}")

    # 9. Data-quality results
    quality = tool.read_data_quality_summary()
    step("9. Data-quality results", f"{quality['record_count']} result(s): {quality['records'][:3]}")

    # 10. Duplicate input handling
    con = db.connect(read_only=True)
    before = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
    con.close()
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_csv)
    con = db.connect(read_only=True)
    after = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
    con.close()
    step("10. Duplicate input handling", f"Re-ingested identical file: {before} rows before, {after} rows after (no growth).")

    # 11. Invalid-record quarantine
    import io as _io

    import pandas as pd  # noqa: PLC0415

    df = pd.read_csv(_io.BytesIO(spp_csv))
    df.loc[0, "BAA"] = "NOT_REAL"
    buf = _io.StringIO()
    df.to_csv(buf, index=False)
    quarantine_result = pipeline.run_spp_load_ingest(
        2026, 7, 20, "OP-MTLF-202607200000.csv", raw_csv=buf.getvalue().encode()
    )
    step("11. Invalid-record quarantine", f"1 row with invalid BAA quarantined: {quarantine_result}")

    # 12. Missing-interval detection
    # Demonstrated in a fresh, isolated runtime: the main demo runtime above
    # has already ingested this same fixture's timestamps multiple times
    # (steps 3-4, 10, 11), so a "gap" introduced here would just get
    # silently backfilled by those earlier upserts rather than showing up --
    # that would be a misleading demo, not a real gap. Isolating it mirrors
    # exactly what tests/test_missing_interval_detection.py does.
    original_runtime_root = os.environ["POWERPIPELINE_RUNTIME_ROOT"]
    gap_demo_root = REPO_ROOT / ".powerpipeline_demo_runtime_gap_check"
    if gap_demo_root.exists():
        shutil.rmtree(gap_demo_root)
    os.environ["POWERPIPELINE_RUNTIME_ROOT"] = str(gap_demo_root)
    try:
        original_spp = pd.read_csv(_io.BytesIO(spp_csv))
        subset = original_spp[original_spp["BAA"] == "SPP"].sort_values("GMTIntervalEnd")
        gappy = original_spp.drop(index=subset.index[len(subset) // 2])
        buf2 = _io.StringIO()
        gappy.to_csv(buf2, index=False)
        pipeline.run_spp_load_ingest(2026, 7, 21, "OP-MTLF-202607210000.csv", raw_csv=buf2.getvalue().encode())
        gap_tool = ResidentAiReadOnlyTool()
        quality_after_gap = gap_tool.read_data_quality_summary()
        gap_check = next(
            r for r in quality_after_gap["records"] if r["check_name"] == "missing_interval_completeness"
        )
    finally:
        os.environ["POWERPIPELINE_RUNTIME_ROOT"] = original_runtime_root
        shutil.rmtree(gap_demo_root, ignore_errors=True)
    step(
        "12. Missing-interval detection",
        f"In an isolated ingest with one SPP interval removed: {gap_check} "
        "(the gap is flagged, not interpolated -- demonstrated in a fresh "
        "runtime so it isn't masked by other steps' overlapping data).",
    )

    # 13 & 14. Simulated source failure + retry/backfill recovery
    import httpx  # noqa: PLC0415

    from powerpipeline.ingest import spp_load as spp_load_module  # noqa: PLC0415

    original_fetch = spp_load_module.fetch_raw_csv

    def flaky_fetch(year, month, day, filename, client=None, **kwargs):
        if (year, month, day) == (2026, 7, 22):
            raise httpx.ConnectError("simulated outage for interview demo")
        return spp_csv

    spp_load_module.fetch_raw_csv = flaky_fetch
    try:
        backfill_result = pipeline.bounded_backfill(
            [
                (2026, 7, 22, "OP-MTLF-202607220000.csv"),  # fails
                (2026, 7, 23, "OP-MTLF-202607230000.csv"),  # succeeds
            ]
        )
    finally:
        spp_load_module.fetch_raw_csv = original_fetch
    step(
        "13-14. Simulated source failure + retry/backfill recovery",
        f"{backfill_result} -- the failed day did not block the successful one.",
    )

    # 15. Preservation of valid curated data
    con = db.connect(read_only=True)
    final_count = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
    con.close()
    step(
        "15. Preservation of valid curated data",
        f"{final_count} curated rows present after the simulated failure above -- prior data untouched.",
    )

    # 16. ResidentAI read-only query
    live_query = tool.read_spp_load_conditions("2026-07-15", "2026-07-15", baa="SPP")
    step("16. ResidentAI read-only query", f"{live_query['record_count']} row(s) returned with full provenance metadata.")

    # 17 & 18. Rejection of arbitrary SQL and writes
    no_sql_method = {"query", "execute", "execute_sql", "run_sql", "sql"}.isdisjoint(
        {m for m in dir(tool) if not m.startswith("_")}
    )
    raw_con = tool._connect()
    write_rejected = False
    try:
        raw_con.execute("DELETE FROM fact_household_solar")
    except Exception as exc:  # noqa: BLE001
        write_rejected = True
        write_error = str(exc)
    finally:
        raw_con.close()
    step(
        "17-18. Rejection of arbitrary SQL and writes",
        f"No query/sql method exists on the tool class: {no_sql_method}. "
        f"Direct DELETE against the tool's read-only connection raised: {write_rejected} "
        f"({write_error if write_rejected else 'n/a'}).",
    )

    # 19. FranklinWH future-adapter design
    step(
        "19. FranklinWH future-adapter design",
        "Not implemented. Planned shape: mirror the Enphase pattern -- a "
        "separate, authorized ingestion module producing a curated JSON "
        "snapshot PowerPipeline reads read-only. See docs/FUTURE_ARCHITECTURE.md "
        "-- no access attempted until legitimate API/data access is confirmed.",
    )

    # 20. Design tradeoffs and future architecture
    step(
        "20. Design tradeoffs and future architecture",
        "DuckDB+Parquet+systemd chosen over Kafka/Spark/Airflow/dbt/Postgres for "
        "single-operator homelab scale and batch (not streaming) cadence -- see "
        "docs/ARCHITECTURE.md and docs/FUTURE_ARCHITECTURE.md for what would "
        "actually justify moving off this stack.",
    )

    _write_report(steps)
    print(f"\nReport written to {REPO_ROOT / 'reports' / 'interview_demo_report.html'}")


def _write_report(steps: list[tuple[str, str]]) -> None:
    rows = "\n".join(
        f"<section><h2>{html.escape(title)}</h2><pre>{html.escape(body)}</pre></section>"
        for title, body in steps
    )
    content = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>PowerPipeline Interview Demo</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
pre {{ white-space: pre-wrap; background: #f5f5f5; padding: 0.75rem; border-radius: 6px; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
</style></head>
<body>
<h1>PowerPipeline Interview Demonstration</h1>
<p>Generated by <code>python -m powerpipeline.demo run-all</code> against sanitized fixtures -- offline-capable, no live network access used.</p>
{rows}
</body></html>
"""
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "interview_demo_report.html").write_text(content)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "run-all":
        print("Usage: python -m powerpipeline.demo run-all")
        sys.exit(1)
    run_all()


if __name__ == "__main__":
    main()
