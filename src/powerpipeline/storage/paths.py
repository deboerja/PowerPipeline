"""Runtime storage layout.

PowerPipeline owns a single runtime root (defaults to /srv/powerpipeline in
deployment, overridable via POWERPIPELINE_RUNTIME_ROOT for local dev/tests)
subdivided into raw/normalized/quarantine/curated/metadata/logs/reports.
See docs/ARCHITECTURE.md for the full rationale.
"""

from __future__ import annotations

import os
from pathlib import Path


def runtime_root() -> Path:
    return Path(os.environ.get("POWERPIPELINE_RUNTIME_ROOT", "./.powerpipeline_dev_runtime"))


def raw_dir(*parts: str) -> Path:
    return runtime_root() / "raw" / Path(*parts)


def quarantine_dir(*parts: str) -> Path:
    return runtime_root() / "quarantine" / Path(*parts)


def normalized_dir(*parts: str) -> Path:
    return runtime_root() / "normalized" / Path(*parts)


def database_path() -> Path:
    return runtime_root() / "database" / "powerpipeline.duckdb"


def logs_dir() -> Path:
    return runtime_root() / "logs"


def reports_dir() -> Path:
    return runtime_root() / "reports"


def ensure_dirs() -> None:
    for d in (
        raw_dir(),
        quarantine_dir(),
        normalized_dir(),
        database_path().parent,
        logs_dir(),
        reports_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)
