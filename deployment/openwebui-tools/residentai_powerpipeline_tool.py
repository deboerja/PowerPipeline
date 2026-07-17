"""
title: ResidentAI PowerPipeline (SPP + Household Energy)
author: deboerja / ResidentAI
version: 1.0.0
description: Bounded read-only access to curated Southwest Power Pool (SPP) regional load/forecast data and household solar production/forecast data, plus pipeline health and data-quality status. Reads only pre-exported, scheduled JSON snapshots -- never queries a live database, never accepts a SQL string, never writes anything. The SPP renewable (wind/solar) forecast-vs-actual dataset is not yet available upstream and is reported honestly as such rather than fabricated.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

MAX_DATE_RANGE_DAYS = 366
MAX_ROWS = 500
VALID_BAA = {"SPP", "SWPW"}


class Tools:
    class Valves(BaseModel):
        state_dir: str = Field(
            default="/srv/apps/powerpipeline/state/latest",
            description=(
                "In-container path to PowerPipeline's exported JSON snapshots "
                "(household_solar_history.json, household_solar_forecast.json, "
                "household_forecast_accuracy.json, spp_load_conditions.json, "
                "spp_load_forecast_accuracy.json, pipeline_health.json, "
                "data_quality_summary.json), refreshed on a schedule by "
                "powerpipeline-quality-check.timer. Must be mounted read-only "
                "into this container -- see /srv/compose/ai/docker-compose.yml."
            ),
        )

    def __init__(self):
        self.valves = self.Valves()

    def _safe_error(self, reason: str, detail: str) -> Dict[str, Any]:
        return {"ok": False, "reason": reason, "detail": detail}

    def _read_json(self, filename: str) -> Optional[Dict[str, Any]]:
        path = Path(self.valves.state_dir) / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _validate_date_range(self, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except (TypeError, ValueError) as exc:
            return self._safe_error("invalid_date_format", f"Expected YYYY-MM-DD: {exc}")
        if start > end:
            return self._safe_error("invalid_date_range", "start_date must not be after end_date")
        if (end - start).days > MAX_DATE_RANGE_DAYS:
            return self._safe_error("date_range_too_large", f"Maximum range is {MAX_DATE_RANGE_DAYS} days")
        return None

    def _filter_by_date(self, records: List[dict], date_field: str, start_date: str, end_date: str) -> List[dict]:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        filtered = []
        for r in records:
            raw = r.get(date_field)
            if not raw:
                continue
            try:
                record_date = date.fromisoformat(str(raw)[:10])
            except ValueError:
                continue
            if start <= record_date <= end:
                filtered.append(r)
        return filtered[:MAX_ROWS]

    def _envelope(self, source: str, export: dict, records: List[dict]) -> Dict[str, Any]:
        return {
            "ok": True,
            "source": source,
            "export_generated_at_utc": export.get("generated_at_utc"),
            "record_count": len(records),
            "records": records,
            "known_limitations": export.get("known_limitations", []),
        }

    def read_household_solar_history(self, start_date: str, end_date: str) -> str:
        """
        Retrieve curated daily household solar production (kWh) for a date
        range, from the existing Enphase pipeline's curated summaries.
        Only already-ingested dates are returned -- this never triggers a
        new ingestion. Maximum range is 366 days; results are capped at 500
        rows.
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        export = self._read_json("household_solar_history.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "household_solar_history.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        records = self._filter_by_date(export.get("records", []), "date", start_date, end_date)
        return json.dumps(self._envelope("enphase_household_solar", export, records), indent=2, sort_keys=True)

    def read_household_solar_forecast(self, start_date: str, end_date: str) -> str:
        """
        Retrieve the household solar production forecast (kWh) for a date
        range, from the existing physics-based projection model. Only
        covers roughly the next 14 days from the last export -- this is a
        short-term forecast, not a historical archive.
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        export = self._read_json("household_solar_forecast.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "household_solar_forecast.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        records = self._filter_by_date(export.get("records", []), "forecast_for_date", start_date, end_date)
        return json.dumps(self._envelope("household_solar_forecast", export, records), indent=2, sort_keys=True)

    def read_household_forecast_accuracy(self, start_date: str, end_date: str) -> str:
        """
        Retrieve household solar forecast-vs-actual accuracy (bias and
        absolute error in kWh) for a date range, for days where both a
        forecast and an actual are available.
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        export = self._read_json("household_forecast_accuracy.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "household_forecast_accuracy.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        records = self._filter_by_date(export.get("records", []), "date", start_date, end_date)
        return json.dumps(self._envelope("v_household_solar_forecast_accuracy", export, records), indent=2, sort_keys=True)

    def read_spp_load_conditions(self, start_date: str, end_date: str, baa: str = "SPP") -> str:
        """
        Retrieve Southwest Power Pool hourly load and load-forecast data
        (megawatts) for a date range and balancing area ("SPP" for the
        Eastern Interconnect, "SWPW" for the Western Interconnect).
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        if baa not in VALID_BAA:
            return json.dumps(
                self._safe_error("invalid_baa", f"baa must be one of {sorted(VALID_BAA)}"),
                indent=2, sort_keys=True,
            )
        export = self._read_json("spp_load_conditions.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "spp_load_conditions.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        records = [r for r in export.get("records", []) if r.get("baa") == baa]
        records = self._filter_by_date(records, "interval_start_utc", start_date, end_date)
        return json.dumps(self._envelope("spp_mtlf_vs_actual", export, records), indent=2, sort_keys=True)

    def read_spp_load_forecast_accuracy(self, start_date: str, end_date: str, baa: str = "SPP") -> str:
        """
        Retrieve daily SPP load forecast-vs-actual accuracy metrics (mean
        bias, mean absolute error, mean absolute percent error in MW) for
        a date range and balancing area.
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        if baa not in VALID_BAA:
            return json.dumps(
                self._safe_error("invalid_baa", f"baa must be one of {sorted(VALID_BAA)}"),
                indent=2, sort_keys=True,
            )
        export = self._read_json("spp_load_forecast_accuracy.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "spp_load_forecast_accuracy.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        records = [r for r in export.get("records", []) if r.get("baa") == baa]
        records = self._filter_by_date(records, "day", start_date, end_date)
        return json.dumps(self._envelope("v_spp_load_forecast_accuracy", export, records), indent=2, sort_keys=True)

    def read_spp_renewable_conditions(self, start_date: str, end_date: str) -> str:
        """
        Retrieve Southwest Power Pool renewable (wind/solar) generation
        forecast-vs-actual data. NOT CURRENTLY AVAILABLE: the public SPP
        dataset for this has not yet been located (see PowerPipeline's
        implementation/BLOCKERS.yaml bl-001). This always returns an
        honest "not available" result rather than fabricated numbers.
        """
        error = self._validate_date_range(start_date, end_date)
        if error:
            return json.dumps(error, indent=2, sort_keys=True)
        result = {
            "ok": True,
            "source": "spp_renewable_forecast_vs_actual",
            "status": "not_available",
            "record_count": 0,
            "records": [],
            "known_limitations": [
                "Public SPP renewable (wind/solar) forecast-vs-actual dataset not yet "
                "located. See PowerPipeline's docs/SOURCE_REGISTRY.md and "
                "implementation/BLOCKERS.yaml bl-001.",
            ],
        }
        return json.dumps(result, indent=2, sort_keys=True)

    def read_pipeline_health(self) -> str:
        """
        Retrieve PowerPipeline's own operational health: for each data
        source (SPP load, household solar, weather, household solar
        forecast), the last successful run time, last attempted run time,
        current watermark, and freshness status (fresh/stale/failing).
        """
        export = self._read_json("pipeline_health.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "pipeline_health.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        return json.dumps(
            self._envelope("source_freshness", export, export.get("records", [])), indent=2, sort_keys=True
        )

    def read_data_quality_summary(self) -> str:
        """
        Retrieve PowerPipeline's most recent data-quality check results
        (completeness, missing-interval detection, source-freshness sweep)
        -- pass/fail status and detail for each check.
        """
        export = self._read_json("data_quality_summary.json")
        if export is None:
            return json.dumps(
                self._safe_error("export_not_available", "data_quality_summary.json not found or unreadable."),
                indent=2, sort_keys=True,
            )
        return json.dumps(
            self._envelope("data_quality_results", export, export.get("records", [])), indent=2, sort_keys=True
        )
