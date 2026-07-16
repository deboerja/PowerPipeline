"""Data contract for the existing Enphase pipeline's curated daily-summary
JSON (homelab/scripts, homelab_scripts/runtime/enphase-energy/). PowerPipeline
reads this file read-only and re-validates it -- it never authenticates to
Enphase itself. See docs/EXISTING_COMPONENT_REUSE.md.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series

VALID_STATUS = {"complete", "partial", "missing"}


class EnphaseDailySummarySchema(pa.DataFrameModel):
    date: Series[str] = pa.Field(nullable=False)
    system: Series[str] = pa.Field(nullable=False)
    solar_production_kwh: Series[float] = pa.Field(nullable=False, ge=0)
    completeness_pct: Series[float] = pa.Field(nullable=True, ge=0, le=100)
    data_status: Series[str] = pa.Field(nullable=True, isin=VALID_STATUS)
    source_file: Series[str] = pa.Field(nullable=False)
    ingested_at: Series[str] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


def validate_raw(df):
    try:
        validated = EnphaseDailySummarySchema.validate(df, lazy=True)
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
            accepted = EnphaseDailySummarySchema.validate(accepted)
        return accepted, rejected
