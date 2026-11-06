"""Schrittleiste: sechs Schritte, Freigaben und Veraltet-Hinweis (U-1, Z-7).

Das Widget kennt keine Fachlogik. Es zeigt an, was freigaben_fuer()
liefert, und meldet per Signal, welchen Schritt der Nutzer waehlen will.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..app.zustand import SCHRITTNAMEN, Freigabe, Schritt


class Schrittleiste(QWidget):
    """Waagerechte Leiste mit einem Knopf je Schritt."""

    #: Der Nutzer hat einen erlaubten Schritt gewaehlt.
    schritt_gewaehlt = Signal(object)  # Schritt

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._knoepfe: dict[Schritt, QPushButton] = {}
        self._aktiver: Schritt = Schritt.AUFBAU

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(8, 8, 8, 4)
        aussen.setSpacing(4)

        leiste = QHBoxLayout()
        leiste.setSpacing(0)
        aussen.addLayout(leiste)

        gruppe = QButtonGroup(self)
        gruppe.setExclusive(True)

        schritte = list(Schritt)
        for nummer, schritt in enumerate(schritte, start=1):
            knopf = QPushButton(f"{nummer}. {SCHRITTNAMEN[schritt]}")
            knopf.setCheckable(True)
            knopf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            knopf.clicked.connect(lambda _=False, s=schritt: self._auf_klick(s))
            self._knoepfe[schritt] = knopf
            gruppe.addButton(knopf)
            leiste.addWidget(knopf)
            if schritt is not schritte[-1]:
                pfeil = QLabel("›")
                pfeil.setStyleSheet("color: palette(mid); padding: 0 4px;")
                leiste.addWidget(pfeil)

        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setStyleSheet("color: palette(mid); padding: 2px 4px;")
        aussen.addWidget(self._hinweis)

        self._knoepfe[Schritt.AUFBAU].setChecked(True)

    # ------------------------------------------------------------------

    def _auf_klick(self, schritt: Schritt) -> None:
        knopf = self._knoepfe[schritt]
        if not knopf.isEnabled():
            return
        self._aktiver = schritt
        self.schritt_gewaehlt.emit(schritt)

    def aktiver_schritt(self) -> Schritt:
        return self._aktiver

    def schritt_setzen(self, schritt: Schritt) -> None:
        """Markiert einen Schritt, ohne das Signal auszuloesen."""
        self._aktiver = schritt
        self._knoepfe[schritt].setChecked(True)

    def freigaben_anwenden(
        self, freigaben: dict[Schritt, Freigabe], veraltet: bool = False
    ) -> None:
        """Aktiviert oder sperrt die Knoepfe und zeigt den Grund als Tooltip."""
        for schritt, knopf in self._knoepfe.items():
            freigabe = freigaben.get(schritt, Freigabe(True))
            knopf.setEnabled(freigabe.erlaubt)
            knopf.setToolTip(freigabe.grund)

        aktiv = freigaben.get(self._aktiver, Freigabe(True))
        if veraltet:
            self._hinweis.setText(
                "Die Ergebnisse sind veraltet, weil die Anlage geaendert wurde. "
                "Bitte NWA erneut bestaetigen."
            )
        elif not aktiv.erlaubt and aktiv.grund:
            self._hinweis.setText(aktiv.grund)
        else:
            self._hinweis.setText("")


class Trennlinie(QFrame):
    """Duenne waagerechte Linie unter der Schrittleiste."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)