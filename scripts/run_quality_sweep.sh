#!/usr/bin/env bash
# Independent, periodic quality sweep across the full curated dataset --
# distinct from the per-run checks that fire inline with each ingest.
# Intended to run hourly via powerpipeline-quality-check.timer.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${POWERPIPELINE_PYTHON:-$REPO_ROOT/.venv/bin/python3}"

"$PYTHON" -c "
from powerpipeline import pipeline
result = pipeline.run_quality_sweep()
print(result)
"
