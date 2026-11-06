"""Gemeinsame Fixtures. Pfade sind relativ zum Projektwurzelverzeichnis."""

from __future__ import annotations

from pathlib import Path

import pytest

from exinos_tool.core.io_csv import lies_anlage
from exinos_tool.core.pool import Pool

WURZEL = Path(__file__).resolve().parents[1]
POOLDATEI = WURZEL / "konfiguration" / "bauteilpool.json"
BEISPIELE = WURZEL / "beispiele"

#: Erwartungswerte der Abnahme: (Fehler, Warnungen, Hinweise)
ERWARTUNG = {
    "EXINOS": (0, 0, 1),
    "Coil2Stack": (0, 0, 0),
    "ZFalter": (0, 0, 0),
}

#: Zeilen in components.csv, Bauteile, Materialbahnen, Verbindungen
UMFANG = {
    "EXINOS": (55, 52, 3, 61),
    "Coil2Stack": (47, 46, 1, 60),
    "ZFalter": (26, 25, 1, 31),
}


@pytest.fixture(scope="session")
def pool() -> Pool:
    return Pool.laden(POOLDATEI)


@pytest.fixture(scope="session")
def anlagen() -> dict:
    return {name: lies_anlage(BEISPIELE / name, name) for name in ERWARTUNG}


@pytest.fixture(params=sorted(ERWARTUNG))
def anlage_name(request) -> str:
    """Laeuft jeden Test einmal pro Referenzanlage."""
    return request.param