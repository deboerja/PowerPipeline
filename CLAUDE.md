# PowerPipeline — Claude Code Instructions

## Read before modifying anything in this project

1. `docs/NORTH_STAR.md`
2. `docs/MVP_CHARTER.md`
3. `docs/MVP_AUTONOMY_PROFILE.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SECURITY_AND_AUTHORITY.md`
6. `implementation/MVP_AUTONOMY_PROFILE.yaml`
7. `implementation/MVP_ACCEPTANCE_CRITERIA.yaml`
8. `implementation/WORK_QUEUE.yaml`
9. `implementation/CURRENT_STATUS.yaml`
10. `implementation/BLOCKERS.yaml`

Never rely on session/conversation memory as the only record of project
state — everything that matters is in the files above, kept current in Git.

## Every session

1. Recover project state from Git (`git log`, `git status`,
   `implementation/CURRENT_STATUS.yaml`, `implementation/WORK_QUEUE.yaml`).
2. Inspect the current branch and working tree before doing anything.
3. Identify the next incomplete, unblocked item in
   `implementation/WORK_QUEUE.yaml` (check `implementation/BLOCKERS.yaml`
   first for anything that changes the picture).
4. Continue autonomous implementation of that item.
5. Use existing homelab conventions — see `docs/EXISTING_COMPONENT_REUSE.md`
   before building something that duplicates an existing capability.
6. Prefer the smallest reliable design (DuckDB + Parquet + systemd timers;
   see `docs/ARCHITECTURE.md` for why, and don't reach for
   Kafka/Spark/Airflow/dbt/Kubernetes/Postgres without a discovered technical
   requirement).
7. Run required tests before considering an item done.
8. Correct ordinary failures (test failures, schema issues, timestamp bugs,
   merge conflicts, ordinary service errors) without asking the user — up to
   five materially different attempts, then record the blocker in
   `implementation/BLOCKERS.yaml` and move to independent work.
9. Update `implementation/CURRENT_STATUS.yaml`,
   `implementation/EXECUTION_HISTORY.yaml`, and the relevant
   `implementation/WORK_QUEUE.yaml` item status after each unit of work.
10. Commit and push completed work.
11. Merge tested PowerPipeline changes into `main` when validation passes
    (working tree clean, tests pass, secret scan clean).
12. Deploy or update isolated PowerPipeline services **except** where an
    agent-imposed checkpoint applies (see next section) — get explicit user
    confirmation there first, every time, even though the originating
    instruction pre-authorizes it.
13. Stop only for a true blocker (see `docs/MVP_AUTONOMY_PROFILE.md` and the
    original task instruction §18) — an ordinary technical failure is not one.
14. Never rely on Claude session memory as the only project record.

## Checkpoints that require explicit user confirmation regardless of prior autonomy grants

- Deploying any container/systemd service to Odin under `/srv`
- Wiring real Enphase/weather credentials into PowerPipeline code paths
- Restarting any ResidentAI/OpenWebUI component
- Registering the ResidentAI-facing read-only interface for real use

These are recorded in `docs/MVP_AUTONOMY_PROFILE.md` as checkpoints the
implementing agent chose to keep. A future session should keep them too
unless the user explicitly lifts them.

## Boundaries that never relax

No FranklinWH access attempts. No private/authenticated SPP access. No
equipment control of any kind. No arbitrary SQL or write access for
ResidentAI. No committed secrets. No fabricated data, hidden validation
failures, or silent EIA-930-for-SPP substitution. Full list:
`docs/SECURITY_AND_AUTHORITY.md` and `docs/MVP_AUTONOMY_PROFILE.md`.
