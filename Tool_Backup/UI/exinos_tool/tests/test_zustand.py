"""Zustandsautomat: Freigaben und Veraltet-Logik (U-1, Z-7, Q-7)."""

from __future__ import annotations

import pytest

from exinos_tool.app.zustand import (
    Freigabe,
    Schritt,
    Zustand,
    ergebnis_aktuell,
    freigaben_fuer,
    pruefung_gueltig,
    veraltet,
)


@pytest.fixture
def leer() -> Zustand:
    """Gerade geöffnet, nichts berechnet."""
    return Zustand(struktur_fingerabdruck="abc123")


@pytest.fixture
def geprueft() -> Zustand:
    """Prüfung erfolgreich, Struktur unverändert."""
    return Zustand(
        struktur_fingerabdruck="abc123",
        pruefung_fingerabdruck="abc123",
        pruefung_ok=True,
    )


@pytest.fixture
def nach_struktur(geprueft) -> Zustand:
    """Struktur geändert nach erfolgreicher Prüfung."""
    return Zustand(
        struktur_fingerabdruck="xyz789",
        pruefung_fingerabdruck=geprueft.pruefung_fingerabdruck,
        pruefung_ok=geprueft.pruefung_ok,
    )


@pytest.fixture
def nach_analyse(geprueft) -> Zustand:
    """ABC-Analyse erfolgreich."""
    return Zustand(
        struktur_fingerabdruck="abc123",
        pruefung_fingerabdruck="abc123",
        pruefung_ok=True,
        abc_fingerabdruck="abc123",
    )


# ------------------------------------------------------------------
# Gültigkeitsprüfungen
# ------------------------------------------------------------------


def test_pruefung_gueltig(geprueft, nach_struktur):
    assert pruefung_gueltig(geprueft)
    assert not pruefung_gueltig(nach_struktur)


def test_ergebnis_aktuell(nach_analyse, nach_struktur):
    assert ergebnis_aktuell(nach_analyse)
    assert not ergebnis_aktuell(nach_struktur)


def test_veraltet_z7(geprueft):
    """Z-7: Veraltet ist true, wenn ein Ergebnis nicht zur aktuellen Struktur gehört."""
    # Keine Ergebnisse → nicht veraltet
    assert not veraltet(geprueft)
    
    # Struktur-Analyse zu alter Struktur → veraltet
    zustand_mit_alter_analyse = Zustand(
        struktur_fingerabdruck="neu123",
        pruefung_fingerabdruck="neu123",
        pruefung_ok=True,
        struktur_analyse_fingerabdruck="alt123",  # ← zur alten Struktur
    )
    assert veraltet(zustand_mit_alter_analyse)
    
    # ABC zu alter Struktur → veraltet
    zustand_mit_alter_abc = Zustand(
        struktur_fingerabdruck="neu123",
        pruefung_fingerabdruck="neu123",
        pruefung_ok=True,
        abc_fingerabdruck="alt123",  # ← zur alten Struktur
    )
    assert veraltet(zustand_mit_alter_abc)


def test_veraltet_bei_analyse_und_struktur_unterschiedlich(geprueft):
    """Wenn Struktur und ABC-Analyse unterschiedliche Fingerabdrücke haben."""
    zustand = Zustand(
        struktur_fingerabdruck="neu123",
        pruefung_fingerabdruck="alt123",
        pruefung_ok=True,
        abc_fingerabdruck="alt123",
    )
    assert veraltet(zustand)


# ------------------------------------------------------------------
# Freigaben
# ------------------------------------------------------------------


def test_freigaben_aufbau_immer_erlaubt(leer):
    freigaben = freigaben_fuer(leer)
    assert freigaben[Schritt.AUFBAU].erlaubt


def test_freigaben_pruefung_immer_erlaubt(leer):
    freigaben = freigaben_fuer(leer)
    assert freigaben[Schritt.PRUEFUNG].erlaubt


def test_freigaben_nwa_braucht_gepruefung(leer, geprueft):
    """NWA erlaubt nur nach erfolgreicher Prüfung."""
    freigaben_leer = freigaben_fuer(leer)
    assert not freigaben_leer[Schritt.NWA].erlaubt
    assert "noch nicht geprüft" in freigaben_leer[Schritt.NWA].grund

    freigaben_ok = freigaben_fuer(geprueft)
    assert freigaben_ok[Schritt.NWA].erlaubt


def test_freigaben_nwa_braucht_aktuelle_pruefung(nach_struktur):
    """Nach Strukturänderung braucht es eine neue Prüfung."""
    freigaben = freigaben_fuer(nach_struktur)
    assert not freigaben[Schritt.NWA].erlaubt
    assert "nach der Prüfung geändert" in freigaben[Schritt.NWA].grund


def test_freigaben_ergebnis_braucht_analyse(geprueft):
    """Ergebnis ist erst nach erfolgreicher ABC-Analyse erlaubt."""
    freigaben = freigaben_fuer(geprueft)
    assert not freigaben[Schritt.ERGEBNIS].erlaubt
    assert "abc-analyse" in freigaben[Schritt.ERGEBNIS].grund.lower()


def test_freigaben_parameter_folgt_ergebnis(nach_analyse):
    freigaben = freigaben_fuer(nach_analyse)
    assert freigaben[Schritt.PARAMETER].erlaubt


def test_freigaben_code_braucht_parameter(nach_analyse):
    """Code ist nicht erlaubt, wenn Parameter unvollständig."""
    zustand = Zustand(
        struktur_fingerabdruck="abc123",
        pruefung_fingerabdruck="abc123",
        pruefung_ok=True,
        abc_fingerabdruck="abc123",
        parameter_vollstaendig=False,
    )
    freigaben = freigaben_fuer(zustand)
    assert not freigaben[Schritt.CODE].erlaubt
    assert "Pflichtparameter" in freigaben[Schritt.CODE].grund


def test_freigaben_code_ok(nach_analyse):
    zustand = Zustand(
        struktur_fingerabdruck=nach_analyse.struktur_fingerabdruck,
        pruefung_fingerabdruck=nach_analyse.pruefung_fingerabdruck,
        pruefung_ok=nach_analyse.pruefung_ok,
        abc_fingerabdruck=nach_analyse.abc_fingerabdruck,
        parameter_vollstaendig=True,
    )
    freigaben = freigaben_fuer(zustand)
    assert freigaben[Schritt.CODE].erlaubt