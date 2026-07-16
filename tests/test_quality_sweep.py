from powerpipeline import db, pipeline


def test_quality_sweep_runs_with_no_data(spp_mtlf_fixture_bytes):
    # Even with nothing ingested yet, the sweep must run cleanly and record
    # its own pipeline_runs + data_quality_results rows rather than error.
    result = pipeline.run_quality_sweep()
    con = db.connect(read_only=True)
    try:
        run_row = con.execute(
            "SELECT status FROM pipeline_runs WHERE run_id = ?", [result["run_id"]]
        ).fetchone()
        assert run_row[0] == "success"
        quality_row = con.execute(
            "SELECT status FROM data_quality_results WHERE check_name = 'source_freshness_sweep'"
        ).fetchone()
        assert quality_row is not None
    finally:
        con.close()


def test_quality_sweep_flags_stale_source_after_ingest(spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    result = pipeline.run_quality_sweep()
    # A source that just succeeded should not itself be flagged as stale.
    con = db.connect(read_only=True)
    try:
        row = con.execute(
            "SELECT status FROM source_freshness WHERE source = 'spp_mtlf'"
        ).fetchone()
        assert row[0] == "fresh"
    finally:
        con.close()
    assert result["stale_sources"] == 0
