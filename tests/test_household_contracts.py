import pandas as pd

from powerpipeline.contracts.enphase_summary import validate_raw as validate_enphase
from powerpipeline.contracts.household_solar_forecast import validate_raw as validate_forecast
from powerpipeline.contracts.weather_actual import validate_raw as validate_weather


def test_enphase_contract_rejects_negative_production():
    df = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "system": "home-solar",
                "solar_production_kwh": -5.0,
                "completeness_pct": 100.0,
                "data_status": "complete",
                "source_file": "2026-01-01.json",
                "ingested_at": "2026-01-02T00:00:00Z",
            }
        ]
    )
    accepted, rejected = validate_enphase(df)
    assert rejected is not None
    assert len(rejected) == 1


def test_weather_contract_rejects_impossible_temperature():
    df = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "station": "KMDS",
                "timestamp_local": "2026-01-01T00:00:00-06:00",
                "sky_cover_pct": 50.0,
                "temperature_c": 999.0,
                "source_file": "2026-01-01.json",
            }
        ]
    )
    accepted, rejected = validate_weather(df)
    assert rejected is not None
    assert len(rejected) == 1


def test_household_forecast_contract_rejects_negative_forecast():
    df = pd.DataFrame(
        [
            {
                "forecast_for_date": "2026-01-02",
                "captured_at_utc": "2026-01-01T15:00:00Z",
                "forecast_kwh": -1.0,
                "source_file": "proj.json",
            }
        ]
    )
    accepted, rejected = validate_forecast(df)
    assert rejected is not None
    assert len(rejected) == 1
