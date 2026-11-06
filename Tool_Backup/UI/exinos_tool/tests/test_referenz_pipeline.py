from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from conftest import BEISPIELE
from exinos_tool.adapter.prozess import backend_laden


@pytest.fixture
def backend():
    return backend_laden(Path(__file__).parents[1] / "konfiguration" / "config.json")


def _lies(pfad: Path) -> list[list[str]]:
    with pfad.open("r", encoding="utf-8-sig", newline="") as datei:
        return list(csv.reader(datei, delimiter=";"))


def test_referenz_pipeline_erzeugt_alle_stufen(backend, tmp_path: Path) -> None:
    for name in ("components.csv", "connections.csv"):
        shutil.copy2(BEISPIELE / "Coil2Stack" / name, tmp_path / name)

    ergebnis = backend.klassen_und_dsm(tmp_path)

    assert ergebnis.erfolg, ergebnis.meldung
    for name in (
        "instances.csv",
        "edges.csv",
        "pruefung.txt",
        "classes.csv",
        "dsm_matrix.csv",
        "dsm_edges.csv",
    ):
        assert (tmp_path / name).exists(), name

    matrix = _lies(tmp_path / "dsm_matrix.csv")
    assert matrix[0][0] == ""
    assert matrix[0][-1] == "AS"
    assert matrix[-1][0] == "PS"
    assert all(row[i] == "X" for i, row in enumerate(matrix[1:-1], start=1))
