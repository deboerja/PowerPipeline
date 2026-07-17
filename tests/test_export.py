import json
from datetime import date
from pathlib import Path

from powerpipeline import export, pipeline


def test_export_all_writes_expected_files(tmp_path, spp_mtlf_fixture_bytes):
    fixtures = Path(__file__).resolve().parent.parent / "fixtures"
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    pipeline.run_enphase_bridge(fixtures / "enphase" / "daily-summary")
    pipeline.run_weather_bridge(fixtures / "weather" / "daily-actual")
    pipeline.run_household_solar_forecast_bridge(
        fixtures / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )

    out_dir = tmp_path / "state" / "latest"
    result = export.export_all(output_dir=out_dir, as_of=date(2026, 1, 15))
    assert result["files_written"] == 7

    expected_files = [
        "household_solar_history.json",
        "household_solar_forecast.json",
        "household_forecast_accuracy.json",
        "spp_load_conditions.json",
        "spp_load_forecast_accuracy.json",
        "pipeline_health.json",
        "data_quality_summary.json",
    ]
    for filename in expected_files:
        f = out_dir / filename
        assert f.exists(), f"{filename} was not written"
        data = json.loads(f.read_text())
        assert "source" in data
        assert "generated_at_utc" in data
        assert "records" in data
        assert "record_count" in data


def test_export_is_atomic_no_tmp_file_left_behind(tmp_path, spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    out_dir = tmp_path / "state" / "latest"
    export.export_all(output_dir=out_dir, as_of=date(2026, 1, 15))
    tmp_files = list(out_dir.glob("*.tmp"))
    assert tmp_files == []


def test_pipeline_health_export_reflects_real_source_status(tmp_path, spp_mtlf_fixture_bytes):
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    out_dir = tmp_path / "state" / "latest"
    export.export_all(output_dir=out_dir, as_of=date(2026, 1, 15))
    data = json.loads((out_dir / "pipeline_health.json").read_text())
    sources = {r["source"] for r in data["records"]}
    assert "spp_mtlf" in sources
