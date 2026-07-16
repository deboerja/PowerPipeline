"""Data contract for the existing weather pipeline's curated daily-actual
JSON (homelab/scripts weather-projection). Validated per-reading, after
flattening the source file's nested `readings` list into rows -- PowerPipeline
re-validates read-only; it never calls NWS/IEM itself for this data.
See docs/EXISTING_COMPONENT_REUSE.md.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class WeatherReadingSchema(pa.DataFrameModel):
    date: Series[str] = pa.Field(nullable=False)
    station: Series[str] = pa.Field(nullable=False)
    timestamp_local: Series[str] = pa.Field(nullable=False)
    sky_cover_pct: Series[float] = pa.Field(nullable=True, ge=0, le=100)
    temperature_c: Series[float] = pa.Field(nullable=True, ge=-90, le=60)
    source_file: Series[str] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


def validate_raw(df):
    try:
        validated = WeatherReadingSchema.validate(df, lazy=True)
        return validated, None
    except pa.errors.SchemaErrors as exc:
        failure_cases = exc.failure_cases
        bad_indices = set(failure_cases["index"].dropna().astype(int))
        rejected = df.loc[df.index.isin(bad_indices)].copy()
        rejected["rejection_reason"] = rejected.index.map(
            lambda i: "; ".join(
                failure_cases.loc[failure_cases["index"] == i, "check"].astype(str)
            )
        )
        accepted = df.loc[~df.index.isin(bad_indices)]
        if len(accepted) > 0:
            accepted = WeatherReadingSchema.validate(accepted)
        return accepted, rejected
