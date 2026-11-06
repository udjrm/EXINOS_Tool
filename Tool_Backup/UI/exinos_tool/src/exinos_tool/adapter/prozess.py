"""Startet ein Backend als eigenen Prozess (Festlegung: separater Prozess).

Das Arbeitsverzeichnis des Prozesses ist der Austauschordner. Dadurch
arbeiten Mock und echtes Backend mit denselben relativen Dateinamen.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .basis import Ergebnis

STANDARD_ZEITLIMIT = 600.0


class ProzessBackend:
    def __init__(self, befehl: Sequence[str], zeitlimit_s: float = STANDARD_ZEITLIMIT):
        if not befehl:
            raise ValueError("Der Backend-Befehl ist leer.")
        erster = sys.executable if befehl[0] == "python" else befehl[0]
        self._befehl = [erster, *befehl[1:]]
        self._zeitlimit = zeitlimit_s

    def _aufrufen(self, funktion: str, ordner: Path) -> Ergebnis:
        if not ordner.is_dir():
            return Ergebnis(False, f"Austauschordner {ordner} existiert nicht.")
        try:
            lauf = subprocess.run(
                [*self._befehl, funktion],
                cwd=ordner,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._zeitlimit,
                check=False,
            )
        except FileNotFoundError:
            return Ergebnis(False, f"Backend-Programm nicht gefunden: {self._befehl[0]}")
        except subprocess.TimeoutExpired:
            return Ergebnis(False, f"Zeitlimit von {self._zeitlimit:.0f} s ueberschritten.")

        zeilen = [z for z in (lauf.stdout + "\n" + lauf.stderr).splitlines() if z.strip()]
        fehler = [z for z in zeilen if z.startswith("FEHLER;")]
        if lauf.returncode != 0 or fehler:
            if fehler:
                meldung = fehler[-1]
            elif zeilen:
                meldung = zeilen[-1]
            else:
                meldung = f"Exitcode {lauf.returncode}"
            return Ergebnis(False, meldung)
        return Ergebnis(True, zeilen[-1] if zeilen else "")

    def klassen_und_dsm(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("klassen_und_dsm", Path(ordner))

    def nwa(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("nwa", Path(ordner))

    def abc(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("abc", Path(ordner))

    def nwa_und_abc(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("nwa_und_abc", Path(ordner))

    def parameteranfrage(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("parameteranfrage", Path(ordner))

    def amesim_code_erzeugen(self, ordner: Path) -> Ergebnis:
        return self._aufrufen("amesim_code_erzeugen", Path(ordner))

    def version(self, ordner: Path | None = None) -> Ergebnis:
        return self._aufrufen(
            "version", Path(ordner) if ordner else Path(tempfile.gettempdir())
        )


def backend_laden(pfad: str | Path) -> ProzessBackend:
    """Erzeugt den Adapter aus konfiguration/config.json."""
    pfad = Path(pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    eintrag = daten.get("backend")
    if not eintrag or "befehl" not in eintrag:
        raise ValueError(f"{pfad.name}: Abschnitt 'backend' mit 'befehl' fehlt.")
    befehl = list(eintrag["befehl"])
    if (
        len(befehl) > 1
        and not befehl[1].startswith("-")
        and not Path(befehl[1]).is_absolute()
    ):
        befehl[1] = str((pfad.parent / befehl[1]).resolve())
    return ProzessBackend(
        befehl, float(eintrag.get("zeitlimit_s", STANDARD_ZEITLIMIT))
    )