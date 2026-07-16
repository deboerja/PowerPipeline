# PowerPipeline — MVP Autonomy Profile

## What this is

On 2026-07-16 the user granted a temporary, project-specific autonomy
exception for building the PowerPipeline MVP, intended to minimize
back-and-forth during routine implementation work. This document records that
exception precisely, including where it applies and where it doesn't, plus
the additional checkpoints the implementing agent chose to keep despite being
told it didn't need to ask.

The machine-readable version is `implementation/MVP_AUTONOMY_PROFILE.yaml`.

## Scope of the exception

Applies only to:
- The `PowerPipeline` GitHub repository (`deboerja/PowerPipeline`)
- The approved PowerPipeline runtime directory under `/srv` on Odin
- A dedicated PowerPipeline Docker Compose stack or isolated systemd services
- PowerPipeline-created databases, files, logs, schedules, and reports
- A bounded read-only PowerPipeline interface for ResidentAI
- Public Southwest Power Pool data
- Existing approved Enphase and weather data paths

Does **not** grant general authority over Odin, ResidentAI as a whole, Home
Assistant, energy equipment, unrelated repositories, or unrelated services.

## Relaxed controls (within PowerPipeline scope only)

Per-slice `residentai-canon` design/policy/status packages, human approval
after every branch/commit/test, formal approval before routine architectural
decisions, full toolrunner audit integration during early development, formal
change tickets, maintenance windows, multi-person review, enterprise RBAC, HA,
DB replication, geographic DR, a formal data-catalog product, a full
observability platform, multi-source reconciliation as a release gate, a model
registry/governance workflow, full retention-policy implementation, and
separate approval for: creating the isolated runtime directory, deploying or
restarting PowerPipeline-owned services, creating schedules, registering the
ResidentAI read-only interface, and merging tested changes into the default
branch.

## Non-negotiable boundaries (unaffected by the exception)

No FranklinWH access attempts of any kind. No access to private/authenticated
SPP systems. No credential extraction outside project scope. No equipment
control (batteries, inverters, HVAC, water heating), no Home Assistant
service calls that change device state, no dispatch/bidding logic. ResidentAI
never receives arbitrary SQL, write access, shell execution, unrestricted
filesystem access, secret access, or general Home Assistant write authority.
No deleting/overwriting/restarting anything outside PowerPipeline's own scope,
no Firewalla/DNS/reverse-proxy/auth-infra changes, no internet-exposed ports.
No committed secrets. No inventing missing data, hiding failed validations,
presenting stale data as current, letting rejected records into curated
tables, silently substituting EIA-930 for SPP, or claiming completion without
meeting acceptance criteria.

## Checkpoints the implementing agent is keeping anyway

The user's instruction pre-authorizes autonomous merging, deployment, service
restarts, and ResidentAI registration without further confirmation. The agent
communicated at the start of this work that it would still pause for explicit
go-ahead before the following, specifically because they are hard to reverse
and/or touch shared/running state beyond this repo:

1. Deploying any container/systemd service to Odin under `/srv`
2. Wiring real Enphase/weather credentials into PowerPipeline code paths
3. Restarting any ResidentAI/OpenWebUI component
4. Registering the ResidentAI-facing read-only interface for real use

This is a self-imposed control, not a limitation the user asked for — it
exists because a quick check-in before an irreversible, shared-system action
is cheap, and an unwanted one is not. Routine repo-local work (branches,
commits, pushes, local tests, docs, fixtures, local DuckDB files under the
repo's own working tree) proceeds without asking, per the exception above.

## Evidence standard for this MVP

Git history, automated tests, pipeline-run records, data-quality records,
structured logs, work-queue status, execution-history records, the source
registry, architecture/lineage docs, deployment validation, and interview
demonstration results. Formal ResidentAI canon integration (the
`residentai-canon` package format used elsewhere in this homelab) can follow
after the MVP works — it is not a precondition for the MVP itself.
