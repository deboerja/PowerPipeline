"""Orchestrates one SPP load-forecast ingestion run end to end: land raw,
validate/normalize/quarantine, upsert into curated DuckDB tables, record
pipeline_runs + data_quality_results + source_freshness. Idempotent —
re-running for a period already loaded updates in place rather than
duplicating rows (DuckDB upsert keyed on the curated table's primary key).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from powerpipeline import db
from powerpipeline.ingest import enphase_bridge, household_solar_forecast_bridge, spp_load, weather_bridge

SOURCE_NAME = "spp_mtlf"


def run_spp_load_ingest(
    year: int, month: int, day: int, filename: str, raw_csv: bytes | None = None
) -> dict:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    watermark_after = f"{year:04d}-{month:02d}-{day:02d}"

    con = db.init_db()
    status = "success"
    result = None
    try:
        # Fetching/landing/validating is inside the try too: a fetch failure
        # (e.g. a simulated source outage) must still be recorded as a
        # failed run, not silently raise before anything is logged -- see
        # docs/FAILURE_SCENARIOS.md #4.
        result = spp_load.ingest_file(year, month, day, filename, raw_csv=raw_csv)
        if result.normalized_path is not None:
            _upsert_normalized(con, result.normalized_path, result.raw_path.name, run_id)
        _record_completeness_check(con, run_id)
    except Exception:
        status = "failed"
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        con.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, source, started_at, finished_at, status,
                 records_in, records_accepted, records_quarantined,
                 watermark_before, watermark_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                SOURCE_NAME,
                started_at,
                finished_at,
                status,
                result.records_in if result else None,
                result.records_accepted if result else None,
                result.records_rejected if result else None,
                None,
                watermark_after,
            ],
        )
        con.execute(
            """
            INSERT INTO source_freshness (source, last_success_at, last_attempt_at, current_watermark, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (source) DO UPDATE SET
                last_success_at = excluded.last_success_at,
                last_attempt_at = excluded.last_attempt_at,
                current_watermark = excluded.current_watermark,
                status = excluded.status
            """,
            [
                SOURCE_NAME,
                finished_at if status == "success" else None,
                finished_at,
                watermark_after,
                "fresh" if status == "success" else "failing",
            ],
        )
        con.close()

    return {
        "run_id": run_id,
        "status": status,
        "records_in": result.records_in,
        "records_accepted": result.records_accepted,
        "records_rejected": result.records_rejected,
    }


def _upsert_normalized(
    con: duckdb.DuckDBPyConnection, normalized_path, source_file: str, run_id: str
) -> None:
    con.execute(
        f"""
        INSERT INTO fact_spp_load_forecast_actual
            (baa, interval_start_utc, interval_end_utc, load_forecast_mw,
             load_actual_mw, source_file, ingested_at, pipeline_run_id)
        SELECT baa, interval_start_utc, interval_end_utc, load_forecast_mw,
               load_actual_mw, ?, now(), ?
        FROM read_parquet('{normalized_path}')
        ON CONFLICT (baa, interval_start_utc) DO UPDATE SET
            interval_end_utc = excluded.interval_end_utc,
            load_forecast_mw = excluded.load_forecast_mw,
            load_actual_mw = excluded.load_actual_mw,
            source_file = excluded.source_file,
            ingested_at = excluded.ingested_at,
            pipeline_run_id = excluded.pipeline_run_id
        """,
        [source_file, run_id],
    )


def _record_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    source: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    records_in: int,
    records_accepted: int,
    records_rejected: int,
    watermark_after: str,
) -> None:
    con.execute(
        """
        INSERT INTO pipeline_runs
            (run_id, source, started_at, finished_at, status,
             records_in, records_accepted, records_quarantined,
             watermark_before, watermark_after)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [run_id, source, started_at, finished_at, status, records_in, records_accepted,
         records_rejected, None, watermark_after],
    )
    con.execute(
        """
        INSERT INTO source_freshness (source, last_success_at, last_attempt_at, current_watermark, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (source) DO UPDATE SET
            last_success_at = excluded.last_success_at,
            last_attempt_at = excluded.last_attempt_at,
            current_watermark = excluded.current_watermark,
            status = excluded.status
        """,
        [source, finished_at if status == "success" else None, finished_at, watermark_after,
         "fresh" if status == "success" else "failing"],
    )


def run_enphase_bridge(snapshots_dir: Path) -> dict:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    normalized, rejected = enphase_bridge.ingest_directory(snapshots_dir)
    con = db.init_db()
    status = "success"
    try:
        if normalized is not None and len(normalized):
            con.execute(
                """
                INSERT INTO fact_household_solar
                    (date, solar_production_kwh, completeness_pct, data_status,
                     source_file, ingested_at, pipeline_run_id)
                SELECT date, solar_production_kwh, completeness_pct, data_status,
                       source_file, now(), ?
                FROM normalized
                ON CONFLICT (date) DO UPDATE SET
                    solar_production_kwh = excluded.solar_production_kwh,
                    completeness_pct = excluded.completeness_pct,
                    data_status = excluded.data_status,
                    source_file = excluded.source_file,
                    ingested_at = excluded.ingested_at,
                    pipeline_run_id = excluded.pipeline_run_id
                """,
                [run_id],
            )
    except Exception:
        status = "failed"
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        records_in = (len(normalized) if normalized is not None else 0) + (
            len(rejected) if rejected is not None else 0
        )
        _record_run(
            con, run_id, "enphase_household_solar", started_at, finished_at, status,
            records_in, len(normalized) if normalized is not None else 0,
            len(rejected) if rejected is not None else 0,
            str(finished_at.date()),
        )
        con.close()
    return {
        "run_id": run_id,
        "status": status,
        "records_accepted": len(normalized) if normalized is not None else 0,
        "records_rejected": len(rejected) if rejected is not None else 0,
    }


def run_weather_bridge(snapshots_dir: Path) -> dict:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    normalized, rejected = weather_bridge.ingest_directory(snapshots_dir)
    con = db.init_db()
    status = "success"
    try:
        if normalized is not None and len(normalized):
            con.execute(
                """
                INSERT INTO fact_weather_actual
                    (date, station, avg_temperature_c, avg_sky_cover_pct,
                     source_file, ingested_at, pipeline_run_id)
                SELECT date, station, avg_temperature_c, avg_sky_cover_pct,
                       source_file, now(), ?
                FROM normalized
                ON CONFLICT (date, station) DO UPDATE SET
                    avg_temperature_c = excluded.avg_temperature_c,
                    avg_sky_cover_pct = excluded.avg_sky_cover_pct,
                    source_file = excluded.source_file,
                    ingested_at = excluded.ingested_at,
                    pipeline_run_id = excluded.pipeline_run_id
                """,
                [run_id],
            )
    except Exception:
        status = "failed"
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        records_in = (len(normalized) if normalized is not None else 0) + (
            len(rejected) if rejected is not None else 0
        )
        _record_run(
            con, run_id, "weather_actual", started_at, finished_at, status,
            records_in, len(normalized) if normalized is not None else 0,
            len(rejected) if rejected is not None else 0,
            str(finished_at.date()),
        )
        con.close()
    return {
        "run_id": run_id,
        "status": status,
        "records_accepted": len(normalized) if normalized is not None else 0,
        "records_rejected": len(rejected) if rejected is not None else 0,
    }


def run_household_solar_forecast_bridge(source_path: Path) -> dict:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    normalized, rejected = household_solar_forecast_bridge.ingest_file(source_path)
    con = db.init_db()
    status = "success"
    try:
        if normalized is not None and len(normalized):
            con.execute(
                """
                INSERT INTO fact_household_solar_forecast
                    (forecast_for_date, captured_at_utc, forecast_kwh,
                     source_file, ingested_at, pipeline_run_id)
                SELECT forecast_for_date, captured_at_utc, forecast_kwh,
                       source_file, now(), ?
                FROM normalized
                ON CONFLICT (forecast_for_date, captured_at_utc) DO UPDATE SET
                    forecast_kwh = excluded.forecast_kwh,
                    source_file = excluded.source_file,
                    ingested_at = excluded.ingested_at,
                    pipeline_run_id = excluded.pipeline_run_id
                """,
                [run_id],
            )
    except Exception:
        status = "failed"
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        records_in = (len(normalized) if normalized is not None else 0) + (
            len(rejected) if rejected is not None else 0
        )
        _record_run(
            con, run_id, "household_solar_forecast", started_at, finished_at, status,
            records_in, len(normalized) if normalized is not None else 0,
            len(rejected) if rejected is not None else 0,
            str(finished_at.date()),
        )
        con.close()
    return {
        "run_id": run_id,
        "status": status,
        "records_accepted": len(normalized) if normalized is not None else 0,
        "records_rejected": len(rejected) if rejected is not None else 0,
    }


def bounded_backfill(day_specs: list[tuple[int, int, int, str]]) -> dict:
    """Ingest a bounded list of (year, month, day, filename) specs, one
    ingestion run per spec. A failure on one day is recorded and does not
    abort the rest of the batch -- this is what lets a scheduled run recover
    from a single missed/failed day without needing the whole history
    replayed. See docs/FAILURE_SCENARIOS.md #4.
    """
    results = []
    for year, month, day, filename in day_specs:
        try:
            result = run_spp_load_ingest(year, month, day, filename)
        except Exception as exc:  # noqa: BLE001 -- deliberately continue past any single day's failure
            results.append({"date": f"{year:04d}-{month:02d}-{day:02d}", "status": "failed", "error": str(exc)})
            continue
        results.append({"date": f"{year:04d}-{month:02d}-{day:02d}", "status": result["status"]})
    failed = [r for r in results if r["status"] != "success"]
    return {"attempted": len(results), "failed": len(failed), "results": results}


def run_quality_sweep() -> dict:
    """Independent, periodic full-table quality sweep -- distinct from the
    per-run completeness check that fires inline with each ingest. Re-checks
    the entire fact_spp_load_forecast_actual table for gaps (not just the
    latest batch) and flags any source whose freshness has gone stale
    without a new successful run. Intended to run hourly via
    powerpipeline-quality-check.timer, independent of ingestion timing.
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    con = db.init_db()
    try:
        _record_completeness_check(con, run_id)
        stale = con.execute(
            """
            SELECT source, last_success_at, status
            FROM source_freshness
            WHERE status != 'fresh'
               OR last_success_at IS NULL
               OR last_success_at < now() - INTERVAL 25 HOUR
            """
        ).fetchall()
        next_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM data_quality_results").fetchone()[0]
        status = "fail" if stale else "pass"
        detail = f"{len(stale)} stale/failing source(s): {stale}" if stale else "all sources fresh"
        con.execute(
            """
            INSERT INTO data_quality_results (id, run_id, check_name, status, detail, checked_at)
            VALUES (?, ?, 'source_freshness_sweep', ?, ?, now())
            """,
            [next_id, run_id, status, detail],
        )
        return {"run_id": run_id, "stale_sources": len(stale)}
    finally:
        finished_at = datetime.now(timezone.utc)
        con.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, source, started_at, finished_at, status,
                 records_in, records_accepted, records_quarantined,
                 watermark_before, watermark_after)
            VALUES (?, 'quality_sweep', ?, ?, 'success', NULL, NULL, NULL, NULL, NULL)
            """,
            [run_id, started_at, finished_at],
        )
        con.close()


def _record_completeness_check(con: duckdb.DuckDBPyConnection, run_id: str) -> None:
    """Flags any hour-sized gap in the loaded fact table per BAA, without
    guessing a value for the missing hour — see docs/FAILURE_SCENARIOS.md #3.
    """
    gaps = con.execute(
        """
        WITH ordered AS (
            SELECT baa, interval_start_utc,
                   lag(interval_start_utc) OVER (PARTITION BY baa ORDER BY interval_start_utc) AS prev
            FROM fact_spp_load_forecast_actual
        )
        SELECT baa, prev, interval_start_utc
        FROM ordered
        WHERE prev IS NOT NULL
          AND interval_start_utc - prev > INTERVAL 1 HOUR
        """
    ).fetchall()
    next_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM data_quality_results").fetchone()[0]
    status = "fail" if gaps else "pass"
    detail = f"{len(gaps)} gap(s) detected" if gaps else "no gaps detected"
    con.execute(
        """
        INSERT INTO data_quality_results (id, run_id, check_name, status, detail, checked_at)
        VALUES (?, ?, 'missing_interval_completeness', ?, ?, now())
        """,
        [next_id, run_id, status, detail],
    )
