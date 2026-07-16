#!/usr/bin/env bash
# Fetches and ingests today's (UTC) SPP mtlf-vs-actual file. Intended to run
# hourly via powerpipeline-spp-ingest.timer. See docs/OPERATIONS.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${POWERPIPELINE_PYTHON:-$REPO_ROOT/.venv/bin/python3}"

DATE_UTC="$(date -u +%Y-%m-%d)"
FILENAME="OP-MTLF-$(date -u +%Y%m%d%H)00.csv"

"$PYTHON" - "$DATE_UTC" "$FILENAME" <<'EOF'
import sys
from datetime import date

from powerpipeline import pipeline

date_str, filename = sys.argv[1], sys.argv[2]
d = date.fromisoformat(date_str)
result = pipeline.run_spp_load_ingest(d.year, d.month, d.day, filename)
print(result)
if result["status"] != "success":
    sys.exit(1)
EOF
