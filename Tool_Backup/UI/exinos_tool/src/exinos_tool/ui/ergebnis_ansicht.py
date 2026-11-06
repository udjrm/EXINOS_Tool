from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class ErgebnisAnsicht(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabelle = QTableWidget(self)
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout = QVBoxLayout(self)
        layout.addWidget(self._tabelle)

    def setzen(self, zeilen: list[dict[str, str]]) -> None:
        if not zeilen:
            self._tabelle.clear()
            return
        if "B_ges" in zeilen[0]:
            zeilen = sorted(
                zeilen,
                key=lambda zeile: self._zahl(zeile.get("B_ges", "")),
                reverse=True,
            )
        spalten = list(zeilen[0])
        self._tabelle.setRowCount(len(zeilen))
        self._tabelle.setColumnCount(len(spalten))
        self._tabelle.setHorizontalHeaderLabels(spalten)
        for row, zeile in enumerate(zeilen):
            for column, spalte in enumerate(spalten):
                self._tabelle.setItem(row, column, QTableWidgetItem(zeile.get(spalte, "")))

    @staticmethod
    def _zahl(wert: str) -> float:
        try:
            return float(wert.strip().replace(".", "").replace(",", "."))
        except ValueError:
            return float("-inf")
