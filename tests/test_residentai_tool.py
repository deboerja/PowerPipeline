from pathlib import Path

import pytest

from powerpipeline import pipeline
from powerpipeline.residentai_tool import DateRangeError, ResidentAiReadOnlyTool

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def loaded_tool(spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    pipeline.run_enphase_bridge(FIXTURES / "enphase" / "daily-summary")
    pipeline.run_household_solar_forecast_bridge(
        FIXTURES / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )
    return ResidentAiReadOnlyTool()


def test_named_operation_returns_provenance_and_quality_metadata(loaded_tool):
    result = loaded_tool.read_spp_load_conditions("2026-07-15", "2026-07-15", baa="SPP")
    assert result["record_count"] > 0
    assert result["source"] == "spp_mtlf_vs_actual"
    assert "observation_period" in result
    assert "ingestion_timestamp" in result
    assert "quality_status" in result
    assert "known_limitations" in result


def test_household_solar_history_works(loaded_tool):
    result = loaded_tool.read_household_solar_history("2026-01-01", "2026-01-31")
    assert result["record_count"] == 3


def test_invalid_baa_rejected(loaded_tool):
    with pytest.raises(ValueError):
        loaded_tool.read_spp_load_conditions("2026-07-15", "2026-07-15", baa="NOT_REAL")


def test_date_range_exceeding_maximum_rejected(loaded_tool):
    with pytest.raises(DateRangeError):
        loaded_tool.read_spp_load_conditions("2020-01-01", "2026-01-01", baa="SPP")


def test_inverted_date_range_rejected(loaded_tool):
    with pytest.raises(DateRangeError):
        loaded_tool.read_spp_load_conditions("2026-07-15", "2026-07-01", baa="SPP")


def test_malformed_date_rejected(loaded_tool):
    with pytest.raises(DateRangeError):
        loaded_tool.read_spp_load_conditions("not-a-date", "2026-07-15", baa="SPP")


def test_renewable_conditions_honestly_reports_unavailable(loaded_tool):
    result = loaded_tool.read_spp_renewable_conditions("2026-07-01", "2026-07-15")
    assert result["status"] == "not_available"
    assert result["record_count"] == 0
    assert "bl-001" in result["known_limitations"][0]


def test_pipeline_health_and_quality_summary_return_real_data(loaded_tool):
    health = loaded_tool.read_pipeline_health()
    assert health["record_count"] > 0
    quality = loaded_tool.read_data_quality_summary()
    assert quality["record_count"] > 0


def test_no_arbitrary_sql_method_exists(loaded_tool):
    """Structural test: there is no method on this class that accepts a raw
    SQL string. This is not a permissions check -- the method literally
    doesn't exist.
    """
    forbidden_names = {"query", "execute", "execute_sql", "run_sql", "sql"}
    actual_methods = {name for name in dir(loaded_tool) if not name.startswith("_")}
    assert forbidden_names.isdisjoint(actual_methods)


def test_underlying_connection_is_read_only_and_rejects_writes(loaded_tool):
    """Even if something obtained the tool's connection directly, DuckDB
    itself refuses writes on a read_only=True connection.
    """
    con = loaded_tool._connect()
    try:
        with pytest.raises(Exception):
            con.execute("DELETE FROM fact_household_solar")
        with pytest.raises(Exception):
            con.execute("DROP TABLE fact_spp_load_forecast_actual")
        with pytest.raises(Exception):
            con.execute("INSERT INTO fact_household_solar VALUES ('2099-01-01', 1.0, 100.0, 'complete', 'x', now(), 'y')")
    finally:
        con.close()


def test_audit_log_written_for_every_call(loaded_tool, monkeypatch):
    loaded_tool.read_pipeline_health()
    assert loaded_tool._audit_log_path.exists()
    lines = loaded_tool._audit_log_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    import json
    record = json.loads(lines[-1])
    assert record["action"] == "read_pipeline_health"
    assert "execution_id" in record
    assert "timestamp_utc" in record
