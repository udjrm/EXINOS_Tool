"""Bauteilbibliothek: nach Kategorie gegliederte Liste zum Ziehen (Abnahme 2).

Beim Ziehen wird der Typname als Text im MIME-Format mitgegeben. Die Szene
liest ihn und legt ueber den Controller ein Bauteil an.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ..core.pool import Pool

#: MIME-Typ, unter dem der Bauteiltyp transportiert wird.
MIME_TYP = "application/x-exinos-bauteiltyp"


class Bibliothek(QTreeWidget):
    def __init__(self, pool: Pool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pool = pool
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setMinimumWidth(220)
        self._fuellen()

    def _fuellen(self) -> None:
        nach_kategorie: dict[str, list] = {}
        for typ in self.pool.platzierbare_typen():
            nach_kategorie.setdefault(typ.kategorie, []).append(typ)

        for kategorie in sorted(nach_kategorie):
            kopf = QTreeWidgetItem([kategorie])
            kopf.setFlags(Qt.ItemIsEnabled)  # nicht ziehbar, nur Gruppe
            self.addTopLevelItem(kopf)
            for typ in sorted(nach_kategorie[kategorie], key=lambda t: t.kurz):
                kind = QTreeWidgetItem([typ.kurz])
                kind.setData(0, Qt.UserRole, typ.typ)
                kind.setToolTip(0, typ.bezeichnung)
                kopf.addChild(kind)
            kopf.setExpanded(True)

    # ------------------------------------------------------------------

    def startDrag(self, erlaubte_aktionen) -> None:  # noqa: N802 (Qt-Name)
        eintrag = self.currentItem()
        if eintrag is None:
            return
        typ = eintrag.data(0, Qt.UserRole)
        if not typ:
            return  # Kategoriekopf

        nutzdaten = QMimeData()
        nutzdaten.setData(MIME_TYP, typ.encode("utf-8"))
        nutzdaten.setText(typ)

        drag = QDrag(self)
        drag.setMimeData(nutzdaten)
        drag.exec(Qt.CopyAction)