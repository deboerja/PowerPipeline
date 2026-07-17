import json
from pathlib import Path

from powerpipeline.ingest import enphase_bridge


def _write_summary(path: Path, date: str, kwh: float, completeness: float) -> None:
    path.write_text(json.dumps({
        "date": date,
        "system": "home-solar",
        "solar_production_kwh": kwh,
        "completeness_pct": completeness,
        "data_status": "complete" if completeness == 100.0 else "partial",
        "source": "enphase_monitoring_api",
        "ingested_at": "2026-07-16T01:00:00+00:00",
    }))


def test_upstream_revision_of_already_published_summary_does_not_crash(tmp_path):
    """Reproduces the real production failure caught on 2026-07-17: the
    upstream Enphase pipeline revised an already-published date's summary
    (late-arriving telemetry improving completeness) between two
    household-bridge runs a few minutes apart. This must land the revision,
    not raise.
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    day_file = source_dir / "2026-07-15.json"

    _write_summary(day_file, "2026-07-15", kwh=80.0, completeness=95.0)
    first = enphase_bridge.land_raw(day_file, "2026-07-15")

    _write_summary(day_file, "2026-07-15", kwh=83.51, completeness=100.0)  # upstream revised it
    second = enphase_bridge.land_raw(day_file, "2026-07-15")

    assert first != second
    assert first.exists() and second.exists()
    assert json.loads(second.read_text())["completeness_pct"] == 100.0


def test_ingest_directory_uses_latest_revision(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("POWERPIPELINE_RUNTIME_ROOT", str(runtime_root))

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    day_file = source_dir / "2026-07-15.json"

    _write_summary(day_file, "2026-07-15", kwh=80.0, completeness=95.0)
    enphase_bridge.ingest_directory(source_dir)

    _write_summary(day_file, "2026-07-15", kwh=83.51, completeness=100.0)
    normalized, rejected = enphase_bridge.ingest_directory(source_dir)

    assert len(normalized) == 1
    assert normalized.iloc[0]["completeness_pct"] == 100.0
    assert normalized.iloc[0]["solar_production_kwh"] == 83.51
