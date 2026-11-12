"""What the interface expects from the server, checked against the server's own values.

Reads the interface's sources (frontend/src)."""

import re
from pathlib import Path
from typing import get_args

import pytest

from owstudio.core.extract.catalogue import Status

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
pytestmark = pytest.mark.skipif(not SRC.is_dir(), reason="interface sources not present")


def test_the_interface_sorts_the_diagnostics_by_a_status_the_server_gives() -> None:
    """Regression: the variable lists left out the status "unavailable", which the server never
    gives ("impossible"): a quantity the files cannot give was offered, then refused."""
    known = set(get_args(Status))
    compared: set[str] = set()
    for name in ("pages/project/ExplorerPage.tsx", "pages/project/export/WrfoutExport.tsx"):
        text = (SRC / name).read_text(encoding="utf-8")
        found = re.findall(r'd\.status [!=]== "([a-z]+)"', text)
        assert found, f"{name} no longer sorts the diagnostics by their status"
        compared.update(found)
    assert compared <= known, compared - known
    assert "impossible" in compared
