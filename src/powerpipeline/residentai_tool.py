"""The bounded, read-only interface ResidentAI is allowed to call.

Structural guarantees (not just policy):
  - The DuckDB connection is opened with read_only=True. DuckDB itself
    refuses any write/DDL statement on such a connection -- this isn't a
    check this code performs, it's enforced by the database engine.
  - There is no method, parameter, or code path anywhere in this class that
    accepts a SQL string. Every query is a fixed template with `?`
    placeholders; the only caller-supplied values are validated dates
    (parsed and range-checked before use) and a bounded `baa` enum. There is
    no way to reach this class and run arbitrary SQL, by construction.
  - Every call is logged (see _audit()) with a structured record matching
    the inline-YAML pattern already used by the Enphase/weather capabilities
    (see docs/EXISTING_COMPONENT_REUSE.md).

See docs/SECURITY_AND_AUTHORITY.md for the full authority statement and
docs/FAILURE_SCENARIOS.md #6 for the tests that exercise this boundary.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from powerpipeline import db
from powerpipeline.storage import paths

MAX_DATE_RANGE_DAYS = 366
MAX_ROWS = 5000
VALID_BAA = {"SPP", "SWPW"}


class DateRangeError(ValueError):
    pass


def _validate_date_range(start_date: str, end_date: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError) as exc:
        raise DateRangeError(f"Invalid date format (expected YYYY-MM-DD): {exc}") from exc
    if start > end:
        raise DateRangeError("start_date must not be after end_date")
    if (end - start).days > MAX_DATE_RANGE_DAYS:
        raise DateRangeError(f"Date range exceeds maximum of {MAX_DATE_RANGE_DAYS} days")
    return start, end


class ResidentAiReadOnlyTool:
    """Every public method here is the entire ResidentAI-facing surface.
    There is intentionally no generic `query()` method.
    """

    def __init__(self):
        self._audit_log_path = paths.logs_dir() / "residentai_tool_audit.jsonl"

    def _connect(self):
        return db.connect(read_only=True)

    def _audit(self, action: str, target: dict, is_error: bool, summary: str) -> None:
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "execution_id": str(uuid.uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "interface": "residentai_tool",
            "runtime_entrypoint": "ResidentAiReadOnlyTool",
            "action": action,
            "target": target,
            "is_error": is_error,
            "result_summary": summary,
        }
        with open(self._audit_log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    # -- household ---------------------------------------------------

    def read_household_solar_history(self, start_date: str, end_date: str) -> dict:
        start, end = _validate_date_range(start_date, end_date)
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT date, solar_production_kwh, completeness_pct, data_status,
                       source_file, ingested_at
                FROM fact_household_solar
                WHERE date BETWEEN ? AND ?
                ORDER BY date
                LIMIT ?
                """,
                [start, end, MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = self._wrap_result(
            source="enphase_household_solar",
            observation_period=(start, end),
            rows=rows,
            columns=["date", "solar_production_kwh", "completeness_pct", "data_status",
                     "source_file", "ingested_at"],
        )
        self._audit("read_household_solar_history", {"start": start_date, "end": end_date}, False,
                     f"{len(rows)} rows")
        return result

    def read_household_solar_forecast(self, start_date: str, end_date: str) -> dict:
        start, end = _validate_date_range(start_date, end_date)
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT forecast_for_date, captured_at_utc, forecast_kwh, source_file, ingested_at
                FROM fact_household_solar_forecast
                WHERE forecast_for_date BETWEEN ? AND ?
                ORDER BY forecast_for_date, captured_at_utc
                LIMIT ?
                """,
                [start, end, MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = self._wrap_result(
            source="household_solar_forecast",
            observation_period=(start, end),
            rows=rows,
            columns=["forecast_for_date", "captured_at_utc", "forecast_kwh", "source_file", "ingested_at"],
        )
        self._audit("read_household_solar_forecast", {"start": start_date, "end": end_date}, False,
                     f"{len(rows)} rows")
        return result

    def read_household_forecast_accuracy(self, start_date: str, end_date: str) -> dict:
        start, end = _validate_date_range(start_date, end_date)
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT date, actual_kwh, forecast_kwh, bias_kwh, abs_error_kwh
                FROM v_household_solar_forecast_accuracy
                WHERE date BETWEEN ? AND ?
                ORDER BY date
                LIMIT ?
                """,
                [start, end, MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = self._wrap_result(
            source="v_household_solar_forecast_accuracy",
            observation_period=(start, end),
            rows=rows,
            columns=["date", "actual_kwh", "forecast_kwh", "bias_kwh", "abs_error_kwh"],
        )
        self._audit("read_household_forecast_accuracy", {"start": start_date, "end": end_date}, False,
                     f"{len(rows)} rows")
        return result

    # -- SPP -----------------------------------------------------------

    def read_spp_load_conditions(self, start_date: str, end_date: str, baa: str = "SPP") -> dict:
        start, end = _validate_date_range(start_date, end_date)
        if baa not in VALID_BAA:
            raise ValueError(f"baa must be one of {VALID_BAA}")
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT baa, interval_start_utc, interval_end_utc, load_forecast_mw,
                       load_actual_mw, source_file, ingested_at
                FROM fact_spp_load_forecast_actual
                WHERE baa = ? AND interval_start_utc::DATE BETWEEN ? AND ?
                ORDER BY interval_start_utc
                LIMIT ?
                """,
                [baa, start, end, MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = self._wrap_result(
            source="spp_mtlf_vs_actual",
            observation_period=(start, end),
            rows=rows,
            columns=["baa", "interval_start_utc", "interval_end_utc", "load_forecast_mw",
                     "load_actual_mw", "source_file", "ingested_at"],
        )
        self._audit("read_spp_load_conditions", {"start": start_date, "end": end_date, "baa": baa}, False,
                     f"{len(rows)} rows")
        return result

    def read_spp_load_forecast_accuracy(self, start_date: str, end_date: str, baa: str = "SPP") -> dict:
        start, end = _validate_date_range(start_date, end_date)
        if baa not in VALID_BAA:
            raise ValueError(f"baa must be one of {VALID_BAA}")
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT baa, day, interval_count, mean_bias_mw, mean_abs_error_mw, mean_abs_pct_error
                FROM v_spp_load_forecast_accuracy
                WHERE baa = ? AND day::DATE BETWEEN ? AND ?
                ORDER BY day
                LIMIT ?
                """,
                [baa, start, end, MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = self._wrap_result(
            source="v_spp_load_forecast_accuracy",
            observation_period=(start, end),
            rows=rows,
            columns=["baa", "day", "interval_count", "mean_bias_mw", "mean_abs_error_mw", "mean_abs_pct_error"],
        )
        self._audit("read_spp_load_forecast_accuracy", {"start": start_date, "end": end_date, "baa": baa}, False,
                     f"{len(rows)} rows")
        return result

    def read_spp_renewable_conditions(self, start_date: str, end_date: str) -> dict:
        """Not yet available -- see docs/SOURCE_REGISTRY.md and
        implementation/BLOCKERS.yaml bl-001. Returns an honest
        not-available result rather than fabricating data.
        """
        _validate_date_range(start_date, end_date)
        self._audit("read_spp_renewable_conditions", {"start": start_date, "end": end_date}, True,
                     "source not yet available, see BLOCKERS.yaml bl-001")
        return {
            "source": "spp_renewable_forecast_vs_actual",
            "status": "not_available",
            "known_limitations": [
                "Public SPP renewable (wind/solar) forecast-vs-actual dataset not yet located; "
                "see docs/SOURCE_REGISTRY.md and implementation/BLOCKERS.yaml bl-001.",
            ],
            "records": [],
            "record_count": 0,
        }

    # -- observability ---------------------------------------------------

    def read_pipeline_health(self) -> dict:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT source, last_success_at, last_attempt_at, current_watermark, status FROM source_freshness"
            ).fetchall()
        finally:
            con.close()
        result = {
            "source": "source_freshness",
            "records": [
                dict(zip(["source", "last_success_at", "last_attempt_at", "current_watermark", "status"], r,
                         strict=True))
                for r in rows
            ],
            "record_count": len(rows),
        }
        self._audit("read_pipeline_health", {}, False, f"{len(rows)} sources")
        return result

    def read_data_quality_summary(self) -> dict:
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT check_name, status, detail, checked_at
                FROM data_quality_results
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                [MAX_ROWS],
            ).fetchall()
        finally:
            con.close()
        result = {
            "source": "data_quality_results",
            "records": [
                dict(zip(["check_name", "status", "detail", "checked_at"], r, strict=True)) for r in rows
            ],
            "record_count": len(rows),
        }
        self._audit("read_data_quality_summary", {}, False, f"{len(rows)} results")
        return result

    # -- shared -------------------------------------------------------

    def _wrap_result(self, source: str, observation_period: tuple, rows: list, columns: list) -> dict:
        records = [dict(zip(columns, r, strict=True)) for r in rows]
        now = datetime.now(timezone.utc)
        return {
            "source": source,
            "observation_period": {
                "start": observation_period[0].isoformat(),
                "end": observation_period[1].isoformat(),
            },
            "ingestion_timestamp": now.isoformat(),
            "record_count": len(records),
            "quality_status": "quarantine_excluded",
            "known_limitations": [
                "Curated data only -- quarantined/rejected records are never included.",
            ],
            "records": records,
        }
