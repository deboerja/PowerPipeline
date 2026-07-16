# PowerPipeline

A regional + household energy data pipeline: public Southwest Power Pool
(SPP) grid data alongside household solar production and weather, with
forecast-vs-actual analysis, data quality monitoring, and a bounded read-only
interface for a homelab automation system called ResidentAI.

Built as the first working slice of a longer-term energy-intelligence
platform (`docs/NORTH_STAR.md`), and as a working demonstration for a Data
Engineer interview with East River Electric Power Cooperative
(`docs/MVP_CHARTER.md`).

## What this is (and isn't)

- **Is:** a real, running, tested data pipeline — raw landing, schema
  validation and quarantine, normalized/curated layers in DuckDB + Parquet,
  idempotent incremental loading, forecast-accuracy analytics, and a
  read-only ResidentAI integration.
- **Isn't:** equipment control of any kind. This system observes, analyzes,
  and reports — it never touches batteries, inverters, HVAC, or any other
  device. See `docs/SECURITY_AND_AUTHORITY.md`.

## Start here

| Doc | Purpose |
|---|---|
| `docs/NORTH_STAR.md` | Long-term vision |
| `docs/MVP_CHARTER.md` | What the MVP actually delivers |
| `docs/ARCHITECTURE.md` | Storage layers, data flow, why DuckDB |
| `docs/SOURCE_REGISTRY.md` | Every external data source, validated live |
| `docs/EXISTING_COMPONENT_REUSE.md` | What's reused from existing homelab capabilities vs. new |
| `docs/SECURITY_AND_AUTHORITY.md` | Exactly what ResidentAI can and can't do |
| `docs/INTERVIEW_DEMO.md` | How to run the offline demonstration |
| `implementation/CURRENT_STATUS.yaml` | What's actually done right now |
| `implementation/WORK_QUEUE.yaml` | Full ordered work breakdown |

## Development

```bash
pip install -e ".[dev]"
pytest
python -m powerpipeline.demo run-all
```

Requires no credentials for the SPP source (public, unauthenticated). See
`.env.example` for the household-source bridge configuration.

## Status

Control-plane and documentation phase complete; pipeline implementation in
progress. See `implementation/CURRENT_STATUS.yaml` for the authoritative,
current state — this README is not re-checked as often as that file.
