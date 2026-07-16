-- PowerPipeline curated + metadata schema (DuckDB)
-- Applied fresh to an empty database file. Idempotent: CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS fact_spp_load_forecast_actual (
    baa                 VARCHAR NOT NULL,           -- 'SPP' (Eastern) or 'SWPW' (Western)
    interval_start_utc  TIMESTAMPTZ NOT NULL,
    interval_end_utc    TIMESTAMPTZ NOT NULL,
    load_forecast_mw    DOUBLE NOT NULL,
    load_actual_mw      DOUBLE,                      -- NULL until SPP publishes the actual
    source_file         VARCHAR NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL,
    pipeline_run_id     VARCHAR NOT NULL,
    PRIMARY KEY (baa, interval_start_utc)
);

CREATE TABLE IF NOT EXISTS fact_household_solar (
    date                DATE NOT NULL,
    solar_production_kwh DOUBLE NOT NULL,
    completeness_pct    DOUBLE,
    data_status         VARCHAR,
    source_file         VARCHAR NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL,
    pipeline_run_id     VARCHAR NOT NULL,
    PRIMARY KEY (date)
);

CREATE TABLE IF NOT EXISTS fact_household_solar_forecast (
    forecast_for_date   DATE NOT NULL,
    captured_at_utc     TIMESTAMPTZ NOT NULL,
    forecast_kwh        DOUBLE NOT NULL,
    source_file         VARCHAR NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL,
    pipeline_run_id     VARCHAR NOT NULL,
    PRIMARY KEY (forecast_for_date, captured_at_utc)
);

CREATE TABLE IF NOT EXISTS fact_weather_actual (
    date                DATE NOT NULL,
    station             VARCHAR NOT NULL,
    avg_temperature_c    DOUBLE,
    avg_sky_cover_pct    DOUBLE,
    source_file         VARCHAR NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL,
    pipeline_run_id     VARCHAR NOT NULL,
    PRIMARY KEY (date, station)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              VARCHAR NOT NULL PRIMARY KEY,
    source              VARCHAR NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    finished_at         TIMESTAMPTZ,
    status              VARCHAR NOT NULL,            -- 'success' | 'failed' | 'partial'
    records_in          INTEGER,
    records_accepted    INTEGER,
    records_quarantined INTEGER,
    watermark_before    VARCHAR,
    watermark_after     VARCHAR
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    id                  BIGINT NOT NULL,
    run_id              VARCHAR NOT NULL,
    check_name          VARCHAR NOT NULL,             -- e.g. 'completeness', 'freshness', 'range'
    status              VARCHAR NOT NULL,             -- 'pass' | 'fail'
    detail              VARCHAR,
    checked_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS source_freshness (
    source              VARCHAR NOT NULL PRIMARY KEY,
    last_success_at     TIMESTAMPTZ,
    last_attempt_at     TIMESTAMPTZ,
    current_watermark   VARCHAR,
    status              VARCHAR                       -- 'fresh' | 'stale' | 'failing'
);
