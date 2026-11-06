"""Einstiegspunkt der Oberflaeche. Baut Pool, Backend und Controller auf.

Aufruf:
    exinos-ui
oder
    python -m exinos_tool.ui.app
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from ..adapter.prozess import backend_laden
from ..app.controller import Controller
from ..core.io_projekt import Projekt
from ..core.nwa import lies_kriterien
from ..core.pool import Pool

WURZEL = Path(__file__).resolve().parents[3]
KONFIG = WURZEL / "konfiguration"
AUSTAUSCH = WURZEL / "Exports"


def controller_aufbauen() -> Controller:
    pool = Pool.laden(KONFIG / "bauteilpool.json")
    backend = backend_laden(KONFIG / "config.json")
    kriterien = lies_kriterien(KONFIG / "nwa_kriterien.csv")
    AUSTAUSCH.mkdir(exist_ok=True)
    return Controller(pool, backend, AUSTAUSCH, kriterien, Projekt())


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("EXINOS-Werkzeug")

    try:
        controller = controller_aufbauen()
    except Exception as fehler:
        QMessageBox.critical(None, "Start nicht moeglich", str(fehler))
        return 1

    # Projektnamen abfragen, bevor das Fenster erscheint.
    from .start_dialog import StartDialog

    dialog = StartDialog(vorschlag="EXINOS")
    if dialog.exec() != StartDialog.Accepted:
        return 0  # Nutzer hat abgebrochen
    controller.projektname_setzen(dialog.anlagenname())

    from .hauptfenster import Hauptfenster

    fenster = Hauptfenster(controller)
    fenster.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())