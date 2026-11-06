"""Gezeichnete Verbindung zwischen zwei Ports.

Die Linie liest ihre Endpunkte bei jedem Neuzeichnen aus den beteiligten
Bauteil-Items, damit sie beim Verschieben folgt. Bahn-Verbindungen werden
in der Bahnfarbe gezeichnet, andere Arten in einem neutralen Grau.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsItem

from ..core.modell import Anlage

FARBE_NEUTRAL = QColor("#607D8B")
FARBE_AUSWAHL = QColor("#1E88E5")
BREITE = 2.0


class VerbindungItem(QGraphicsLineItem):
    def __init__(
        self,
        verbindung_id: str,
        anlage: Anlage,
        items: dict,
        bahnfarbe,
    ) -> None:
        super().__init__()
        self.verbindung_id = verbindung_id
        self._anlage = anlage
        self._items = items
        self._bahnfarbe = bahnfarbe  # Callable: bahn_id -> farbe oder None
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(0)  # unter den Bauteilen
        self.aktualisieren()

    def _verbindung(self):
        return self._anlage.verbindungen[self.verbindung_id]

    def _farbe(self) -> QColor:
        v = self._verbindung()
        if v.art == "bahn" and v.bahn:
            farbe = self._bahnfarbe(v.bahn)
            if farbe:
                return QColor(farbe)
        return FARBE_NEUTRAL

    def aktualisieren(self) -> None:
        """Setzt die Linie neu zwischen die aktuellen Portpositionen."""
        v = self._verbindung()
        von_item = self._items.get(v.von)
        nach_item = self._items.get(v.nach)
        if von_item is None or nach_item is None:
            return

        von_ports = von_item.port_positionen()
        nach_ports = nach_item.port_positionen()
        p_von = von_ports.get(v.von_port)
        p_nach = nach_ports.get(v.nach_port)
        if p_von is None or p_nach is None:
            return

        self.setLine(p_von[0], p_von[1], p_nach[0], p_nach[1])
        self._stift_setzen()

    def _stift_setzen(self) -> None:
        if self.isSelected():
            stift = QPen(FARBE_AUSWAHL, BREITE + 1.0)
        else:
            stift = QPen(self._farbe(), BREITE)
        stift.setCapStyle(Qt.RoundCap)
        self.setPen(stift)

    def paint(self, maler, option, widget=None):
        self._stift_setzen()
        super().paint(maler, option, widget)