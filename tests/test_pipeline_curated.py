from powerpipeline import db, pipeline


def test_full_run_upserts_curated_and_records_run(spp_mtlf_fixture_bytes):
    result = pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    assert result["status"] == "success"
    assert result["records_accepted"] > 0

    con = db.connect(read_only=True)
    try:
        row_count = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
        assert row_count == result["records_accepted"]

        run_count = con.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0]
        assert run_count == 1

        quality_count = con.execute("SELECT count(*) FROM data_quality_results").fetchone()[0]
        assert quality_count == 1
    finally:
        con.close()


def test_rerun_is_idempotent_no_duplicate_curated_rows(spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    result2 = pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)

    con = db.connect(read_only=True)
    try:
        row_count = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
        assert row_count == result2["records_accepted"]

        run_count = con.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0]
        assert run_count == 2  # two runs recorded...
        assert row_count < run_count * result2["records_accepted"]  # ...but curated rows didn't double
    finally:
        con.close()


def test_forecast_accuracy_view_returns_rows_with_published_actuals(spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    con = db.connect(read_only=True)
    try:
        rows = con.execute("SELECT * FROM v_spp_load_forecast_accuracy").fetchall()
        assert len(rows) > 0
    finally:
        con.close()
