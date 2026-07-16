"""Bridge for the existing weather pipeline's curated daily-actual output.
Read-only; no NWS/IEM network calls originate from PowerPipeline for this
data. See docs/EXISTING_COMPONENT_REUSE.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from powerpipeline.contracts.weather_actual import validate_raw
from powerpipeline.storage import paths


def land_raw(source_path: Path, date: str) -> Path:
    dest_dir = paths.raw_dir("weather", "daily-actual")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{date}.json"
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


def _flatten(record: dict, source_file: str) -> list[dict]:
    rows = []
    for reading in record.get("readings", []):
        rows.append(
            {
                "date": record.get("date"),
                "station": record.get("station"),
                "timestamp_local": reading.get("timestamp_local"),
                "sky_cover_pct": reading.get("sky_cover_pct"),
                "temperature_c": reading.get("temperature_c"),
                "source_file": source_file,
            }
        )
    return rows


def parse_and_normalize(files: list[Path]) -> tuple:
    rows = []
    for f in files:
        with open(f) as fh:
            record = json.load(fh)
        rows.extend(_flatten(record, f.name))
    df = pd.DataFrame(rows)
    accepted, rejected = validate_raw(df)
    daily = None
    if accepted is not None and len(accepted):
        accepted = accepted.copy()
        accepted["date"] = pd.to_datetime(accepted["date"]).dt.date
        daily = (
            accepted.groupby(["date", "station"], as_index=False)
            .agg(
                avg_temperature_c=("temperature_c", "mean"),
                avg_sky_cover_pct=("sky_cover_pct", "mean"),
                source_file=("source_file", "first"),
            )
        )
    return daily, rejected


def ingest_directory(snapshots_dir: Path) -> tuple:
    files = sorted(Path(snapshots_dir).glob("*.json"))
    landed = [land_raw(f, f.stem) for f in files]
    return parse_and_normalize(landed)
