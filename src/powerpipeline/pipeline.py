"""Orchestrates one SPP load-forecast ingestion run end to end: land raw,
validate/normalize/quarantine, upsert into curated DuckDB tables, record
pipeline_runs + data_quality_results + source_freshness. Idempotent —
re-running for a period already loaded updates in place rather than
duplicating rows (DuckDB upsert keyed on the curated table's primary key).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import duckdb

from powerpipeline import db
from powerpipeline.ingest import spp_load

SOURCE_NAME = "spp_mtlf"


def run_spp_load_ingest(
    year: int, month: int, day: int, filename: str, raw_csv: bytes | None = None
) -> dict:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    result = spp_load.ingest_file(year, month, day, filename, raw_csv=raw_csv)

    con = db.init_db()
    status = "success"
    try:
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
                result.records_in,
                result.records_accepted,
                result.records_rejected,
                None,
                f"{year:04d}-{month:02d}-{day:02d}",
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
                f"{year:04d}-{month:02d}-{day:02d}",
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
