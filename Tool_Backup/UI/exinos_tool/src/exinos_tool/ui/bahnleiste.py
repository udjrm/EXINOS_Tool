"""Bahnleiste: zeigt die angelegten Bahnen und waehlt die aktive Bahn.

Die aktive Bahn wird beim Ziehen einer Bahn-Verbindung vorgewaehlt
(Paket 5c-2). Die Leiste meldet Aenderungen per Signal.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ..app.controller import Controller


class Bahnleiste(QWidget):
    #: Es wurde etwas an den Bahnen geaendert (neu, geaendert, geloescht).
    bahnen_geaendert = Signal()
    #: Die aktive Bahn wurde gewechselt (bahn_id oder "").
    aktive_bahn_gewechselt = Signal(str)

    def __init__(self, controller: Controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller

        aufbau = QHBoxLayout(self)
        aufbau.setContentsMargins(8, 4, 8, 4)

        aufbau.addWidget(QLabel("Aktive Bahn:"))

        self._auswahl = QComboBox()
        self._auswahl.setMinimumWidth(200)
        self._auswahl.currentIndexChanged.connect(self._auswahl_gewechselt)
        aufbau.addWidget(self._auswahl)

        self._neu = QPushButton("Neue Bahn …")
        self._neu.clicked.connect(self._bahn_anlegen)
        aufbau.addWidget(self._neu)

        self._bearbeiten = QPushButton("Bearbeiten …")
        self._bearbeiten.clicked.connect(self._bahn_bearbeiten)
        aufbau.addWidget(self._bearbeiten)

        self._loeschen = QPushButton("Löschen")
        self._loeschen.clicked.connect(self._bahn_loeschen)
        aufbau.addWidget(self._loeschen)

        aufbau.addStretch(1)
        self.neu_laden()

    # ------------------------------------------------------------------

    def _farb_symbol(self, farbe: str) -> QIcon:
        bild = QPixmap(14, 14)
        bild.fill(QColor(farbe))
        return QIcon(bild)

    def neu_laden(self) -> None:
        """Fuellt die Auswahl aus den Bahnen der Anlage."""
        self._auswahl.blockSignals(True)
        self._auswahl.clear()
        bahnen = self.controller.bahnen()
        for bahn in bahnen:
            text = f"{bahn.id} ({bahn.kuerzel}) – {bahn.bezeichnung}"
            self._auswahl.addItem(self._farb_symbol(bahn.farbe), text, bahn.id)
        self._auswahl.blockSignals(False)

        hat_bahnen = bool(bahnen)
        self._bearbeiten.setEnabled(hat_bahnen)
        self._loeschen.setEnabled(hat_bahnen)
        if hat_bahnen:
            self.aktive_bahn_gewechselt.emit(self.aktive_bahn())

    def aktive_bahn(self) -> str:
        return self._auswahl.currentData() or ""

    def anzahl(self) -> int:
        return self._auswahl.count()

    # ------------------------------------------------------------------

    def _auswahl_gewechselt(self) -> None:
        self.aktive_bahn_gewechselt.emit(self.aktive_bahn())

    def _bahn_anlegen(self) -> None:
        if self._auswahl.count() >= 3:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self, "Grenze erreicht", "Es sind hoechstens drei Bahnen vorgesehen."
            )
            return

        from .bahn_dialog import BahnDialog
        from .materialpfade import pfad_bezeichnung

        vorschlag_id = f"Bahn{self._auswahl.count() + 1}"
        dialog = BahnDialog(self, bahn_id=vorschlag_id)
        if dialog.exec() != BahnDialog.Accepted:
            return
        if not dialog.bahn_id():
            return
        bezeichnung = dialog.bezeichnung() or pfad_bezeichnung(dialog.kuerzel())
        try:
            self.controller.bahn_anlegen(
                dialog.bahn_id(), bezeichnung, dialog.kuerzel(), dialog.farbe()
            )
        except KeyError as fehler:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Bahn anlegen", str(fehler))
            return
        self.neu_laden()
        self._auswahl.setCurrentIndex(self._auswahl.findData(dialog.bahn_id()))
        self.bahnen_geaendert.emit()

    def _bahn_bearbeiten(self) -> None:
        bahn_id = self.aktive_bahn()
        if not bahn_id:
            return
        bahn = self.controller.anlage.bahnen[bahn_id]

        from .bahn_dialog import BahnDialog

        dialog = BahnDialog(
            self,
            bahn_id=bahn.id,
            bezeichnung=bahn.bezeichnung,
            kuerzel=bahn.kuerzel,
            farbe=bahn.farbe,
            id_sperren=True,
        )
        if dialog.exec() != BahnDialog.Accepted:
            return
        self.controller.bahn_aendern(
            bahn_id, dialog.bezeichnung(), dialog.kuerzel(), dialog.farbe()
        )
        self.neu_laden()
        self._auswahl.setCurrentIndex(self._auswahl.findData(bahn_id))
        self.bahnen_geaendert.emit()

    def _bahn_loeschen(self) -> None:
        bahn_id = self.aktive_bahn()
        if not bahn_id:
            return

        from PySide6.QtWidgets import QMessageBox

        betroffen = [
            v
            for v in self.controller.anlage.verbindungen.values()
            if v.art == "bahn" and v.bahn == bahn_id
        ]
        if betroffen:
            antwort = QMessageBox.question(
                self,
                "Bahn löschen",
                f"{bahn_id} wird von {len(betroffen)} Verbindung(en) genutzt. "
                "Diese verlieren ihre Bahnzuordnung. Fortfahren?",
            )
            if antwort != QMessageBox.Yes:
                return
        self.controller.bahn_entfernen(bahn_id)
        self.neu_laden()
        self.bahnen_geaendert.emit()