"""Controller: Kompletter Ablauf ohne Qt (Abnahme 4 und 5)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import BEISPIELE, WURZEL
from exinos_tool.adapter.prozess import backend_laden
from exinos_tool.app.controller import Controller, SchrittFehler
from exinos_tool.app.zustand import Schritt
from exinos_tool.core.io_csv import lies_anlage
from exinos_tool.core.nwa import lies_kriterien
from exinos_tool.core.pool import Pool

KONFIG = WURZEL / "konfiguration" / "config.json"
KRITERIEN_DATEI = WURZEL / "konfiguration" / "nwa_kriterien.csv"


@pytest.fixture(scope="module")
def pool() -> Pool:
    return Pool.laden(WURZEL / "konfiguration" / "bauteilpool.json")


@pytest.fixture(scope="module")
def backend():
    return backend_laden(KONFIG)


@pytest.fixture(scope="module")
def kriterien():
    return lies_kriterien(KRITERIEN_DATEI)


@pytest.fixture
def austausch(tmp_path) -> Path:
    return tmp_path / "austausch"


@pytest.fixture
def controller(pool, backend, kriterien, austausch) -> Controller:
    anlage = lies_anlage(BEISPIELE / "Coil2Stack", "Coil2Stack")
    from exinos_tool.core.io_projekt import Projekt
    projekt = Projekt(anlage=anlage)
    return Controller(pool, backend, austausch, kriterien, projekt)


def test_schritt1_aufbau_erlaubt(controller):
    freigaben = controller.freigaben()
    assert freigaben[Schritt.AUFBAU].erlaubt


def test_schritt2_pruefung_erlaubt(controller):
    freigaben = controller.freigaben()
    assert freigaben[Schritt.PRUEFUNG].erlaubt


def test_schritt2_ausfuehren(controller):
    bericht = controller.pruefen()
    assert bericht.exportfaehig
    freigaben = controller.freigaben()
    assert freigaben[Schritt.NWA].erlaubt


def test_schritt3_nwa_speichert_bewertung(controller, tmp_path):
    controller.pruefen()
    # Nach erfolgreicher Pruefung ist NWA erlaubt
    assert controller.freigaben()[Schritt.NWA].erlaubt
    
    # Struktur-Analyse
    ergebnis = controller.struktur_analysieren()
    assert ergebnis.erfolg, ergebnis.meldung
    
    # NWA-Bewertung ohne Änderungen
    eingaben = {}
    for klasse in controller.klassen():
        kid = klasse["klasse_id"]
        for kriterium in controller.kriterien_fuer("Vereinzelung"):
            eingaben[(kid, kriterium.kriterium_id)] = controller._vorschlag("Vereinzelung", kid, kriterium.kriterium_id)
    controller.bewertung_schreiben("Vereinzelung", eingaben)
    
    # ABC-Analyse
    ergebnis = controller.nwa_analysieren()
    assert ergebnis.erfolg, ergebnis.meldung
    assert controller.freigaben()[Schritt.ERGEBNIS].erlaubt


def test_schritt5_parameter_abfragen(controller):
    controller.pruefen()
    controller.struktur_analysieren()
    
    eingaben = {}
    for klasse in controller.klassen():
        kid = klasse["klasse_id"]
        for kriterium in controller.kriterien_fuer("Vereinzelung"):
            eingaben[(kid, kriterium.kriterium_id)] = 1
    controller.bewertung_schreiben("Vereinzelung", eingaben)
    
    controller.nwa_analysieren()
    ergebnis = controller.parameter_abfragen()
    assert ergebnis.erfolg, ergebnis.meldung
    
    anfrage = controller.parameter_anfrage()
    assert len(anfrage) > 0


def test_schritt6_code_erzeugen(controller):
    controller.pruefen()
    controller.struktur_analysieren()
    
    eingaben = {(k["klasse_id"], controller.kriterien_fuer("Vereinzelung")[0].kriterium_id): 1 
                for k in controller.klassen()}
    controller.bewertung_schreiben("Vereinzelung", eingaben)
    controller.nwa_analysieren()
    controller.parameter_abfragen()
    
    # Alle Parameter mit Standardwerten setzen
    for z in controller.parameter_anfrage():
        controller.parameter_setzen(z["component_id"], z["parameter"], z["standardwert"])
    
    ergebnis = controller.code_erzeugen()
    assert ergebnis.erfolg, ergebnis.meldung
    
    code = controller.code_text()
    assert "PLATZHALTER" in code


def test_n5_zielgroessenwechsel_behaelt_struktur(controller):
    """N-5 und Abnahme 5: Ordner bleibt gleich, Struktur-CSV unverändert."""
    controller.pruefen()
    ergebnis = controller.struktur_analysieren()
    fp = controller.anlage.strukturfingerabdruck()[:12]
    ordner1 = controller.aktueller_ordner()
    
    # DSM und Klassen unverändert
    assert (ordner1 / "classes.csv").exists()
    import hashlib
    hash1 = hashlib.sha256((ordner1 / "classes.csv").read_bytes()).hexdigest()
    
    # Zielgrößenwechsel
    eingaben_ve = {(k["klasse_id"], "VE1"): 1 for k in controller.klassen()}
    controller.bewertung_schreiben("Vereinzelung", eingaben_ve)
    controller.nwa_analysieren()
    
    ordner2 = controller.aktueller_ordner()
    assert ordner1 == ordner2
    hash2 = hashlib.sha256((ordner2 / "classes.csv").read_bytes()).hexdigest()
    assert hash1 == hash2