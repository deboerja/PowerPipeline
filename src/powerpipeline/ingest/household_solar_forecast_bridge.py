"""Bridge for the existing weather pipeline's household solar production
projection (`solar_production_projection.json`). Unlike the daily-actual
snapshots, this upstream file is overwritten in place on every run -- it has
no history of its own. PowerPipeline therefore snapshots it under its own
`captured_at`-based filename on each read, so PowerPipeline's own raw
landing preserves history the upstream doesn't. See
docs/DATA_LINEAGE.md and docs/EXISTING_COMPONENT_REUSE.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from powerpipeline.contracts.household_solar_forecast import validate_raw
from powerpipeline.storage import paths


def land_raw(source_path: Path) -> Path:
    with open(source_path) as f:
        record = json.load(f)
    captured_at = record.get("generated_at_utc", "unknown").replace(":", "").replace(".", "")
    dest_dir = paths.raw_dir("solar_forecast")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{captured_at}.json"
    content = source_path.read_bytes()
    if dest.exists():
        if dest.read_bytes() != content:
            raise ValueError(
                f"Raw landing collision: {dest} already exists with different content. "
                "Raw landing is immutable."
            )
        return dest
    dest.write_bytes(content)
    return dest


def parse_and_normalize(raw_path: Path) -> tuple:
    with open(raw_path) as f:
        record = json.load(f)
    captured_at_utc = record.get("generated_at_utc")
    rows = [
        {
            "forecast_for_date": day.get("date"),
            "captured_at_utc": captured_at_utc,
            "forecast_kwh": day.get("projected_kwh"),
            "source_file": raw_path.name,
        }
        for day in record.get("projection_days", [])
    ]
    df = pd.DataFrame(rows)
    accepted, rejected = validate_raw(df)
    if accepted is not None and len(accepted):
        accepted = accepted.copy()
        accepted["forecast_for_date"] = pd.to_datetime(accepted["forecast_for_date"]).dt.date
        accepted["captured_at_utc"] = pd.to_datetime(accepted["captured_at_utc"], utc=True)
    return accepted, rejected


def ingest_file(source_path: Path) -> tuple:
    raw_path = land_raw(source_path)
    return parse_and_normalize(raw_path)
