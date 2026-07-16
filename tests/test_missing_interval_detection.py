import io

import pandas as pd

from powerpipeline import db, pipeline


def _drop_one_interval(raw_csv: bytes, baa: str) -> bytes:
    """Remove one row for a given BAA to create a genuine hour-sized gap,
    simulating a source file that's missing an interval.
    """
    df = pd.read_csv(io.BytesIO(raw_csv))
    subset = df[df["BAA"] == baa].sort_values("GMTIntervalEnd")
    drop_index = subset.index[len(subset) // 2]
    df = df.drop(index=drop_index)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def test_missing_interval_is_detected_not_interpolated(spp_mtlf_fixture_bytes):
    gappy_csv = _drop_one_interval(spp_mtlf_fixture_bytes, "SPP")
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=gappy_csv)

    con = db.connect(read_only=True)
    try:
        result = con.execute(
            "SELECT status, detail FROM data_quality_results WHERE check_name = 'missing_interval_completeness'"
        ).fetchone()
        assert result[0] == "fail"
        assert "gap" in result[1]

        # The missing hour must not appear with a fabricated/interpolated value.
        spp_rows = con.execute(
            "SELECT count(*) FROM fact_spp_load_forecast_actual WHERE baa = 'SPP'"
        ).fetchone()[0]
        original_spp_rows = pd.read_csv(io.BytesIO(spp_mtlf_fixture_bytes))
        original_spp_count = len(original_spp_rows[original_spp_rows["BAA"] == "SPP"])
        assert spp_rows == original_spp_count - 1
    finally:
        con.close()


def test_complete_data_passes_completeness_check(spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    con = db.connect(read_only=True)
    try:
        result = con.execute(
            "SELECT status FROM data_quality_results WHERE check_name = 'missing_interval_completeness'"
        ).fetchone()
        assert result[0] == "pass"
    finally:
        con.close()
