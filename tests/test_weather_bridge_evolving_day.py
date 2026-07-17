import json
from pathlib import Path

from powerpipeline.ingest import weather_bridge


def _write_weather_file(path: Path, date: str, num_readings: int) -> None:
    readings = [
        {"timestamp_local": f"{date}T{h:02d}:55:00-05:00", "sky_cover_pct": 10, "temperature_c": 20.0 + h}
        for h in range(num_readings)
    ]
    path.write_text(json.dumps({"date": date, "station": "KMDS", "readings": readings}))


def test_current_day_file_growing_between_runs_does_not_crash(tmp_path):
    """Reproduces the real production failure caught on 2026-07-17: the
    upstream weather pipeline appends more readings to *today's*
    daily-actual file every 30 minutes until its own nightly job finalizes
    it after midnight, so a second household-bridge run within the same
    day sees different content for the same date -- this must not raise,
    unlike a genuine immutability violation on an already-finalized date.
    """
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    day_file = source_dir / "2026-07-15.json"

    _write_weather_file(day_file, "2026-07-15", num_readings=4)
    first_landed = weather_bridge.land_raw(day_file, "2026-07-15")
    assert first_landed.exists()

    _write_weather_file(day_file, "2026-07-15", num_readings=8)  # upstream added more readings
    second_landed = weather_bridge.land_raw(day_file, "2026-07-15")
    assert second_landed.exists()
    assert second_landed != first_landed  # distinct capture, not overwritten, not crashed

    # Both historical captures survive on disk -- raw landing is still
    # genuinely immutable, just no longer one-file-per-date.
    assert first_landed.read_text() != second_landed.read_text()


def test_ingest_directory_uses_latest_capture_for_growing_day(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("POWERPIPELINE_RUNTIME_ROOT", str(runtime_root))

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    day_file = source_dir / "2026-07-15.json"

    _write_weather_file(day_file, "2026-07-15", num_readings=4)
    weather_bridge.ingest_directory(source_dir)

    _write_weather_file(day_file, "2026-07-15", num_readings=8)
    daily, rejected = weather_bridge.ingest_directory(source_dir)

    assert daily is not None
    assert len(daily) == 1  # one station-day row, from the latest (8-reading) capture, not both combined
