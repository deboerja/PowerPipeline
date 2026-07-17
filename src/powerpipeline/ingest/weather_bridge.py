"""Bridge for the existing weather pipeline's curated daily-actual output.
Read-only; no NWS/IEM network calls originate from PowerPipeline for this
data. See docs/EXISTING_COMPONENT_REUSE.md.

Design note on "immutable" raw landing for this source specifically: unlike
SPP's hourly files (genuinely immutable once published), the upstream
weather pipeline's daily-actual file for *today's* date is still being
appended to in place every 30 minutes until its own nightly job finalizes
it after midnight -- discovered in production 2026-07-17 when a
30-minutes-later household-bridge run hit a raw-landing collision on the
still-updating current day (see docs/DECISION_LOG.md). Rather than fail on
that expected mismatch, each distinct observed version of a date's file is
landed under its own capture-timestamped filename -- still genuinely
immutable (a landed file is never overwritten), just no longer assuming
one file equals one final version. Ingestion always uses the latest
captured version per date, since later captures of a still-filling-in day
are more complete.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from powerpipeline.contracts.weather_actual import validate_raw
from powerpipeline.ingest.land import land_versioned_snapshot
from powerpipeline.storage import paths

_CAPTURE_SUFFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:__.*)?$")


def land_raw(source_path: Path, date: str) -> Path:
    dest_dir = paths.raw_dir("weather", "daily-actual")
    return land_versioned_snapshot(dest_dir, date, source_path.read_bytes())


def _date_from_filename(path: Path) -> str:
    match = _CAPTURE_SUFFIX_RE.match(path.stem)
    return match.group(1) if match else path.stem


def _latest_per_date(files: list[Path]) -> list[Path]:
    """Among all landed raw files, keep only the most-recently-modified one
    per source date, so a still-evolving "today" file isn't double-counted
    or averaged across its earlier, less-complete captures.
    """
    latest: dict[str, Path] = {}
    for f in sorted(files, key=lambda p: p.stat().st_mtime):
        latest[_date_from_filename(f)] = f
    return list(latest.values())


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
    files = _latest_per_date(files)
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
