"""DuckDB connection + schema management for PowerPipeline's curated layer."""

from __future__ import annotations

from pathlib import Path

import duckdb

from powerpipeline.storage import paths

_SQL_DIR = Path(__file__).resolve().parent.parent.parent / "sql"


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    paths.database_path().parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(paths.database_path()), read_only=read_only)


def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute((_SQL_DIR / "schema.sql").read_text())


def apply_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute((_SQL_DIR / "views.sql").read_text())


def init_db() -> duckdb.DuckDBPyConnection:
    con = connect(read_only=False)
    apply_schema(con)
    apply_views(con)
    return con
