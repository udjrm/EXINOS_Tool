"""Grafisches Bauteil auf der Leinwand.

Zeichnet das SVG-Symbol des Typs, darunter die Beschriftung und am Rand
die Ports. Fehlt ein Symbol, wird ein schlichtes Ersatzrechteck gezeichnet.
Verschieben meldet das Item am Ende der Mausbewegung an die Szene.

boundingRect() ist um den Portradius vergroessert, damit beim Verschieben
keine Zeichenreste der ueberstehenden Ports stehen bleiben.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ..core.darstellung import Darstellung
from ..core.modell import Anlage

PORT_RADIUS = 5.0
RAND = PORT_RADIUS + 2.0
FARBE_RAHMEN = QColor("#37474F")
FARBE_FUELLUNG = QColor("#ECEFF1")
FARBE_AUSWAHL = QColor("#1E88E5")
FARBE_PORT_EIN = QColor("#43A047")
FARBE_PORT_AUS = QColor("#E53935")


class BauteilItem(QGraphicsRectItem):
    def __init__(self, bauteil_id: str, anlage: Anlage, darstellung: Darstellung) -> None:
        self._anlage = anlage
        self._darstellung = darstellung
        self.bauteil_id = bauteil_id

        form = darstellung.fuer(self._bauteil().typ)
        super().__init__(0, 0, form.breite, form.hoehe)

        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPen(QPen(FARBE_RAHMEN, 1.5))
        self.setBrush(QBrush(FARBE_FUELLUNG))
        self.setZValue(1)

        # SVG-Symbol laden, falls vorhanden.
        self._renderer: QSvgRenderer | None = self._renderer_laden()

        self._beschriftung = QGraphicsSimpleTextItem(self.bauteil_id, self)
        schrift = QFont()
        schrift.setPointSizeF(8.0)
        self._beschriftung.setFont(schrift)
        self._beschriftung_setzen()

        self._letzte_position = self.pos()
        self.aus_modell_uebernehmen()

    # ------------------------------------------------------------------

    def _bauteil(self):
        return self._anlage.bauteile[self.bauteil_id]

    def _renderer_laden(self) -> QSvgRenderer | None:
        pfad = self._darstellung.symbol_pfad(self._bauteil().typ)
        if pfad is None:
            return None
        renderer = QSvgRenderer(str(pfad))
        return renderer if renderer.isValid() else None

    def _beschriftung_setzen(self) -> None:
        """Beschriftung unter das Symbol setzen, zentriert."""
        rechteck = self.rect()
        text = self._beschriftung.boundingRect()
        self._beschriftung.setPos(
            (rechteck.width() - text.width()) / 2,
            rechteck.height() + 2,
        )

    def aus_modell_uebernehmen(self) -> None:
        bauteil = self._bauteil()
        self.setPos(bauteil.x, bauteil.y)
        self._letzte_position = self.pos()
        self._beschriftung.setText(bauteil.id)
        self._beschriftung_setzen()

    # ------------------------------------------------------------------
    # Zeichenbereich inklusive ueberstehender Ports

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self.rect().adjusted(-RAND, -RAND, RAND, RAND)

    # ------------------------------------------------------------------
    # Ports

    def port_positionen(self) -> dict[str, tuple[float, float]]:
        bauteil = self._bauteil()
        form = self._darstellung.fuer(bauteil.typ)
        ergebnis: dict[str, tuple[float, float]] = {}
        for name in form.ports:
            x, y = self._darstellung.position(
                form.typ, name, bauteil.drehung, bauteil.gespiegelt
            )
            szene = self.mapToScene(x, y)
            ergebnis[name] = (szene.x(), szene.y())
        return ergebnis

    def port_unter(self, szenen_punkt, toleranz: float = 8.0) -> str | None:
        for name, (x, y) in self.port_positionen().items():
            dx = szenen_punkt.x() - x
            dy = szenen_punkt.y() - y
            if (dx * dx + dy * dy) ** 0.5 <= toleranz + PORT_RADIUS:
                return name
        return None

    # ------------------------------------------------------------------

    def paint(self, maler, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        rechteck = self.rect()

        if self._renderer is not None:
            # Heller Hintergrund, dann das Symbol, dann der Auswahlrahmen.
            maler.setPen(Qt.NoPen)
            maler.setBrush(QBrush(FARBE_FUELLUNG))
            maler.drawRoundedRect(rechteck, 3, 3)
            self._renderer.render(maler, rechteck)
            if self.isSelected():
                maler.setPen(QPen(FARBE_AUSWAHL, 2.0))
                maler.setBrush(Qt.NoBrush)
                maler.drawRoundedRect(rechteck, 3, 3)
        else:
            # Ersatzrechteck wie bisher.
            if self.isSelected():
                self.setPen(QPen(FARBE_AUSWAHL, 2.0))
            else:
                self.setPen(QPen(FARBE_RAHMEN, 1.5))
            super().paint(maler, option, widget)

        # Ports immer obendrauf.
        form = self._darstellung.fuer(self._bauteil().typ)
        bauteil = self._bauteil()
        for name in form.ports:
            x, y = self._darstellung.position(
                form.typ, name, bauteil.drehung, bauteil.gespiegelt
            )
            maler.setBrush(QBrush(FARBE_PORT_EIN if "ein" in name else FARBE_PORT_AUS))
            maler.setPen(QPen(FARBE_RAHMEN, 0.8))
            maler.drawEllipse(
                QRectF(x - PORT_RADIUS, y - PORT_RADIUS, 2 * PORT_RADIUS, 2 * PORT_RADIUS)
            )

    # ------------------------------------------------------------------

    def mouseReleaseEvent(self, ereignis) -> None:  # noqa: N802
        super().mouseReleaseEvent(ereignis)
        neu = self.pos()
        if neu != self._letzte_position:
            szene = self.scene()
            if szene is not None and hasattr(szene, "bauteil_verschoben"):
                szene.bauteil_verschoben(self.bauteil_id, (neu.x(), neu.y()))
            self._letzte_position = neu