from unittest.mock import MagicMock

import httpx
import pytest

from powerpipeline import db, pipeline
from powerpipeline.ingest import spp_load


def _mock_response(content: bytes = b"", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_fetch_retries_transient_failure_then_succeeds(spp_mtlf_fixture_bytes):
    fake_client = MagicMock()
    fake_client.get.side_effect = [
        httpx.ConnectError("simulated transient network failure"),
        _mock_response(content=spp_mtlf_fixture_bytes, status_code=200),
    ]
    result = spp_load.fetch_raw_csv(
        2026, 7, 15, "OP-MTLF-202607150000.csv", client=fake_client, retry_backoff_seconds=0
    )
    assert result == spp_mtlf_fixture_bytes
    assert fake_client.get.call_count == 2


def test_fetch_gives_up_after_max_retries():
    fake_client = MagicMock()
    fake_client.get.side_effect = httpx.ConnectError("persistent simulated outage")
    with pytest.raises(httpx.ConnectError):
        spp_load.fetch_raw_csv(
            2026, 7, 15, "OP-MTLF-202607150000.csv", client=fake_client,
            max_retries=2, retry_backoff_seconds=0,
        )
    assert fake_client.get.call_count == 3  # initial attempt + 2 retries


def test_fetch_does_not_retry_permanent_4xx_errors():
    fake_client = MagicMock()
    fake_client.get.return_value = _mock_response(status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        spp_load.fetch_raw_csv(
            2026, 7, 15, "OP-MTLF-202607150000.csv", client=fake_client,
            max_retries=3, retry_backoff_seconds=0,
        )
    assert fake_client.get.call_count == 1  # no point retrying a 404


def test_bounded_backfill_continues_past_one_failed_day_and_preserves_curated_data(
    spp_mtlf_fixture_bytes, monkeypatch
):
    """Simulates a source outage on one day within a multi-day backfill.
    The batch must record the failure but still successfully ingest the
    other days, and previously-curated data must survive untouched -- see
    docs/FAILURE_SCENARIOS.md #4 and #5.
    """
    call_log = []

    def fake_fetch(year, month, day, filename, client=None, **kwargs):
        call_log.append((year, month, day))
        if (year, month, day) == (2026, 7, 16):
            raise httpx.ConnectError("simulated outage for this one day")
        return spp_mtlf_fixture_bytes

    monkeypatch.setattr(spp_load, "fetch_raw_csv", fake_fetch)

    # First, land some data that must survive the batch below untouched.
    pipeline.run_spp_load_ingest(2026, 7, 14, "OP-MTLF-202607140000.csv", raw_csv=spp_mtlf_fixture_bytes)
    con = db.connect(read_only=True)
    try:
        rows_before = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
    finally:
        con.close()
    assert rows_before > 0

    result = pipeline.bounded_backfill(
        [
            (2026, 7, 15, "OP-MTLF-202607150000.csv"),
            (2026, 7, 16, "OP-MTLF-202607160000.csv"),  # this one "fails"
            (2026, 7, 17, "OP-MTLF-202607170000.csv"),
        ]
    )

    assert result["attempted"] == 3
    assert result["failed"] == 1
    statuses = {r["date"]: r["status"] for r in result["results"]}
    assert statuses["2026-07-15"] == "success"
    assert statuses["2026-07-16"] == "failed"
    assert statuses["2026-07-17"] == "success"

    con = db.connect(read_only=True)
    try:
        rows_after = con.execute("SELECT count(*) FROM fact_spp_load_forecast_actual").fetchone()[0]
        failed_run = con.execute(
            "SELECT status FROM pipeline_runs WHERE watermark_after = '2026-07-16'"
        ).fetchall()
    finally:
        con.close()
    # Pre-existing curated data was never touched by the failed day.
    assert rows_after >= rows_before
    # The failure itself was recorded, not silently swallowed.
    assert len(failed_run) == 1
    assert failed_run[0][0] == "failed"
