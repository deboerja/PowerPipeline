"""Data contract for SPP's mtlf-vs-actual dataset (Mid-Term Load Forecast vs.
Actual). Raw CSV schema, as published by portal.spp.org, before any
normalization: `Interval,GMTIntervalEnd,MTLF,Averaged Actual,BAA`.

`Interval` is SPP's local operating time (Central); `GMTIntervalEnd` is UTC.
`MTLF` (forecast, MW) is always present. `Averaged Actual` (MW) is empty for
intervals whose actual hasn't been published yet — that's expected, not a
defect, and callers must not treat an empty actual as an invalid record.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series

VALID_BAA = {"SPP", "SWPW"}


class SppMtlfRawSchema(pa.DataFrameModel):
    Interval: Series[str] = pa.Field(nullable=False)
    GMTIntervalEnd: Series[str] = pa.Field(nullable=False)
    MTLF: Series[float] = pa.Field(nullable=False, ge=0)
    Averaged_Actual: Series[float] = pa.Field(
        nullable=True, ge=0, alias="Averaged Actual"
    )
    BAA: Series[str] = pa.Field(nullable=False, isin=VALID_BAA)

    class Config:
        strict = True
        coerce = True


def validate_raw(df):
    """Validate a raw SPP MTLF dataframe.

    Returns (valid_rows, rejected_rows_with_reason) — rejected rows are never
    silently dropped; callers must route them to quarantine.
    """
    try:
        validated = SppMtlfRawSchema.validate(df, lazy=True)
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
            accepted = SppMtlfRawSchema.validate(accepted)
        return accepted, rejected
