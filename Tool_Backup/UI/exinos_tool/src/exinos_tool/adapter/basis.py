"""Schnittstelle zum Backend (Lastenheft D-1).

Jede Funktion arbeitet ueber Dateien im Austauschordner und gibt ein
Ergebnis zurueck. Ausnahmen gehen nie ueber die Grenze.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Ergebnis:
    """Status eines Backend-Aufrufs. erfolg=False traegt die Fehlermeldung."""

    erfolg: bool
    meldung: str = ""


class Backend(Protocol):
    def klassen_und_dsm(self, ordner: Path) -> Ergebnis: ...
    def nwa(self, ordner: Path) -> Ergebnis: ...
    def abc(self, ordner: Path) -> Ergebnis: ...
    def nwa_und_abc(self, ordner: Path) -> Ergebnis: ...
    def parameteranfrage(self, ordner: Path) -> Ergebnis: ...
    def amesim_code_erzeugen(self, ordner: Path) -> Ergebnis: ...
    def version(self, ordner: Path | None = None) -> Ergebnis: ...


FUNKTIONEN = (
    "klassen_und_dsm",
    "nwa_und_abc",
    "parameteranfrage",
    "amesim_code_erzeugen",
    "version",
)