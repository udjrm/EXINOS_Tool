"""Gewichte gegen die RPZ aus Tab. 5-2 der Dissertation."""

from __future__ import annotations

import csv

import pytest

from conftest import WURZEL
from exinos_tool.adapter.mock.mock_backend import KRITERIEN
from exinos_tool.core.nwa import gewichte_pruefen, gewichtssumme, lies_kriterien

KRITERIENDATEI = WURZEL / "konfiguration" / "nwa_kriterien.csv"


@pytest.fixture(scope="module")
def kriterien():
    return lies_kriterien(KRITERIENDATEI)


def test_summen(kriterien):
    assert gewichtssumme(kriterien["Vereinzelung"]) == pytest.approx(1.0001, abs=1e-9)
    assert gewichtssumme(kriterien["Stapeln"]) == pytest.approx(1.0, abs=1e-9)
    assert gewichte_pruefen(kriterien) == []


def test_gewichte_entsprechen_rpz(kriterien):
    """Druckfehler-Befund: 0,4884 = 336/688 gerundet, nicht 0,4984."""
    for zielgroesse, liste in kriterien.items():
        summe = sum(k.rpz for k in liste)
        for k in liste:
            assert round(k.rpz / summe, 4) == pytest.approx(k.gewicht, abs=1e-9), (
                zielgroesse,
                k.kriterium_id,
            )


def test_mock_kriterien_entsprechen_konfiguration():
    """Das Mock-Backend fuehrt dieselben Kriterien wie die Konfiguration."""
    with KRITERIENDATEI.open("r", encoding="utf-8-sig", newline="") as datei:
        zeilen = [
            tuple(z[s] for s in ("zielgroesse", "kriterium_id", "kuerzel", "kriterium", "rpz", "gewicht"))
            for z in csv.DictReader(datei, delimiter=";")
        ]
    assert zeilen == KRITERIEN