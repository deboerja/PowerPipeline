"""Ingestion for SPP's mtlf-vs-actual dataset (hourly load + load
forecast-vs-actual, both SPP-East and SWPW-West balancing areas).

Source: https://portal.spp.org/file-browser-api/download/mtlf-vs-actual
No authentication required. See docs/SOURCE_REGISTRY.md for validation
evidence.

Design note on timestamps: the raw file gives both a local-time `Interval`
column and a `GMTIntervalEnd` column. Rather than parse the local column
(which would require correctly handling SPP's Central-time DST transitions),
we treat `GMTIntervalEnd` as authoritative and derive the interval start in
UTC by subtracting one hour — avoiding fragile local-time parsing entirely
when an unambiguous UTC field is already provided by the source.
"""

from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from powerpipeline.contracts.spp_mtlf import validate_raw
from powerpipeline.storage import paths

SOURCE_BASE = "https://portal.spp.org"
DATASET = "mtlf-vs-actual"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 2


@dataclass
class IngestResult:
    run_id: str
    raw_path: Path
    records_in: int
    records_accepted: int
    records_rejected: int
    normalized_path: Path | None
    quarantine_path: Path | None


def fetch_raw_csv(
    year: int,
    month: int,
    day: int,
    filename: str,
    client: httpx.Client | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> bytes:
    """Download one raw MTLF file from SPP's public portal. Forces IPv4,
    matching the existing weather-pipeline convention on this host (this
    network's IPv6 route is blackholed — see docs/EXISTING_COMPONENT_REUSE.md).

    Retries transient failures (connection errors, 5xx, timeouts) up to
    max_retries times with linear backoff before giving up -- see
    docs/FAILURE_SCENARIOS.md #4.
    """
    url = f"{SOURCE_BASE}/file-browser-api/download/{DATASET}"
    path_param = f"/{year:04d}/{month:02d}/{day:02d}/{filename}"
    own_client = client is None
    if own_client:
        client = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"), timeout=30.0)
    try:
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.get(url, params={"path": path_param})
                resp.raise_for_status()
                return resp.content
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise  # 4xx is not transient -- don't waste retries on it
                if attempt < max_retries:
                    time.sleep(retry_backoff_seconds * (attempt + 1))
        raise last_exc
    finally:
        if own_client:
            client.close()


def land_raw(content: bytes, year: int, month: int, day: int, filename: str) -> Path:
    """Write raw content to the immutable raw-landing layer. Never
    overwrites an existing file with different content — a byte-identical
    re-pull is a no-op, but a content mismatch is a hard error (raw landing
    must never silently replace history).
    """
    dest_dir = paths.raw_dir("spp", "mtlf", f"{year:04d}", f"{month:02d}", f"{day:02d}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if dest.exists():
        existing_hash = hashlib.sha256(dest.read_bytes()).hexdigest()
        new_hash = hashlib.sha256(content).hexdigest()
        if existing_hash != new_hash:
            raise ValueError(
                f"Raw landing collision: {dest} already exists with different content "
                f"(existing={existing_hash[:12]} new={new_hash[:12]}). Raw landing is immutable."
            )
        return dest
    dest.write_bytes(content)
    return dest


def parse_and_normalize(raw_csv: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw_csv))
    accepted, rejected = validate_raw(df)
    normalized = accepted.copy() if accepted is not None and len(accepted) else accepted
    if normalized is not None and len(normalized):
        gmt_end = pd.to_datetime(normalized["GMTIntervalEnd"], format="%m/%d/%Y %H:%M:%S", utc=True)
        normalized["interval_end_utc"] = gmt_end
        normalized["interval_start_utc"] = gmt_end - pd.Timedelta(hours=1)
        normalized["load_forecast_mw"] = normalized["MTLF"]
        normalized["load_actual_mw"] = normalized["Averaged Actual"]
        normalized["baa"] = normalized["BAA"]
        normalized = normalized[
            ["interval_start_utc", "interval_end_utc", "baa", "load_forecast_mw", "load_actual_mw"]
        ]
        # Dedup within this file: same (baa, interval_start_utc) should be one row.
        normalized = normalized.drop_duplicates(subset=["baa", "interval_start_utc"], keep="last")
    return normalized, rejected


def write_normalized(normalized: pd.DataFrame, run_id: str) -> Path | None:
    if normalized is None or len(normalized) == 0:
        return None
    dest_dir = paths.normalized_dir("spp", "load_forecast_actual")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{run_id}.parquet"
    normalized.to_parquet(dest, index=False)
    return dest


def write_quarantine(rejected: pd.DataFrame | None, run_id: str) -> Path | None:
    if rejected is None or len(rejected) == 0:
        return None
    dest_dir = paths.quarantine_dir("spp", "mtlf")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{run_id}.parquet"
    rejected.to_parquet(dest, index=False)
    return dest


def ingest_file(
    year: int, month: int, day: int, filename: str, raw_csv: bytes | None = None
) -> IngestResult:
    """Ingest a single raw MTLF file end to end: land raw, validate,
    normalize, quarantine failures. If raw_csv is not provided, fetches it
    live from SPP.
    """
    run_id = f"spp-mtlf-{year:04d}{month:02d}{day:02d}-{filename}-{datetime.now(timezone.utc).strftime('%H%M%S%f')}"
    if raw_csv is None:
        raw_csv = fetch_raw_csv(year, month, day, filename)
    raw_path = land_raw(raw_csv, year, month, day, filename)
    normalized, rejected = parse_and_normalize(raw_path.read_bytes())
    normalized_path = write_normalized(normalized, run_id)
    quarantine_path = write_quarantine(rejected, run_id)
    records_in = (len(normalized) if normalized is not None else 0) + (
        len(rejected) if rejected is not None else 0
    )
    return IngestResult(
        run_id=run_id,
        raw_path=raw_path,
        records_in=records_in,
        records_accepted=len(normalized) if normalized is not None else 0,
        records_rejected=len(rejected) if rejected is not None else 0,
        normalized_path=normalized_path,
        quarantine_path=quarantine_path,
    )
