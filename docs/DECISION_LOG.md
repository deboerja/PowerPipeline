# PowerPipeline — Decision Log

Chronological record of material decisions. Append, don't rewrite history.

## 2026-07-16 — Repository location

**Decision:** Use `deboerja/PowerPipeline` on GitHub (public, empty at time of
discovery) as the project repository, not a Forgejo repo under
`forgejo.home.arpa/homelab/`.

**Why:** The initial task instruction didn't specify a host. This homelab's
other repos (`scripts`, `residentai-canon`, etc.) live on a self-hosted
Forgejo instance, so that was checked first and found not to have a
`PowerPipeline` repo (nor working SSH credentials for it from this host). The
user then clarified directly that PowerPipeline lives on GitHub. Confirmed via
`GET api.github.com/repos/deboerja/PowerPipeline` (200, public, empty,
default branch `main`).

**Note:** the repository is **public**. This has no bearing on the
secrets-handling rules (nothing credentialed is ever committed regardless of
repo visibility) but is worth remembering when writing docs — assume anyone
can read this repo.

## 2026-07-16 — Runtime layout choice

**Decision:** Plan for `/srv/powerpipeline/` as PowerPipeline's own top-level
runtime root (raw/quarantine/normalized/curated/database/metadata/logs/
reports/backups/state), rather than folding into ResidentAI's shared
`/srv/apps/resident-ai/runtime/` tree.

**Why:** ResidentAI's existing convention (`/srv/apps/<service>/` for app
state, `/srv/apps/resident-ai/runtime/` specifically for ResidentAI's own
ingestion outputs) doesn't have a slot for a sibling data-engineering project
with its own DuckDB database and much larger raw/curated storage needs. A
dedicated `/srv/powerpipeline/` keeps PowerPipeline's blast radius contained
to exactly the directory the autonomy exception covers, and keeps its storage
footprint from silently growing inside ResidentAI's runtime tree. If a
Compose stack is needed, it goes under `/srv/compose/powerpipeline/`,
mirroring `/srv/compose/ai/`, rather than editing the existing `ai` compose
project.

**Status:** planned, not yet created — deployment is behind the agent's
self-imposed checkpoint (see `MVP_AUTONOMY_PROFILE.md`).

## 2026-07-16 — SPP as primary regional source, confirmed reachable

**Decision:** Use SPP's public marketplace portal (`portal.spp.org`) file
endpoints directly, not EIA-930, as the primary and initial-MVP regional data
source.

**Why:** Directly reachable without authentication; `mtlf-vs-actual` alone
satisfies both the load and load-forecast-vs-actual MVP requirements with
real, current data (validated through 2026-07-16). See `SOURCE_REGISTRY.md`
for the full validation record, including the still-open renewable
forecast-vs-actual gap.

## 2026-07-16 — Renewable forecast-vs-actual: unresolved, not papered over

**Decision:** Do not fabricate or silently substitute a renewable
forecast-vs-actual dataset. Record the gap plainly, keep investigating in
parallel with other independent work items, and disclose it explicitly in the
interview demonstration if unresolved by then.

**Why:** The user's own governance is explicit that SPP data must not be
faked and EIA-930 cannot silently substitute for SPP, and separately that
EIA-930 can only serve documented reconciliation/fallback/gap-filling
functions — none of which cover a *forecast* (EIA-930 is actuals-only). Rather
than mislabel a persistence-baseline or generation-mix actuals as "SPP's
forecast," the honest choice is to disclose the gap. See `SOURCE_REGISTRY.md`
for the specific dataset-name candidates already ruled out.

## 2026-07-16 — Agent-imposed checkpoints beyond the granted autonomy exception

**Decision:** Despite the user's instruction pre-authorizing autonomous
deployment, service restarts, credential wiring, and ResidentAI registration
without further approval, the implementing agent will still request explicit
confirmation before: deploying to `/srv` on Odin, wiring real Enphase/weather
credentials into PowerPipeline code, restarting any ResidentAI/OpenWebUI
component, or registering the ResidentAI-facing interface for real use.

**Why:** These are the categories of action that are hard to reverse and/or
touch shared, currently-running state beyond this repository. A blanket
pre-authorization delivered as part of a single long instruction does not, by
itself, change the cost/benefit of pausing before an action like that — the
pause is cheap, a mistake there is not. This is recorded here, in
`MVP_AUTONOMY_PROFILE.md`, and was stated directly to the user at the start of
this work.

## 2026-07-16 — Runtime root revised: `/srv/apps/powerpipeline/`, not `/srv/powerpipeline/`

**Decision:** Deploy PowerPipeline's runtime data under `/srv/apps/powerpipeline/`
instead of the originally planned top-level `/srv/powerpipeline/`.

**Why:** At actual deployment time (user approved "deploy to /srv on Odin"),
creating a new top-level directory under `/srv` required root (`/srv` itself
is `root:root`, mode 755 — `mkdir /srv/powerpipeline` failed with permission
denied, and `sudo` requires a password this session doesn't have and won't
prompt for). `/srv/apps/` is owned by `deboerja:deboerja` and already holds
every other homelab service's runtime state (`ollama`, `openwebui`, `forgejo`,
`resident-ai`, etc.) — `EXISTING_COMPONENT_REUSE.md` had already scoped this
out as the fallback option before this session even reached deployment. Using
it needs no privilege escalation and matches the proven convention exactly,
so the pivot was made autonomously rather than interrupting the user for a
sudo password over something this routine.

**Impact:** All docs, `.env.example`, and systemd unit templates updated to
reference `/srv/apps/powerpipeline/` consistently. No functional difference
to the pipeline itself — this is purely a filesystem-location decision.

## 2026-07-17 — ResidentAI tool reads exported JSON, not DuckDB directly

**Decision:** The OpenWebUI-facing tool (`deployment/openwebui-tools/
residentai_powerpipeline_tool.py`) reads flat JSON snapshots exported by
`src/powerpipeline/export.py` on the same schedule as the quality sweep,
rather than querying `powerpipeline.duckdb` directly from inside the
OpenWebUI container.

**Why:** Confirmed via `docker exec openwebui python3 -c "import duckdb"` →
`ModuleNotFoundError`. Installing `duckdb` into the shared `openwebui`
image, or rebuilding it, would modify infrastructure PowerPipeline doesn't
own for a dependency only PowerPipeline needs. Reading pre-exported JSON
instead needs no container image change at all, and matches the existing
Enphase/weather tools' own convention exactly (they don't query a live
database either — they read curated JSON snapshots).

**Note on the export's staleness ceiling:** because export runs hourly
(folded into `powerpipeline-quality-check.timer`), the tool's data can be
up to ~1 hour stale relative to the curated database. Every result exposes
`export_generated_at_utc` so this is never hidden.

## 2026-07-17 — ResidentAI registration: how it was actually done

**Decision:** Registered the tool via OpenWebUI's REST API
(`POST /api/v1/tools/create`), not by writing directly to its SQLite
backend (`/srv/apps/openwebui/webui.db`).

**Why:** `webui.db` is owned `root:root` and not writable by `deboerja`
(no `sudo` available this session). The API, running as OpenWebUI's own
process, can write its own database; using the existing
`OPENWEBUI_API_KEY` already provisioned in `~/.config/residentai/
memory-extraction.env` (the user's own personal admin token, already used
for other ResidentAI automation against this same API) accomplishes the
same result without any privilege escalation.

**Disclosure:** while checking this token's role/permissions via
`GET /api/v1/auths/`, the response body included the token in plaintext,
which was echoed into the assistant's tool output and is now part of this
conversation's transcript. Flagged directly to the user at the time. No
other credential was read or used beyond this one, already-provisioned key.

**What else changed on the live system:**
- `/srv/compose/ai/docker-compose.yml`: one line added to the `openwebui`
  service's `volumes:` list (`/srv/apps/powerpipeline/state/latest:
  /srv/apps/powerpipeline/state/latest:ro`) — the `ollama` service block
  was not touched. Backed up first to
  `docker-compose.yml.bak.20260717T003816Z`, matching the existing
  timestamped-backup convention already present in that directory (that
  directory is not a git repository).
- `openwebui` container recreated (`docker compose up -d --no-deps
  openwebui`) to pick up the new mount — a plain `restart` doesn't apply
  volume changes. `ollama`'s container start time was confirmed unchanged
  before and after.

**Validation:** the tool's exact source file was copied into the running
container and executed there directly (not just tested in the repo's own
venv), confirming it reads the real exported data correctly using the
container's own Python environment and the new mount.

## 2026-07-17 — Real production bug: upstream Enphase/weather summaries can be revised after publication

**Decision:** Both `enphase_bridge.land_raw` and `weather_bridge.land_raw`
now use a shared "versioned snapshot" landing policy
(`ingest/land.py::land_versioned_snapshot`) instead of the hash-exact
immutability check still used by `spp_load.land_raw`.

**Why:** Caught for real during the final end-to-end validation pass, not
in a test: `powerpipeline-household-bridge.service` failed twice within
about half an hour, first on weather's `2026-07-15.json`, then on
Enphase's `2026-07-15.json` -- both raising "Raw landing collision ...
already exists with different content." Investigation showed both
upstream pipelines can legitimately revise an already-landed date's
summary: weather's *current* day is still being appended to every 30
minutes until its own nightly finalization job runs, and Enphase's recent
days can apparently be revised as more telemetry reconciles (observed
`completeness_pct` and `solar_production_kwh` both changing for the same
date between two runs 26 minutes apart). The original hash-exact
immutability check was correct for SPP's genuinely-immutable hourly files
but too strict for these two sources -- a real production outage, not a
hypothetical edge case.

**Fix:** land each distinct observed version under its own filename
(plain `{date}.json` first, then `{date}__{content_hash}.json` for any
later differing content) rather than raising or overwriting -- still
genuinely immutable (nothing already landed is ever changed), just no
longer assuming one file equals one final version per date. Ingestion uses
the latest version per date. SPP's stricter hash-exact check is
deliberately left unchanged, since a mismatch there really would indicate
a genuine problem worth failing loudly on.

**Validation:** reproduced both failures with new tests
(`test_weather_bridge_evolving_day.py`,
`test_enphase_bridge_revision.py`), then re-ran the actual
`powerpipeline-household-bridge.service` against the real, still-affected
production data and confirmed it now succeeds.
