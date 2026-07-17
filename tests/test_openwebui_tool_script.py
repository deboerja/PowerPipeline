import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from powerpipeline import export, pipeline

TOOL_SCRIPT = (
    Path(__file__).resolve().parent.parent / "deployment" / "openwebui-tools" / "residentai_powerpipeline_tool.py"
)


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("residentai_powerpipeline_tool", TOOL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exported_state(tmp_path, spp_mtlf_fixture_bytes):
    fixtures = Path(__file__).resolve().parent.parent / "fixtures"
    pipeline.run_spp_load_ingest(2026, 7, 15, "OP-MTLF-202607150000.csv", raw_csv=spp_mtlf_fixture_bytes)
    pipeline.run_enphase_bridge(fixtures / "enphase" / "daily-summary")
    pipeline.run_household_solar_forecast_bridge(
        fixtures / "solar_forecast" / "solar_production_projection_2026-01-01.json"
    )
    out_dir = tmp_path / "state" / "latest"
    export.export_all(output_dir=out_dir, as_of=date(2026, 1, 15))
    return out_dir


def test_tool_script_loads_standalone_with_no_powerpipeline_import(exported_state):
    """The tool script must be import-independent of the powerpipeline
    package itself (it runs inside the OpenWebUI container, which does not
    have powerpipeline or duckdb installed) -- it only reads exported JSON.
    """
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_pipeline_health())
    assert result["ok"] is True
    assert result["record_count"] > 0


def test_tool_script_household_solar_history(exported_state):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_household_solar_history("2026-01-01", "2026-01-31"))
    assert result["ok"] is True
    assert result["record_count"] == 3


def test_tool_script_spp_load_conditions_filters_by_baa(exported_state):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_spp_load_conditions("2026-07-14", "2026-07-15", baa="SPP"))
    assert result["ok"] is True
    assert all(r["baa"] == "SPP" for r in result["records"])

    result_swpw = json.loads(tools.read_spp_load_conditions("2026-07-14", "2026-07-15", baa="SWPW"))
    assert all(r["baa"] == "SWPW" for r in result_swpw["records"])


def test_tool_script_rejects_invalid_baa(exported_state):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_spp_load_conditions("2026-07-14", "2026-07-15", baa="NOT_REAL"))
    assert result["ok"] is False
    assert result["reason"] == "invalid_baa"


def test_tool_script_rejects_bad_date_range(exported_state):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_household_solar_history("2026-07-15", "2026-07-01"))
    assert result["ok"] is False
    assert result["reason"] == "invalid_date_range"


def test_tool_script_renewable_honestly_unavailable(exported_state):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(exported_state)
    result = json.loads(tools.read_spp_renewable_conditions("2026-07-01", "2026-07-15"))
    assert result["status"] == "not_available"
    assert result["record_count"] == 0


def test_tool_script_handles_missing_export_gracefully(tmp_path):
    module = _load_tool_module()
    tools = module.Tools()
    tools.valves.state_dir = str(tmp_path / "nonexistent")
    result = json.loads(tools.read_household_solar_history("2026-01-01", "2026-01-31"))
    assert result["ok"] is False
    assert result["reason"] == "export_not_available"


def test_tool_script_has_no_sql_or_write_capability(exported_state):
    """Structural check mirroring test_residentai_tool.py: no method that
    accepts or executes a SQL string, and no import of a database driver at
    all (the whole point of this script is to need none).
    """
    module = _load_tool_module()
    tools = module.Tools()
    forbidden = {"query", "execute", "execute_sql", "run_sql", "sql"}
    actual = {name for name in dir(tools) if not name.startswith("_")}
    assert forbidden.isdisjoint(actual)
    source = TOOL_SCRIPT.read_text()
    assert "import duckdb" not in source
    assert "import sqlite3" not in source
