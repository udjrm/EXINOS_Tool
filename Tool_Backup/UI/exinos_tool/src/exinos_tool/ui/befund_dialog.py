
"""Zeigt die Pruefbefunde als Liste, wenn der Weiter-Schritt blockiert wird."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

FARBEN = {
    "FEHLER": "#C62828",
    "WARNUNG": "#EF6C00",
    "HINWEIS": "#1565C0",
    "INFO": "#424242",
}


class BefundDialog(QDialog):
    def __init__(self, bericht, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pruefung")
        self.resize(640, 420)

        aufbau = QVBoxLayout(self)

        fehler, warnungen, hinweise = bericht.zusammenfassung()
        if fehler:
            kopf = (
                f"Die Pruefung meldet {fehler} Fehler. Der Uebergang ist "
                "gesperrt, bis sie behoben sind."
            )
        else:
            kopf = f"{warnungen} Warnung(en), {hinweise} Hinweis(e)."
        titel = QLabel(kopf)
        titel.setWordWrap(True)
        aufbau.addWidget(titel)

        baum = QTreeWidget()
        baum.setHeaderLabels(["Schwere", "Quelle", "Meldung"])
        baum.setColumnWidth(0, 90)
        baum.setColumnWidth(1, 70)
        for befund in bericht.befunde:
            schwere = befund.schwere.name if hasattr(befund.schwere, "name") else str(befund.schwere)
            eintrag = QTreeWidgetItem([schwere, befund.code, befund.text])
            farbe = FARBEN.get(schwere.upper())
            if farbe:
                from PySide6.QtGui import QBrush, QColor

                eintrag.setForeground(0, QBrush(QColor(farbe)))
            baum.addTopLevelItem(eintrag)
        baum.resizeColumnToContents(2)
        aufbau.addWidget(baum)

        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        knoepfe.rejected.connect(self.reject)
        knoepfe.accepted.connect(self.accept)
        aufbau.addWidget(knoepfe)
        aufbau.addWidget(knoepfe)