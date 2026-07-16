import io

import pandas as pd

from powerpipeline.contracts.spp_mtlf import validate_raw


def test_valid_fixture_passes_contract(spp_mtlf_fixture_bytes):
    df = pd.read_csv(io.BytesIO(spp_mtlf_fixture_bytes))
    accepted, rejected = validate_raw(df)
    assert accepted is not None
    assert len(accepted) == len(df)
    assert rejected is None or len(rejected) == 0


def test_invalid_baa_is_quarantined(spp_mtlf_fixture_bytes):
    df = pd.read_csv(io.BytesIO(spp_mtlf_fixture_bytes))
    df.loc[0, "BAA"] = "NOT_A_REAL_BAA"
    accepted, rejected = validate_raw(df)
    assert rejected is not None
    assert len(rejected) == 1
    assert "rejection_reason" in rejected.columns
    assert accepted is None or len(accepted) == len(df) - 1


def test_negative_forecast_is_quarantined(spp_mtlf_fixture_bytes):
    df = pd.read_csv(io.BytesIO(spp_mtlf_fixture_bytes))
    df.loc[0, "MTLF"] = -100.0
    accepted, rejected = validate_raw(df)
    assert rejected is not None
    assert len(rejected) == 1


def test_non_numeric_forecast_is_quarantined(spp_mtlf_fixture_bytes):
    # Inject malformed CSV text directly (rather than mutate an already-typed
    # dataframe) so pandas parses MTLF as object dtype the same way it would
    # for real malformed source data, instead of raising pandas' own
    # LossySetitemError before the contract ever runs.
    text = spp_mtlf_fixture_bytes.decode("utf-8")
    lines = text.splitlines()
    header, first_row, rest = lines[0], lines[1], lines[2:]
    parts = first_row.split(",")
    parts[2] = "not-a-number"
    mutated = "\n".join([header, ",".join(parts), *rest]) + "\n"
    df = pd.read_csv(io.StringIO(mutated))
    accepted, rejected = validate_raw(df)
    assert rejected is not None
    assert len(rejected) == 1
