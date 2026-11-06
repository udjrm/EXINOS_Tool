"""Startdialog: fragt beim Oeffnen der UI nach dem Anlagennamen.

Der Name wandert in Anlage.name und bildet spaeter den Ordnernamen beim
Export (NAME_DDMMYYYY_HHMM).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QWidget,
)


class StartDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, vorschlag: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Neue Anlage")
        self.setMinimumWidth(360)

        aufbau = QFormLayout(self)
        hinweis = QLabel(
            "Wie soll die Anlage heissen? Der Name wird fuer den "
            "Export-Ordner verwendet."
        )
        hinweis.setWordWrap(True)
        aufbau.addRow(hinweis)

        self._name = QLineEdit(vorschlag)
        self._name.setPlaceholderText("z. B. EXINOS")
        aufbau.addRow("Anlagenname:", self._name)

        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        aufbau.addRow(knoepfe)

        # OK erst aktiv, wenn etwas eingegeben wurde.
        self._ok = knoepfe.button(QDialogButtonBox.Ok)
        self._ok.setEnabled(bool(vorschlag.strip()))
        self._name.textChanged.connect(
            lambda t: self._ok.setEnabled(bool(t.strip()))
        )

    def anlagenname(self) -> str:
        return self._name.text().strip()