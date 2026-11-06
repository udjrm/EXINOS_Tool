"""Import, Export und Round-Trip (Abnahme 1)."""

from __future__ import annotations

import pytest

from conftest import UMFANG
from exinos_tool.core.io_csv import (
    CsvFehler,
    lies_anlage,
    lies_components,
    schreibe_anlage,
)
from exinos_tool.core.modell import Anlage


def test_umfang(anlagen, anlage_name):
    anlage = anlagen[anlage_name]
    zeilen, bauteile, bahnen, verbindungen = UMFANG[anlage_name]
    assert len(anlage.bauteile) == bauteile
    assert len(anlage.bahnen) == bahnen
    assert len(anlage.bauteile) + len(anlage.bahnen) == zeilen
    assert len(anlage.verbindungen) == verbindungen


def test_ids_bleiben_erhalten(anlagen):
    """F-3: Beim Import bleiben alle ids erhalten."""
    c2s = anlagen["Coil2Stack"]
    assert "V01" in c2s.verbindungen
    assert "V60" in c2s.verbindungen
    assert c2s.verbindungen["V21"].von == "Fuehrung_Hub"
    assert c2s.verbindungen["V21"].von_port == "messung"


def test_roundtrip_mengenvergleich(anlagen, anlage_name, tmp_path):
    """Abnahme 1: Export ist inhaltlich identisch, Zeilenfolge darf abweichen."""
    original = anlagen[anlage_name]
    ziel = tmp_path / anlage_name
    schreibe_anlage(original, ziel)
    erneut = lies_anlage(ziel, anlage_name)

    nur_hier, nur_dort = original.unterschiede(erneut)
    assert not nur_hier and not nur_dort
    assert original.inhaltsgleich(erneut)
    assert original.strukturfingerabdruck() == erneut.strukturfingerabdruck()


def test_fingerabdruck_ignoriert_position(anlagen):
    anlage = anlagen["ZFalter"]
    vorher = anlage.strukturfingerabdruck()
    naechstes = next(iter(anlage.bauteile.values()))
    naechstes.x += 500
    naechstes.drehung = 90
    assert anlage.strukturfingerabdruck() == vorher


def test_fingerabdruck_reagiert_auf_struktur(anlagen):
    anlage = anlagen["ZFalter"]
    vorher = anlage.strukturfingerabdruck()
    anlage.verbindungen["Z31"].nach_port = "signal_ein_x"
    try:
        assert anlage.strukturfingerabdruck() != vorher
    finally:
        anlage.verbindungen["Z31"].nach_port = "signal_ein"


def test_rahmen_wird_abgelehnt(tmp_path):
    """Das Frontend schreibt nie eine rahmen-Zeile und liest sie nicht ein."""
    pfad = tmp_path / "components.csv"
    pfad.write_text(
        "id;typ;bezeichnung;materialpfad;baugruppe;gestellfest;bemerkung\n"
        "R1;rahmen;Rahmen;;;;\n",
        encoding="utf-8",
    )
    with pytest.raises(CsvFehler, match="rahmen"):
        lies_components(pfad, Anlage())


def test_semikolon_im_freitext(tmp_path):
    pfad = tmp_path / "components.csv"
    pfad.write_text(
        "id;typ;bezeichnung;materialpfad;baugruppe;gestellfest;bemerkung\n"
        "A;umlenkrolle;Rolle;El;;ja;eins\n",
        encoding="utf-8",
    )
    anlage = lies_components(pfad, Anlage())
    anlage.bauteile["A"].bemerkung = "eins;zwei"
    from exinos_tool.core.io_csv import schreibe_components

    with pytest.raises(CsvFehler, match="Semikolon|';'"):
        schreibe_components(anlage, tmp_path / "raus.csv")