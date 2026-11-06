"""Undo, Redo und Makros (E-4, E-5)."""

from __future__ import annotations

import pytest

from exinos_tool.app.befehle import (
    BauteilHinzufuegen,
    BauteilUmbenennen,
    BauteilVerschieben,
    Befehlsstapel,
    MakroBefehl,
    VerbindungHinzufuegen,
)
from exinos_tool.core.modell import Anlage, Bauteil, Verbindung


@pytest.fixture
def anlage() -> Anlage:
    return Anlage(name="Test")


@pytest.fixture
def stapel(anlage) -> Befehlsstapel:
    return Befehlsstapel(anlage, grenze=10)


def test_bauteil_hinzufuegen_ausfuehren(stapel, anlage):
    b = Bauteil(id="R1", typ="umlenkrolle")
    stapel.ausfuehren(BauteilHinzufuegen(b))
    assert "R1" in anlage.bauteile


def test_bauteil_hinzufuegen_rueckgaengig(stapel, anlage):
    b = Bauteil(id="R1", typ="umlenkrolle")
    stapel.ausfuehren(BauteilHinzufuegen(b))
    stapel.rueckgaengig()
    assert "R1" not in anlage.bauteile


def test_bauteil_verschieben_verschmilzt(stapel, anlage):
    """Aufeinanderfolgende Bewegungen verschmelzen zu einem Undo-Schritt (E-4)."""
    b = Bauteil(id="R1", typ="umlenkrolle", x=0, y=0)
    anlage.hinzufuegen(b)
    
    stapel.ausfuehren(BauteilVerschieben("R1", (100, 100)))
    stapel.ausfuehren(BauteilVerschieben("R1", (200, 200)))
    stapel.ausfuehren(BauteilVerschieben("R1", (300, 300)))
    
    assert len(stapel._zurueck) == 1
    assert anlage.bauteile["R1"].x == 300
    
    stapel.rueckgaengig()
    assert anlage.bauteile["R1"].x == 0


def test_verschieben_oeффnet_neue_verschmelzung(stapel, anlage):
    """Andere Befehle unterbrechen die Verschmelzung."""
    b = Bauteil(id="R1", typ="umlenkrolle", x=0, y=0)
    anlage.hinzufuegen(b)
    
    stapel.ausfuehren(BauteilVerschieben("R1", (100, 100)))
    stapel.ausfuehren(BauteilUmbenennen("R1", "R2"))
    stapel.ausfuehren(BauteilVerschieben("R2", (200, 200)))
    
    assert len(stapel._zurueck) == 3


def test_makro(stapel, anlage):
    """Mehrere Befehle werden als ein Schritt zusammengefasst (E-5)."""
    b = Bauteil(id="R1", typ="umlenkrolle")
    v = Verbindung(id="V1", von="R1", von_port="bahn_ein", nach="R2", nach_port="bahn_aus", art="bahn", bahn="")
    
    with stapel.makro("Komplexe Änderung"):
        stapel.ausfuehren(BauteilHinzufuegen(b))
        stapel.ausfuehren(VerbindungHinzufuegen(v))
    
    assert len(stapel._zurueck) == 1
    assert isinstance(stapel._zurueck[0], MakroBefehl)
    assert stapel._zurueck[0].text == "Komplexe Änderung"
    
    stapel.rueckgaengig()
    assert "R1" not in anlage.bauteile


def test_makro_rollback_bei_fehler(stapel, anlage):
    """Wenn ein Befehl im Makro fehlschlägt, wird alles rückgängig gemacht."""
    b = Bauteil(id="R1", typ="umlenkrolle")
    anlage.hinzufuegen(b)
    
    with pytest.raises(KeyError):
        with stapel.makro("Fehlgeschlagenes Makro"):
            stapel.ausfuehren(BauteilHinzufuegen(b))
            stapel.ausfuehren(BauteilUmbenennen("Nicht_vorhanden", "Neu"))
    
    assert "R1" in anlage.bauteile


def test_rueckgaengig_wiederholen(stapel, anlage):
    b = Bauteil(id="R1", typ="umlenkrolle")
    stapel.ausfuehren(BauteilHinzufuegen(b))
    assert "R1" in anlage.bauteile
    
    stapel.rueckgaengig()
    assert "R1" not in anlage.bauteile
    assert stapel.kann_wiederholen
    
    stapel.wiederholen()
    assert "R1" in anlage.bauteile
    assert not stapel.kann_wiederholen


def test_neue_befehle_leeren_redo_stapel(stapel, anlage):
    b = Bauteil(id="R1", typ="umlenkrolle")
    anlage.hinzufuegen(b)
    
    stapel.ausfuehren(BauteilVerschieben("R1", (100, 100)))
    stapel.rueckgaengig()
    assert stapel.kann_wiederholen
    
    stapel.ausfuehren(BauteilVerschieben("R1", (200, 200)))
    assert not stapel.kann_wiederholen

def test_duplizieren(stapel, anlage):
    """Duplizieren legt eine Kopie mit neuer id und Versatz an, Undo entfernt sie."""
    from exinos_tool.app.befehle import BauteilDuplizieren
    from exinos_tool.core.modell import Bauteil

    anlage.hinzufuegen(Bauteil(id="R1", typ="umlenkrolle", x=100, y=100))
    stapel.ausfuehren(BauteilDuplizieren("R1", "R2"))

    assert "R2" in anlage.bauteile
    assert anlage.bauteile["R2"].typ == "umlenkrolle"
    assert anlage.bauteile["R2"].x == 130  # 100 + 30 Versatz
    assert anlage.bauteile["R2"].y == 130

    stapel.rueckgaengig()
    assert "R2" not in anlage.bauteile
    assert "R1" in anlage.bauteile  # Original bleibt