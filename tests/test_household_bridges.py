from pathlib import Path

from powerpipeline import db, pipeline

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_enphase_bridge_ingests_curated_summaries():
    result = pipeline.run_enphase_bridge(FIXTURES / "enphase" / "daily-summary")
    assert result["status"] == "success"
    assert result["records_accepted"] == 3  # 2026-01-01, 02, 04 (03 deliberately missing)

    con = db.connect(read_only=True)
    try:
        rows = con.execute("SELECT date, solar_production_kwh FROM fact_household_solar ORDER BY date").fetchall()
        assert len(rows) == 3
    finally:
        con.close()


def test_weather_bridge_ingests_and_aggregates_daily():
    result = pipeline.run_weather_bridge(FIXTURES / "weather" / "daily-actual")
    assert result["status"] == "success"
    assert result["records_accepted"] == 2  # two fixture days, aggregated to one row each

    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            "SELECT date, station, avg_temperature_c FROM fact_weather_actual ORDER BY date"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "KMDS"
    finally:
        con.close()


def test_household_solar_forecast_bridge_ingests():
    result = pipeline.run_household_solar_forecast_bridge(
        FIXTURES / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )
    assert result["status"] == "success"
    assert result["records_accepted"] == 4

    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            "SELECT forecast_for_date, forecast_kwh FROM fact_household_solar_forecast ORDER BY forecast_for_date"
        ).fetchall()
        assert len(rows) == 4
    finally:
        con.close()


def test_household_forecast_accuracy_view_joins_actual_and_forecast():
    pipeline.run_enphase_bridge(FIXTURES / "enphase" / "daily-summary")
    pipeline.run_household_solar_forecast_bridge(
        FIXTURES / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )
    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            "SELECT date, actual_kwh, forecast_kwh, bias_kwh FROM v_household_solar_forecast_accuracy ORDER BY date"
        ).fetchall()
        # Actuals exist for 01-01, 01-02, 01-04; forecasts exist for 01-02..01-05.
        # Only the overlap (01-02, 01-04) should produce accuracy rows.
        assert len(rows) == 2
        dates = [r[0].isoformat() for r in rows]
        assert dates == ["2026-01-02", "2026-01-04"]
    finally:
        con.close()
