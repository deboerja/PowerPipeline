# PowerPipeline — North Star

This document records the long-term destination for PowerPipeline. It is not a
description of what exists today (see `MVP_CHARTER.md` for that) and it is not
a task list (see `implementation/FUTURE_BACKLOG.yaml`). It exists so that any
future session — human or Claude — can recover *why* the project exists
without depending on conversation memory.

## Long-term objective

A governed ResidentAI energy-intelligence platform that combines:

- Enphase household solar production (actual)
- Local weather observations (actual)
- Local weather forecasts
- Historical household energy data
- Household solar-generation forecasting
- Forecast-versus-actual analysis, at both household and regional scale
- Southwest Power Pool (SPP) regional load
- SPP renewable generation
- SPP regional load and renewable forecasts
- FranklinWH battery telemetry, once authorized access exists (not before)
- Operational monitoring of the pipeline itself
- Historical analysis across all of the above
- Explainable recommendations derived from the data
- Read-only ResidentAI access to all of it
- A strict, permanent separation between **observation**, **recommendation**,
  and **equipment control** — this platform only ever does the first two.

## Why this exists

Two reasons, both real, neither one fake:

1. It is a demonstration vehicle for a Data Engineer interview with East River
   Electric Power Cooperative (see `MVP_CHARTER.md` §Business Context). It has
   to be honest, working, and defensible under questioning — not a prop.
2. It is a genuine step toward giving ResidentAI the ability to reason about
   household energy behavior in the context of the regional grid it sits
   inside of — something no existing capability in this homelab currently
   does. Enphase and weather integrations already exist and are reused, not
   rebuilt (see `EXISTING_COMPONENT_REUSE.md`); SPP regional data is new
   ground.

## What the MVP is, relative to this

The MVP (`MVP_CHARTER.md`) is the first working slice of this platform: one
regional source (SPP), the two household sources that already exist (Enphase,
weather), forecast-vs-actual analysis for both, and a bounded read-only
ResidentAI surface. It is not the platform. Items that serve this North Star
but are out of MVP scope live in `implementation/FUTURE_BACKLOG.yaml` and must
not be implemented just because they trace back to this document — see
`FUTURE_ARCHITECTURE.md` for the reasoning boundary between "MVP" and "later."

## Permanent invariants

These hold regardless of how far the platform grows:

- ResidentAI's access to this data is read-only, forever, via named
  operations — never arbitrary SQL, never write access.
- Nothing in this system controls equipment. Not batteries, not inverters,
  not HVAC, not water heating. If a future capability needs to *recommend* an
  action, it recommends it to a human; it does not execute it.
- FranklinWH access is only ever pursued through an authorized, documented
  path. No reverse engineering, no unauthorized access attempts.
- Regional data is sourced from SPP's public data first. EIA-930 is a
  reconciliation/fallback source, never a silent substitute (see
  `SOURCE_REGISTRY.md`, `DECISION_LOG.md`).
