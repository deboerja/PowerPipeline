import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime_root(tmp_path, monkeypatch):
    """Every test gets its own throwaway runtime root so tests never touch
    real /srv paths or share state with each other.
    """
    root = tmp_path / "powerpipeline_runtime"
    monkeypatch.setenv("POWERPIPELINE_RUNTIME_ROOT", str(root))
    yield root
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def spp_mtlf_fixture_bytes():
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "spp"
        / "mtlf"
        / "OP-MTLF-202607150000.csv"
    )
    return fixture_path.read_bytes()
