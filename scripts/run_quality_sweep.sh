#!/usr/bin/env bash
# Independent, periodic quality sweep across the full curated dataset --
# distinct from the per-run checks that fire inline with each ingest.
# Also refreshes the ResidentAI-facing JSON export (see
# src/powerpipeline/export.py and docs/EXISTING_COMPONENT_REUSE.md for why
# the OpenWebUI-facing tool reads static JSON instead of querying DuckDB
# directly) on the same schedule, so both stay in lockstep rather than
# drifting independently. Intended to run hourly via
# powerpipeline-quality-check.timer.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${POWERPIPELINE_PYTHON:-$REPO_ROOT/.venv/bin/python3}"

"$PYTHON" -c "
from powerpipeline import pipeline, export
result = pipeline.run_quality_sweep()
print(result)
export_result = export.export_all()
print(export_result)
"
