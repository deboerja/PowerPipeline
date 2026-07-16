"""Bridge for the existing Enphase pipeline's curated daily-summary output.
PowerPipeline reads these files read-only (no Enphase credentials, no
network calls to Enphase) and re-validates them under its own contract --
see docs/EXISTING_COMPONENT_REUSE.md for why this is reused rather than
rebuilt, and docs/SECURITY_AND_AUTHORITY.md for the read-only boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from powerpipeline.contracts.enphase_summary import validate_raw
from powerpipeline.storage import paths


def land_raw(source_path: Path, date: str) -> Path:
    dest_dir = paths.raw_dir("enphase", "daily-summary")
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


def read_one(source_path: Path) -> dict:
    with open(source_path) as f:
        return json.load(f)


def parse_and_normalize(records: list[dict], source_files: list[str]) -> tuple:
    rows = []
    for record, source_file in zip(records, source_files):
        rows.append(
            {
                "date": record.get("date"),
                "system": record.get("system"),
                "solar_production_kwh": record.get("solar_production_kwh"),
                "completeness_pct": record.get("completeness_pct"),
                "data_status": record.get("data_status"),
                "source_file": source_file,
                "ingested_at": record.get("ingested_at"),
            }
        )
    df = pd.DataFrame(rows)
    accepted, rejected = validate_raw(df)
    if accepted is not None and len(accepted):
        accepted = accepted.copy()
        accepted["date"] = pd.to_datetime(accepted["date"]).dt.date
    return accepted, rejected


def ingest_directory(snapshots_dir: Path) -> tuple:
    """Ingest every daily-summary file found in an Enphase snapshots
    directory (or a fixtures directory laid out the same way).
    """
    files = sorted(Path(snapshots_dir).glob("*.json"))
    records, source_files = [], []
    for f in files:
        date = f.stem
        raw_path = land_raw(f, date)
        records.append(read_one(raw_path))
        source_files.append(raw_path.name)
    normalized, rejected = parse_and_normalize(records, source_files)
    return normalized, rejected
