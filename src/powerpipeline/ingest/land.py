"""Shared raw-landing policy for sources whose upstream per-date snapshot
can be legitimately revised after first publication (Enphase daily
summaries, weather daily-actual) -- as opposed to SPP's hourly files, which
are genuinely immutable once published and use their own stricter
hash-exact check (ingest/spp_load.py::land_raw) precisely because a
mismatch there really would indicate a problem worth failing loudly on.

Discovered in production 2026-07-17: both the Enphase and weather upstream
pipelines can revise an already-published date's summary (e.g. late-arriving
telemetry improving a completeness percentage, or -- for weather
specifically -- the current day's file still being appended to until its
own nightly finalization). A second bridge run within that revision window
must not crash; it must land the new version alongside the old one and use
the newer one, since every landed file remains genuinely immutable (never
overwritten) even though a date may now have more than one captured version
over time. See docs/DECISION_LOG.md for the full incident record.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def land_versioned_snapshot(dest_dir: Path, stem: str, content: bytes) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    plain_dest = dest_dir / f"{stem}.json"
    if not plain_dest.exists():
        plain_dest.write_bytes(content)
        return plain_dest
    if plain_dest.read_bytes() == content:
        return plain_dest

    content_hash = hashlib.sha256(content).hexdigest()[:12]
    versioned_dest = dest_dir / f"{stem}__{content_hash}.json"
    if versioned_dest.exists():
        return versioned_dest
    versioned_dest.write_bytes(content)
    return versioned_dest
