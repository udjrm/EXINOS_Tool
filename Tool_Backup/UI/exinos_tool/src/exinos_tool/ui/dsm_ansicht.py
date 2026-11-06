from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class DsmAnsicht(QWidget):
    bestaetigt = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabelle = QTableWidget(self)
        self._tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._bestaetigen = QPushButton("DSM bestätigen und NWA öffnen", self)
        self._bestaetigen.clicked.connect(self.bestaetigt)
        layout = QVBoxLayout(self)
        layout.addWidget(self._tabelle)
        layout.addWidget(self._bestaetigen)

    def setzen(self, zeilen: list[dict[str, str]]) -> None:
        if not zeilen:
            self._tabelle.clear()
            self._tabelle.setRowCount(0)
            self._tabelle.setColumnCount(0)
            return
        spalten = list(zeilen[0])
        self._tabelle.setRowCount(len(zeilen))
        self._tabelle.setColumnCount(len(spalten))
        self._tabelle.setHorizontalHeaderLabels(spalten)
        for row, zeile in enumerate(zeilen):
            for column, spalte in enumerate(spalten):
                self._tabelle.setItem(row, column, QTableWidgetItem(zeile.get(spalte, "")))
