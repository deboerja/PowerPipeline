#!/usr/bin/env bash
# Reads the existing Enphase/weather pipelines' curated output (read-only, no
# credentials) and ingests it into PowerPipeline's curated layer. Intended to
# run every 30 minutes via powerpipeline-household-bridge.timer.
#
# Path configuration follows the homelab's existing convention: an env file
# under ~/.config/residentai/, sourced here, never committed. See
# .env.example for the expected variables and docs/EXISTING_COMPONENT_REUSE.md
# for why these paths are read-only and credential-free.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${POWERPIPELINE_PYTHON:-$REPO_ROOT/.venv/bin/python3}"
ENV_FILE="${POWERPIPELINE_ENV_FILE:-$HOME/.config/residentai/powerpipeline.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

ENPHASE_DIR="${POWERPIPELINE_ENPHASE_SNAPSHOTS_DIR:?POWERPIPELINE_ENPHASE_SNAPSHOTS_DIR not set}"
WEATHER_DIR="${POWERPIPELINE_WEATHER_SNAPSHOTS_DIR:?POWERPIPELINE_WEATHER_SNAPSHOTS_DIR not set}"
WEATHER_STATE_DIR="${POWERPIPELINE_WEATHER_STATE_DIR:?POWERPIPELINE_WEATHER_STATE_DIR not set}"

"$PYTHON" - "$ENPHASE_DIR/daily-summary" "$WEATHER_DIR/daily-actual" "$WEATHER_STATE_DIR/solar_production_projection.json" <<'EOF'
import sys
from pathlib import Path

from powerpipeline import pipeline

enphase_dir, weather_dir, forecast_path = (Path(p) for p in sys.argv[1:4])

failures = []
for label, fn, arg in (
    ("enphase", pipeline.run_enphase_bridge, enphase_dir),
    ("weather", pipeline.run_weather_bridge, weather_dir),
    ("household_solar_forecast", pipeline.run_household_solar_forecast_bridge, forecast_path),
):
    if not arg.exists():
        print(f"SKIP {label}: {arg} does not exist")
        continue
    result = fn(arg)
    print(label, result)
    if result["status"] != "success":
        failures.append(label)

if failures:
    sys.exit(1)
EOF
