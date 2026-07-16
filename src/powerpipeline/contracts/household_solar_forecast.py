"""Data contract for the existing weather pipeline's household solar
production projection (`solar_production_projection.json`), flattened from
its `projection_days` list into one row per forecasted date. Reused
read-only -- see docs/EXISTING_COMPONENT_REUSE.md.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class HouseholdSolarForecastSchema(pa.DataFrameModel):
    forecast_for_date: Series[str] = pa.Field(nullable=False)
    captured_at_utc: Series[str] = pa.Field(nullable=False)
    forecast_kwh: Series[float] = pa.Field(nullable=False, ge=0)
    source_file: Series[str] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


def validate_raw(df):
    try:
        validated = HouseholdSolarForecastSchema.validate(df, lazy=True)
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
            accepted = HouseholdSolarForecastSchema.validate(accepted)
        return accepted, rejected
