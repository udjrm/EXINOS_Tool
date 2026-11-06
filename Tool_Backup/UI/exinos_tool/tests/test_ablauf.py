"""Schritt 1 bis 6 headless ueber das Backend (Abnahme 4 und 5)."""

from __future__ import annotations

import csv
import hashlib
import shutil
from collections import Counter
from pathlib import Path

import pytest

from conftest import BEISPIELE, UMFANG, WURZEL
from exinos_tool.adapter.prozess import backend_laden

KONFIG = WURZEL / "konfiguration" / "config.json"
ERWARTET_JE_ABC = {"A": 6, "B": 3, "C": 1}
ABC_ERLAUBT = {"A", "B", "C"}


@pytest.fixture
def backend():
    return backend_laden(KONFIG)


@pytest.fixture
def ordner(tmp_path) -> Path:
    ziel = tmp_path / "Coil2Stack"
    ziel.mkdir()
    for datei in ("components.csv", "connections.csv"):
        shutil.copy(BEISPIELE / "Coil2Stack" / datei, ziel / datei)
    return ziel


def lies(ordner: Path, name: str) -> list[dict[str, str]]:
    with (ordner / name).open("r", encoding="utf-8-sig", newline="") as datei:
        return list(csv.DictReader(datei, delimiter=";"))


def hash_von(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def bewertung_aus_vorschlag(ordner: Path, zielgroesse: str) -> None:
    """Simuliert die Bestaetigung der NWA im Frontend ohne Aenderungen."""
    zeilen = [
        {
            "zielgroesse": z["zielgroesse"],
            "klasse_id": z["klasse_id"],
            "kriterium_id": z["kriterium_id"],
            "bewertung": z["vorschlag"],
            "geaendert": "nein",
            "begruendung": "",
        }
        for z in lies(ordner, "nwa_vorschlag.csv")
        if z["zielgroesse"] == zielgroesse
    ]
    with (ordner / "nwa_bewertung.csv").open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.DictWriter(
            datei,
            fieldnames=["zielgroesse", "klasse_id", "kriterium_id", "bewertung", "geaendert", "begruendung"],
            delimiter=";",
            lineterminator="\n",
        )
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def parameter_schreiben(ordner: Path, eingaben: dict | None = None) -> None:
    """Schreibt parameters.csv: Standardwerte, optional mit eigenen Eingaben."""
    eingaben = eingaben or {}
    zeilen = []
    for z in lies(ordner, "parameter_request.csv"):
        schluessel = (z["component_id"], z["parameter"])
        if schluessel in eingaben:
            wert, quelle = eingaben[schluessel], "eingabe"
        else:
            wert, quelle = z["standardwert"], "standard"
        zeilen.append(
            {"component_id": z["component_id"], "parameter": z["parameter"], "wert": wert, "quelle": quelle}
        )
    with (ordner / "parameters.csv").open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.DictWriter(
            datei, fieldnames=["component_id", "parameter", "wert", "quelle"], delimiter=";", lineterminator="\n"
        )
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def bis_stufe2(backend, ordner: Path, zielgroesse: str = "Vereinzelung") -> None:
    assert backend.klassen_und_dsm(ordner).erfolg
    bewertung_aus_vorschlag(ordner, zielgroesse)
    ergebnis = backend.nwa_und_abc(ordner)
    assert ergebnis.erfolg, ergebnis.meldung


def test_version(backend):
    ergebnis = backend.version()
    assert ergebnis.erfolg
    assert "mock" in ergebnis.meldung.lower()


def test_stufe1_erzeugt_alle_dateien(backend, ordner):
    assert backend.klassen_und_dsm(ordner).erfolg
    for name in ("classes.csv", "dsm_matrix.csv", "nwa_kriterien.csv", "nwa_vorschlag.csv"):
        assert (ordner / name).exists(), name


def test_stufe1_vorschlaege_fuer_alle_zielgroessen(backend, ordner):
    backend.klassen_und_dsm(ordner)
    zielgroessen = {z["zielgroesse"] for z in lies(ordner, "nwa_vorschlag.csv")}
    assert zielgroessen == {"Vereinzelung", "Stapeln"}


def test_dsm_quadratisch_symmetrisch_und_mit_x_diagonale(backend, ordner):
    backend.klassen_und_dsm(ordner)
    zeilen = lies(ordner, "dsm_matrix.csv")
    klassen = [z["klasse_id"] for z in zeilen]
    assert len(zeilen) == len(klassen)
    werte = {k: {j: zeilen[i][j] for j in klassen} for i, k in enumerate(klassen)}
    for a in klassen:
        assert werte[a][a] == "X"
        for b in klassen:
            assert werte[a][b] in {"0", "3", "X"}
            if a != b:
                assert werte[a][b] == werte[b][a]


def test_dsm_direkte_verbindung_ergibt_drei(backend, ordner):
    """Antrieb_Abw --welle--> Abwickler (V14) ist eine direkte Verbindung."""
    backend.klassen_und_dsm(ordner)
    zeilen = {z["klasse_id"]: z for z in lies(ordner, "dsm_matrix.csv")}
    assert zeilen["antrieb"]["abwickler"] == "3"


def test_stufe2_ohne_bewertung_meldet_fehler(backend, ordner):
    backend.klassen_und_dsm(ordner)
    ergebnis = backend.nwa_und_abc(ordner)
    assert not ergebnis.erfolg
    assert "nwa_bewertung.csv" in ergebnis.meldung


def test_stufe2_liefert_abc_fuer_alle_bauteile(backend, ordner):
    bis_stufe2(backend, ordner)
    zeilen = lies(ordner, "analysis_result.csv")
    assert len(zeilen) == UMFANG["Coil2Stack"][1]
    abc = {z["abc"] for z in zeilen}
    assert abc <= ABC_ERLAUBT
    assert "A" in abc


def test_parameteranfrage_umfang_nach_abc(backend, ordner):
    """D-6: A erhaelt 6, B 3, C 1 Parameter je Bauteil."""
    bis_stufe2(backend, ordner)
    assert backend.parameteranfrage(ordner).erfolg
    abc = {z["component_id"]: z["abc"] for z in lies(ordner, "analysis_result.csv")}
    anzahl = Counter(z["component_id"] for z in lies(ordner, "parameter_request.csv"))
    for bauteil, stufe in abc.items():
        assert anzahl[bauteil] == ERWARTET_JE_ABC[stufe], (bauteil, stufe)


def test_parameteranfrage_deckt_datentypen_und_gruppen_ab(backend, ordner):
    bis_stufe2(backend, ordner)
    backend.parameteranfrage(ordner)
    zeilen = lies(ordner, "parameter_request.csv")
    assert {z["datentyp"] for z in zeilen} >= {"zahl", "ganzzahl", "auswahl", "text"}
    assert {z["gruppe"] for z in zeilen} >= {"Geometrie", "Massen", "Regelung"}


def test_abnahme4_ablauf_von_schritt1_bis_6(backend, ordner):
    """Abnahme 4: Schritt 1 bis 6 ohne Fehler, Platzhalter sichtbar."""
    bis_stufe2(backend, ordner)
    assert backend.parameteranfrage(ordner).erfolg
    parameter_schreiben(ordner)

    ergebnis = backend.amesim_code_erzeugen(ordner)
    assert ergebnis.erfolg, ergebnis.meldung

    text = (ordner / "amesim_modell.py").read_text(encoding="utf-8")
    assert "PLATZHALTER" in text
    compile(text, "amesim_modell.py", "exec")

    log = (ordner / "analysis_log.txt").read_text(encoding="utf-8")
    assert "WARNUNG;amesim_code_erzeugen;Platzhalter" in log


def test_abnahme5_zielgroessenwechsel_erhaelt_eingaben(backend, ordner):
    """N-5 und Abnahme 5: Stufe 2 erneut, Struktur und Eingaben bleiben."""
    bis_stufe2(backend, ordner, "Vereinzelung")
    backend.parameteranfrage(ordner)
    parameter_schreiben(ordner, {("Abwickler", "radius"): "0,25"})

    unveraendert = ["classes.csv", "dsm_matrix.csv", "nwa_vorschlag.csv", "parameters.csv"]
    vorher = {name: hash_von(ordner / name) for name in unveraendert}
    ergebnis_vorher = hash_von(ordner / "analysis_result.csv")

    bewertung_aus_vorschlag(ordner, "Stapeln")
    assert backend.nwa_und_abc(ordner).erfolg
    assert backend.parameteranfrage(ordner).erfolg

    for name in unveraendert:
        assert hash_von(ordner / name) == vorher[name], name
    assert hash_von(ordner / "analysis_result.csv") != ergebnis_vorher

    eingabe = [
        z for z in lies(ordner, "parameters.csv")
        if z["component_id"] == "Abwickler" and z["parameter"] == "radius"
    ]
    assert eingabe and eingabe[0]["wert"] == "0,25"
    assert eingabe[0]["quelle"] == "eingabe"


def test_fehlende_datei_wird_gemeldet(backend, tmp_path):
    ergebnis = backend.klassen_und_dsm(tmp_path)
    assert not ergebnis.erfolg
    assert "components.csv" in ergebnis.meldung


def test_protokoll_format(backend, ordner):
    backend.klassen_und_dsm(ordner)
    zeilen = (ordner / "analysis_log.txt").read_text(encoding="utf-8").splitlines()
    assert zeilen
    for zeile in zeilen:
        teile = zeile.split(";", 2)
        assert len(teile) == 3, zeile
        assert teile[0] in {"INFO", "WARNUNG", "HINWEIS", "FEHLER"}, zeile