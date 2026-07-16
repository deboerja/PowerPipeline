-- PowerPipeline curated views. Applied after schema.sql.

-- SPP load forecast accuracy: only rows where an actual has been published.
CREATE OR REPLACE VIEW v_spp_load_forecast_accuracy AS
SELECT
    baa,
    date_trunc('day', interval_start_utc) AS day,
    count(*) AS interval_count,
    avg(load_actual_mw - load_forecast_mw) AS mean_bias_mw,
    avg(abs(load_actual_mw - load_forecast_mw)) AS mean_abs_error_mw,
    avg(abs(load_actual_mw - load_forecast_mw) / nullif(load_actual_mw, 0)) * 100
        AS mean_abs_pct_error
FROM fact_spp_load_forecast_actual
WHERE load_actual_mw IS NOT NULL
GROUP BY baa, date_trunc('day', interval_start_utc);

CREATE OR REPLACE VIEW v_household_solar_forecast_accuracy AS
SELECT
    a.date,
    a.solar_production_kwh AS actual_kwh,
    f.forecast_kwh,
    (a.solar_production_kwh - f.forecast_kwh) AS bias_kwh,
    abs(a.solar_production_kwh - f.forecast_kwh) AS abs_error_kwh
FROM fact_household_solar a
JOIN fact_household_solar_forecast f
    ON f.forecast_for_date = a.date
WHERE f.captured_at_utc = (
    SELECT max(f2.captured_at_utc)
    FROM fact_household_solar_forecast f2
    WHERE f2.forecast_for_date = a.date
);
