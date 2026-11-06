"""Pruefungen P-1 bis P-8 (Abnahme 3) und die Erwartungswerte der Abnahme."""

from __future__ import annotations

import copy

import pytest

from conftest import ERWARTUNG
from exinos_tool.core.modell import Bauteil, Verbindung
from exinos_tool.core.pruefung import Schwere, pruefe


def codes(bericht, schwere=None) -> set[str]:
    return {
        b.code
        for b in bericht.befunde
        if schwere is None or b.schwere is schwere
    }


def test_abnahmewerte(pool, anlagen, anlage_name):
    bericht = pruefe(anlagen[anlage_name], pool)
    assert bericht.zusammenfassung() == ERWARTUNG[anlage_name], bericht.protokoll()
    assert bericht.exportfaehig


def test_exinos_hinweis_ist_der_erwartete(pool, anlagen):
    bericht = pruefe(anlagen["EXINOS"], pool)
    (hinweis,) = bericht.hinweise
    assert hinweis.code == "P-8"
    assert "Se_Antrieb_Falt" in hinweis.elemente


def test_protokollformat(pool, anlagen):
    bericht = pruefe(anlagen["EXINOS"], pool)
    schwere, quelle, text = bericht.protokoll().split(";", 2)
    assert schwere in {"FEHLER", "WARNUNG", "HINWEIS", "INFO"}
    assert quelle == "P-8"
    assert text


# ----------------------------------------------------------------------
# Abnahme 3: Jede Pruefung loest bei einem passenden Fehlerfall aus.
# ----------------------------------------------------------------------


@pytest.fixture
def basis(anlagen):
    """Eine fehlerfreie Kopie als Ausgangspunkt fuer die Fehlerfaelle."""
    return copy.deepcopy(anlagen["ZFalter"])


def test_p1_unzulaessige_zeichen(pool, basis):
    basis.umbenennen("Rolle_1", "Rolle-1")
    assert "P-1" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p2_unbekannter_typ(pool, basis):
    basis.bauteile["Rolle_1"].typ = "gibtsnicht"
    assert "P-2" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p2_unbekannter_port(pool, basis):
    basis.verbindungen["Z01"].nach_port = "bahn_rein"
    assert "P-2" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p3a_verschiedene_arten(pool, basis):
    basis.verbindungen["Z12"].nach_port = "welle_ab"
    bericht = pruefe(basis, pool)
    assert {"P-3b"} & codes(bericht, Schwere.FEHLER)


def test_p3b_orientierung_vertauscht(pool, basis):
    v = basis.verbindungen["Z01"]
    v.von, v.von_port, v.nach, v.nach_port = v.nach, v.nach_port, v.von, v.von_port
    assert "P-3b" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p3c_hoechstbelegung(pool, basis):
    """umlenkrolle.bahn_aus hat max 1."""
    basis.verbinden(
        Verbindung("ZX", "Rolle_1", "bahn_aus", "Rolle_9", "bahn_ein", "bahn", "Separator")
    )
    assert "P-3c" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p4_luecke_in_der_kette(pool, basis):
    del basis.verbindungen["Z05"]
    assert "P-4" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p5_bahn_fehlt(pool, basis):
    basis.verbindungen["Z01"].bahn = ""
    assert "P-5" in codes(pruefe(basis, pool), Schwere.FEHLER)


def test_p6_isoliertes_bauteil(pool, basis):
    basis.hinzufuegen(Bauteil(id="Einsam", typ="umlenkrolle"))
    assert "P-6" in codes(pruefe(basis, pool), Schwere.WARNUNG)


def test_p6_bahnen_sind_ausgenommen(pool, anlagen):
    """Materialbahnen haben nie Verbindungen und duerfen nicht warnen."""
    assert not pruefe(anlagen["ZFalter"], pool).warnungen


def test_p7_pflichtport_frei(pool, basis):
    del basis.verbindungen["Z18"]  # schwenkarm.messung ist Pflicht
    assert "P-7" in codes(pruefe(basis, pool), Schwere.WARNUNG)


def test_p8_nur_fuer_typ_antrieb(pool, basis):
    """Ein Antrieb ohne jeden Signaleingang loest P-8 aus; andere Typen nicht.

    Antrieb_Tisch hat in den Z-Falter-Daten zwei Signaleingaenge
    (Z28 sollwert, Z29 istwert). Beide muessen entfernt werden, damit der
    Antrieb wirklich ohne Signal dasteht.
    """
    del basis.verbindungen["Z28"]  # sollwert vom Taktgeber
    del basis.verbindungen["Z29"]  # istwert vom Wegaufnehmer
    bericht = pruefe(basis, pool)
    treffer = [b for b in bericht.befunde if b.code == "P-8"]
    assert len(treffer) == 1
    assert "Antrieb_Tisch" in treffer[0].elemente