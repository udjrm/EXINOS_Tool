"""Dialog zum Anlegen und Aendern einer Materialbahn.

Der Materialpfad kommt aus einer festen Auswahlliste (An/Ka/El/Se), weil
die NWA mit diesen Kuerzeln arbeitet. Die Farbe wird aus dem Pfad
vorbelegt und ist aenderbar.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .materialpfade import MATERIALPFADE, anzeige, pfad_farbe


class BahnDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        bahn_id: str = "",
        bezeichnung: str = "",
        kuerzel: str = "An",
        farbe: str = "",
        id_sperren: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Materialbahn")
        self._farbe = farbe or pfad_farbe(kuerzel)

        aufbau = QFormLayout(self)

        self._id = QLineEdit(bahn_id)
        self._id.setReadOnly(id_sperren)
        aufbau.addRow("Bahn-id:", self._id)

        self._bezeichnung = QLineEdit(bezeichnung)
        aufbau.addRow("Name:", self._bezeichnung)

        self._pfad = QComboBox()
        for k in MATERIALPFADE:
            self._pfad.addItem(anzeige(k), k)
        self._pfad.setCurrentIndex(max(0, list(MATERIALPFADE).index(kuerzel)) if kuerzel in MATERIALPFADE else 0)
        self._pfad.currentIndexChanged.connect(self._pfad_gewechselt)
        aufbau.addRow("Materialpfad:", self._pfad)

        self._farb_knopf = QPushButton()
        self._farb_knopf.clicked.connect(self._farbe_waehlen)
        self._farbe_anzeigen()
        aufbau.addRow("Farbe:", self._farb_knopf)

        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        aufbau.addRow(knoepfe)

    # ------------------------------------------------------------------

    def _pfad_gewechselt(self) -> None:
        """Belegt die Farbe aus dem Pfad vor, solange der Nutzer sie nicht selbst gesetzt hat."""
        self._farbe = pfad_farbe(self.kuerzel())
        self._farbe_anzeigen()

    def _farbe_waehlen(self) -> None:
        gewaehlt = QColorDialog.getColor(QColor(self._farbe), self, "Bahnfarbe waehlen")
        if gewaehlt.isValid():
            self._farbe = gewaehlt.name()
            self._farbe_anzeigen()

    def _farbe_anzeigen(self) -> None:
        self._farb_knopf.setText(self._farbe)
        self._farb_knopf.setStyleSheet(
            f"background-color: {self._farbe}; color: white; padding: 4px;"
        )

    # ------------------------------------------------------------------
    # Ergebnis

    def bahn_id(self) -> str:
        return self._id.text().strip()

    def bezeichnung(self) -> str:
        return self._bezeichnung.text().strip()

    def kuerzel(self) -> str:
        return self._pfad.currentData()

    def farbe(self) -> str:
        return self._farbe