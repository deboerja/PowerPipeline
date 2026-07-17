"""Exports curated query results to flat JSON snapshots under
POWERPIPELINE_RUNTIME_ROOT/state/latest/, matching the exact convention
already used by the Enphase/weather pipelines (see
docs/EXISTING_COMPONENT_REUSE.md) -- a scheduled job writes JSON, and a
separate, self-contained OpenWebUI tool script reads it.

This exists because the OpenWebUI container does not have `duckdb`
installed, so a ResidentAI-facing tool running inside that container cannot
query the DuckDB file directly. Rather than modify OpenWebUI's shared
container image (out of PowerPipeline's ownership), curated results are
exported here as JSON, which needs no special library to read.

Writes are atomic (temp file + rename) so a partially-written export is
never read by the tool script mid-write.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from powerpipeline import db
from powerpipeline.storage import paths

HISTORY_WINDOW_DAYS = 90
FORECAST_WINDOW_DAYS = 14


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    os.replace(tmp, path)


def _envelope(source: str, records: list, extra: dict | None = None) -> dict:
    envelope = {
        "source": source,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
        "known_limitations": [
            "Static export, refreshed on a schedule -- not a live query. "
            "See generated_at_utc for freshness.",
        ],
    }
    if extra:
        envelope.update(extra)
    return envelope


def export_all(output_dir: Path | None = None, as_of: date | None = None) -> dict:
    """as_of defaults to the real current date in production. Tests pass an
    explicit as_of pinned to their fixture data's date range -- otherwise a
    rolling window silently drifts fixture data out of range as real wall-clock
    time advances (caught by test_openwebui_tool_script.py, which failed when
    run months after the fixtures were dated relative to a fixed "today").
    """
    output_dir = Path(output_dir) if output_dir else paths.runtime_root() / "state" / "latest"
    con = db.connect(read_only=True)
    try:
        today = as_of if as_of is not None else date.today()
        history_start = today - timedelta(days=HISTORY_WINDOW_DAYS)
        forecast_end = today + timedelta(days=FORECAST_WINDOW_DAYS)

        household_history = con.execute(
            """
            SELECT date, solar_production_kwh, completeness_pct, data_status, ingested_at
            FROM fact_household_solar
            WHERE date >= ?
            ORDER BY date
            """,
            [history_start],
        ).fetchall()
        _atomic_write_json(
            output_dir / "household_solar_history.json",
            _envelope(
                "enphase_household_solar",
                [
                    dict(zip(
                        ["date", "solar_production_kwh", "completeness_pct", "data_status", "ingested_at"],
                        r, strict=True,
                    ))
                    for r in household_history
                ],
            ),
        )

        household_forecast = con.execute(
            """
            SELECT forecast_for_date, captured_at_utc, forecast_kwh, ingested_at
            FROM fact_household_solar_forecast
            WHERE forecast_for_date BETWEEN ? AND ?
            ORDER BY forecast_for_date
            """,
            [today, forecast_end],
        ).fetchall()
        _atomic_write_json(
            output_dir / "household_solar_forecast.json",
            _envelope(
                "household_solar_forecast",
                [
                    dict(zip(["forecast_for_date", "captured_at_utc", "forecast_kwh", "ingested_at"], r, strict=True))
                    for r in household_forecast
                ],
            ),
        )

        household_accuracy = con.execute(
            """
            SELECT date, actual_kwh, forecast_kwh, bias_kwh, abs_error_kwh
            FROM v_household_solar_forecast_accuracy
            WHERE date >= ?
            ORDER BY date
            """,
            [history_start],
        ).fetchall()
        _atomic_write_json(
            output_dir / "household_forecast_accuracy.json",
            _envelope(
                "v_household_solar_forecast_accuracy",
                [
                    dict(zip(["date", "actual_kwh", "forecast_kwh", "bias_kwh", "abs_error_kwh"], r, strict=True))
                    for r in household_accuracy
                ],
            ),
        )

        spp_conditions = con.execute(
            """
            SELECT baa, interval_start_utc, interval_end_utc, load_forecast_mw, load_actual_mw
            FROM fact_spp_load_forecast_actual
            WHERE interval_start_utc::DATE >= ?
            ORDER BY baa, interval_start_utc
            """,
            [history_start],
        ).fetchall()
        _atomic_write_json(
            output_dir / "spp_load_conditions.json",
            _envelope(
                "spp_mtlf_vs_actual",
                [
                    dict(zip(
                        ["baa", "interval_start_utc", "interval_end_utc", "load_forecast_mw", "load_actual_mw"],
                        r, strict=True,
                    ))
                    for r in spp_conditions
                ],
            ),
        )

        spp_accuracy = con.execute(
            """
            SELECT baa, day, interval_count, mean_bias_mw, mean_abs_error_mw, mean_abs_pct_error
            FROM v_spp_load_forecast_accuracy
            WHERE day::DATE >= ?
            ORDER BY baa, day
            """,
            [history_start],
        ).fetchall()
        _atomic_write_json(
            output_dir / "spp_load_forecast_accuracy.json",
            _envelope(
                "v_spp_load_forecast_accuracy",
                [
                    dict(zip(
                        ["baa", "day", "interval_count", "mean_bias_mw", "mean_abs_error_mw", "mean_abs_pct_error"],
                        r, strict=True,
                    ))
                    for r in spp_accuracy
                ],
            ),
        )

        health = con.execute(
            "SELECT source, last_success_at, last_attempt_at, current_watermark, status FROM source_freshness"
        ).fetchall()
        _atomic_write_json(
            output_dir / "pipeline_health.json",
            _envelope(
                "source_freshness",
                [
                    dict(zip(
                        ["source", "last_success_at", "last_attempt_at", "current_watermark", "status"],
                        r, strict=True,
                    ))
                    for r in health
                ],
            ),
        )

        quality = con.execute(
            """
            SELECT check_name, status, detail, checked_at
            FROM data_quality_results
            ORDER BY checked_at DESC
            LIMIT 100
            """
        ).fetchall()
        _atomic_write_json(
            output_dir / "data_quality_summary.json",
            _envelope(
                "data_quality_results",
                [dict(zip(["check_name", "status", "detail", "checked_at"], r, strict=True)) for r in quality],
            ),
        )

        return {
            "output_dir": str(output_dir),
            "files_written": 7,
            "household_history_rows": len(household_history),
            "household_forecast_rows": len(household_forecast),
            "spp_conditions_rows": len(spp_conditions),
        }
    finally:
        con.close()


def main() -> None:
    result = export_all()
    print(result)


if __name__ == "__main__":
    main()
