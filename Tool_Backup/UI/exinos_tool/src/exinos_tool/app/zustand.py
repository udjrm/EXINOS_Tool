"""Zustandsautomat: Schrittleiste, Freigaben und Veraltet-Kennzeichnung.

Alles wird aus Fingerabdruecken berechnet. Es gibt keine gesetzten Flags,
die vergessen werden koennen (U-1, Z-7, Q-7).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Schritt(enum.IntEnum):
    AUFBAU = 1
    PRUEFUNG = 2
    NWA = 3
    ERGEBNIS = 4
    PARAMETER = 5
    CODE = 6


SCHRITTNAMEN: dict[Schritt, str] = {
    Schritt.AUFBAU: "Aufbau",
    Schritt.PRUEFUNG: "Prüfung",
    Schritt.NWA: "NWA",
    Schritt.ERGEBNIS: "Ergebnis",
    Schritt.PARAMETER: "Parameter",
    Schritt.CODE: "Amesim-Code",
}


@dataclass(frozen=True)
class Freigabe:
    erlaubt: bool
    grund: str = ""


@dataclass(frozen=True)
class Zustand:
    """Momentaufnahme. Alle Fingerabdruecke stammen aus der Anlage bzw. dem Projekt."""

    struktur_fingerabdruck: str
    pruefung_fingerabdruck: str | None = None
    pruefung_ok: bool = False
    struktur_analyse_fingerabdruck: str | None = None
    abc_fingerabdruck: str | None = None
    parameter_vollstaendig: bool = False


def pruefung_gueltig(z: Zustand) -> bool:
    """Gilt, wenn die letzte Pruefung ohne Fehler lief und die Anlage seitdem unveraendert ist."""
    return (
        z.pruefung_fingerabdruck is not None
        and z.pruefung_ok
        and z.pruefung_fingerabdruck == z.struktur_fingerabdruck
    )


def ergebnis_aktuell(z: Zustand) -> bool:
    """Die ABC-Analyse gehoert zur aktuellen Struktur."""
    return z.abc_fingerabdruck is not None and z.abc_fingerabdruck == z.struktur_fingerabdruck


def veraltet(z: Zustand) -> bool:
    """Z-7: Mindestens ein gespeichertes Ergebnis gehoert zu einer anderen Struktur."""
    return any(
        fp is not None and fp != z.struktur_fingerabdruck
        for fp in (z.struktur_analyse_fingerabdruck, z.abc_fingerabdruck)
    )


def freigaben_fuer(z: Zustand) -> dict[Schritt, Freigabe]:
    """Welche Schritte der Schrittleiste erlaubt sind, mit Begruendung."""
    if z.pruefung_fingerabdruck is None:
        pruefgrund = "Die Anlage ist noch nicht geprüft."
    elif z.pruefung_fingerabdruck != z.struktur_fingerabdruck:
        pruefgrund = "Die Anlage wurde nach der Prüfung geändert. Bitte erneut prüfen."
    elif not z.pruefung_ok:
        pruefgrund = "Die Prüfung meldet Fehler. Export und Analyse sind gesperrt."
    else:
        pruefgrund = ""

    if ergebnis_aktuell(z):
        ergebnisgrund = ""
    elif veraltet(z):
        ergebnisgrund = (
            "Die Ergebnisse sind veraltet, weil die Anlage geändert wurde. "
            "NWA erneut bestätigen."
        )
    else:
        ergebnisgrund = "Noch keine ABC-Analyse. NWA bestätigen."

    if ergebnisgrund:
        codegrund = ergebnisgrund
    elif not z.parameter_vollstaendig:
        codegrund = "Pflichtparameter fehlen."
    else:
        codegrund = ""

    return {
        Schritt.AUFBAU: Freigabe(True),
        Schritt.PRUEFUNG: Freigabe(True),
        Schritt.NWA: Freigabe(not pruefgrund, pruefgrund),
        Schritt.ERGEBNIS: Freigabe(not ergebnisgrund, ergebnisgrund),
        Schritt.PARAMETER: Freigabe(not ergebnisgrund, ergebnisgrund),
        Schritt.CODE: Freigabe(not codegrund, codegrund),
    }