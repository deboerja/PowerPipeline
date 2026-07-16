# PowerPipeline — Future Architecture

This describes what the platform could grow into, per `docs/NORTH_STAR.md`.
None of it is authorized for implementation now — see
`implementation/FUTURE_BACKLOG.yaml` for the actual tracked list, and don't
build from this document directly.

## When the current stack would actually need to change

- **DuckDB → Postgres/a server-based engine:** only if PowerPipeline needs
  concurrent multi-writer access (it doesn't yet — one ingestion process at a
  time) or needs to serve queries to something other than a single local
  ResidentAI tool process.
- **Batch → streaming (Kafka or similar):** only if a source starts requiring
  sub-minute reaction latency, which none of the current sources do (SPP
  publishes hourly files; Enphase/weather are already batch).
- **Manual scheduling → Airflow/dbt:** only if the DAG grows enough
  cross-source dependencies that systemd's `Wants=`/`After=` ordering becomes
  genuinely hard to reason about — not merely "more sources exist."
- **Single-host → HA/replicated:** only if this stops being a single-operator
  homelab tool, which isn't the plan.

## FranklinWH adapter (not implemented)

When/if authorized access exists, the integration point is the same shape as
Enphase's: a dedicated ingestion module under
`homelab_scripts/runtime/franklinwh-energy/` (or wherever the owning
capability lives — likely not PowerPipeline itself, mirroring how
PowerPipeline doesn't own Enphase auth either), producing a curated JSON
snapshot (battery state of charge, charge/discharge rate, reserve setting) at
a fixed path, which PowerPipeline would then read the same way it reads
Enphase's `daily-summary` files today — raw-copy, validate, quarantine,
curate. No reverse engineering, no unauthorized access, ever — this adapter
does not get built until legitimate API/data access is confirmed available.

## Explainable recommendations (not implemented)

A future layer that reasons over curated data (e.g. "your solar forecast for
tomorrow is 40% below the seasonal average and SPP's regional forecast shows
high load — consider X") is explicitly a **recommendation-to-a-human** layer,
never an equipment-control layer. It would live downstream of the curated
tables this MVP builds, read-only same as ResidentAI's other access.

## Multi-source reconciliation

Comparing SPP's own numbers against EIA-930 SWPP as an independent check is
future work, not an MVP release gate (per the relaxed controls in
`MVP_AUTONOMY_PROFILE.md`). If pursued, it's a validation view, not a data
source substitution.

## Formal data catalog / model registry / full observability stack

Deferred as documented enterprise capabilities inappropriate for
single-operator homelab scale right now — see `MVP_AUTONOMY_PROFILE.md`
relaxed-controls list for the specific items. Revisit only if PowerPipeline
grows beyond a single operator/consumer.
