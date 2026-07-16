from powerpipeline.ingest import spp_load


def test_ingest_file_lands_raw_and_normalizes(spp_mtlf_fixture_bytes):
    result = spp_load.ingest_file(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    assert result.raw_path.exists()
    assert result.records_accepted > 0
    assert result.normalized_path is not None
    assert result.normalized_path.exists()


def test_raw_landing_is_idempotent_for_identical_content(spp_mtlf_fixture_bytes):
    r1 = spp_load.ingest_file(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    r2 = spp_load.ingest_file(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    assert r1.raw_path == r2.raw_path
    assert r1.raw_path.read_bytes() == spp_mtlf_fixture_bytes


def test_raw_landing_rejects_content_mismatch(spp_mtlf_fixture_bytes):
    spp_load.ingest_file(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    mutated = spp_mtlf_fixture_bytes + b"\nextra,garbage,row,here,SPP\n"
    try:
        spp_load.ingest_file(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=mutated)
        assert False, "expected a ValueError for raw content mismatch"
    except ValueError as exc:
        assert "immutable" in str(exc)


def test_normalization_produces_utc_columns_and_dedupes(spp_mtlf_fixture_bytes):
    normalized, rejected = spp_load.parse_and_normalize(spp_mtlf_fixture_bytes)
    assert "interval_start_utc" in normalized.columns
    assert "interval_end_utc" in normalized.columns
    # baa+interval_start_utc should be unique after dedup
    assert normalized.duplicated(subset=["baa", "interval_start_utc"]).sum() == 0
