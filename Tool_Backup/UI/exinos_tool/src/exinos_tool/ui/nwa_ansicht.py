from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class NwaAnsicht(QWidget):
    bestaetigt = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabelle = QTableWidget(self)
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._bestaetigen = QPushButton("NWA bestätigen und ABC-Analyse starten", self)
        self._bestaetigen.clicked.connect(self.bestaetigt.emit)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nutzwertanalyse"))
        layout.addWidget(self._tabelle)
        layout.addWidget(self._bestaetigen)

    def setzen(self, zeilen: list[dict[str, str]]) -> None:
        if not zeilen:
            self._tabelle.clear()
            return
        spalten = list(zeilen[0])
        self._tabelle.setRowCount(len(zeilen))
        self._tabelle.setColumnCount(len(spalten))
        self._tabelle.setHorizontalHeaderLabels(spalten)
        for row, zeile in enumerate(zeilen):
            for column, spalte in enumerate(spalten):
                self._tabelle.setItem(row, column, QTableWidgetItem(zeile.get(spalte, "")))
