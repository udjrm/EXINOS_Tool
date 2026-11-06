"""Hintergrundausfuehrung der Backend-Aufrufe (D-3), ohne Qt.

Ein Auftrag trennt den Aufruf in zwei Teile:

  ausfuehren()     laeuft im Hintergrund und beruehrt nur den Austauschordner
  abschliessen()   laeuft im Hauptthread und uebernimmt das Ergebnis

Die Qt-Schicht verbindet den Rueckruf des Hintergrunds mit einem Signal,
damit abschliessen() im GUI-Thread laeuft.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..adapter.basis import Ergebnis


@dataclass
class Auftrag:
    name: str
    ordner: Path
    aufruf: Callable[[Path], Ergebnis]
    abschluss: Callable[[Ergebnis], Ergebnis]

    def ausfuehren(self) -> Ergebnis:
        """Im Hintergrund. Faengt alle Ausnahmen ab, sie gehen nie ueber die Grenze."""
        try:
            return self.aufruf(self.ordner)
        except Exception as fehler:
            return Ergebnis(False, f"{self.name}: {type(fehler).__name__}: {fehler}")

    def abschliessen(self, ergebnis: Ergebnis) -> Ergebnis:
        """Im Hauptthread. Uebernimmt das Ergebnis in den Projektzustand."""
        return self.abschluss(ergebnis)


class Hintergrund:
    def __init__(self, arbeiter: int = 1) -> None:
        # Ein Arbeiter: Backend-Laeufe auf demselben Austauschordner laufen nacheinander.
        self._pool = ThreadPoolExecutor(
            max_workers=arbeiter, thread_name_prefix="exinos-backend"
        )

    def starten(
        self,
        auftrag: Auftrag,
        rueckruf: Callable[[Auftrag, Ergebnis], None] | None = None,
    ) -> Future:
        """Startet den Auftrag. Der Rueckruf laeuft im Arbeitsthread."""
        future = self._pool.submit(auftrag.ausfuehren)
        if rueckruf is not None:
            future.add_done_callback(lambda f: rueckruf(auftrag, f.result()))
        return future

    def schliessen(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)