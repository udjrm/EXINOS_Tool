"""Leinwand: Drag & Drop, Mehrfachauswahl, Verbindungen ziehen (Abnahme 2).

Maus-Logik:
- Druck direkt auf einem Port  -> Verbindung ziehen (Gummiband).
- Druck sonst                  -> normale Qt-Auswahl: Rubberband-Rechteck
                                  aufziehen, Shift-Klick erweitert die Auswahl.

Das Kontextmenue wirkt auf die gesamte Auswahl, wenn das angeklickte
Bauteil darin enthalten ist, sonst nur auf das angeklickte Bauteil.
Sammel-Loeschen und -Duplizieren laufen als ein Undo-Schritt.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

from ..app.controller import Controller
from ..core.darstellung import Darstellung
from ..core.modell import Bauteil
from .bauteil_item import BauteilItem
from .bibliothek import MIME_TYP
from .verbindung_item import VerbindungItem

FARBE_GUMMIBAND_OK = QColor("#43A047")
FARBE_GUMMIBAND_NEIN = QColor("#E53935")


class LeinwandSignale(QObject):
    geaendert = Signal()


class Leinwand(QGraphicsScene):
    def __init__(
        self, controller: Controller, darstellung: Darstellung, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.darstellung = darstellung
        self.signale = LeinwandSignale()
        self._items: dict[str, BauteilItem] = {}
        self._verbindungen: dict[str, VerbindungItem] = {}
        self._aktive_bahn: str = ""

        self._ziehen_von: tuple[str, str] | None = None
        self._gummiband: QGraphicsLineItem | None = None

        self.setSceneRect(-2000, -2000, 6000, 6000)
        self.neu_aufbauen()

    # ------------------------------------------------------------------
    # Aktive Bahn

    def aktive_bahn_setzen(self, bahn_id: str) -> None:
        self._aktive_bahn = bahn_id or ""

    def _bahnfarbe(self, bahn_id: str):
        bahn = self.controller.anlage.bahnen.get(bahn_id)
        return bahn.farbe if bahn else None

    # ------------------------------------------------------------------
    # Aufbau

    def neu_aufbauen(self) -> None:
        self.clear()
        self._items.clear()
        self._verbindungen.clear()
        for bauteil_id in self.controller.anlage.bauteile:
            item = BauteilItem(bauteil_id, self.controller.anlage, self.darstellung)
            self.addItem(item)
            self._items[bauteil_id] = item
        for verbindung_id in self.controller.anlage.verbindungen:
            self._verbindung_hinzufuegen(verbindung_id)

    def _verbindung_hinzufuegen(self, verbindung_id: str) -> None:
        item = VerbindungItem(
            verbindung_id, self.controller.anlage, self._items, self._bahnfarbe
        )
        self.addItem(item)
        self._verbindungen[verbindung_id] = item

    def aktualisieren(self) -> None:
        vorhanden = set(self._items)
        soll = set(self.controller.anlage.bauteile)
        for entfernt in vorhanden - soll:
            self.removeItem(self._items.pop(entfernt))
        for neu in soll - vorhanden:
            item = BauteilItem(neu, self.controller.anlage, self.darstellung)
            self.addItem(item)
            self._items[neu] = item
        for item in self._items.values():
            item.aus_modell_uebernehmen()

        v_vorhanden = set(self._verbindungen)
        v_soll = set(self.controller.anlage.verbindungen)
        for entfernt in v_vorhanden - v_soll:
            self.removeItem(self._verbindungen.pop(entfernt))
        for neu in v_soll - v_vorhanden:
            self._verbindung_hinzufuegen(neu)
        for item in self._verbindungen.values():
            item.aktualisieren()

    def verbindungen_neu_zeichnen(self) -> None:
        for item in self._verbindungen.values():
            item.aktualisieren()

    # ------------------------------------------------------------------
    # Drag & Drop aus der Bibliothek

    def dragEnterEvent(self, ereignis) -> None:  # noqa: N802
        if ereignis.mimeData().hasFormat(MIME_TYP):
            ereignis.acceptProposedAction()
        else:
            super().dragEnterEvent(ereignis)

    def dragMoveEvent(self, ereignis) -> None:  # noqa: N802
        if ereignis.mimeData().hasFormat(MIME_TYP):
            ereignis.acceptProposedAction()
        else:
            super().dragMoveEvent(ereignis)

    def dropEvent(self, ereignis) -> None:  # noqa: N802
        nutzdaten = ereignis.mimeData()
        if not nutzdaten.hasFormat(MIME_TYP):
            super().dropEvent(ereignis)
            return
        typ = bytes(nutzdaten.data(MIME_TYP)).decode("utf-8")
        punkt = ereignis.scenePos()
        bauteil = Bauteil(
            id=self.controller.anlage.freie_id(typ), typ=typ, x=punkt.x(), y=punkt.y()
        )
        self.controller.bauteil_anlegen(bauteil)
        self.aktualisieren()
        self.signale.geaendert.emit()
        ereignis.acceptProposedAction()

    # ------------------------------------------------------------------
    # Maus: Verbindung ziehen ODER Auswahl zulassen

    def mousePressEvent(self, ereignis) -> None:  # noqa: N802
        if ereignis.button() == Qt.LeftButton:
            treffer = self._port_unter_streng(ereignis.scenePos())
            if treffer is not None:
                # Direkt auf einem Port: Verbindung ziehen.
                self._ziehen_von = treffer
                start = self._items[treffer[0]].port_positionen()[treffer[1]]
                self._gummiband = QGraphicsLineItem(
                    start[0], start[1], start[0], start[1]
                )
                self._gummiband.setPen(QPen(FARBE_GUMMIBAND_OK, 2.0, Qt.DashLine))
                self._gummiband.setZValue(5)
                self.addItem(self._gummiband)
                ereignis.accept()
                return

            # Shift-Klick auf ein Bauteil: Auswahl erweitern statt ersetzen.
            if ereignis.modifiers() & Qt.ShiftModifier:
                item = self._bauteil_item_unter(ereignis.scenePos())
                if item is not None:
                    item.setSelected(not item.isSelected())
                    ereignis.accept()
                    return

        super().mousePressEvent(ereignis)

    def mouseMoveEvent(self, ereignis) -> None:  # noqa: N802
        if self._ziehen_von is not None and self._gummiband is not None:
            start = self._items[self._ziehen_von[0]].port_positionen()[self._ziehen_von[1]]
            ende = ereignis.scenePos()
            self._gummiband.setLine(start[0], start[1], ende.x(), ende.y())

            ziel = self._port_unter_locker(ende)
            ok = False
            if ziel is not None and ziel[0] != self._ziehen_von[0]:
                ok, _grund, _o = self.controller.verbindung_moeglich(
                    self._ziehen_von[0], self._ziehen_von[1], ziel[0], ziel[1]
                )
            farbe = FARBE_GUMMIBAND_OK if ok else FARBE_GUMMIBAND_NEIN
            self._gummiband.setPen(QPen(farbe, 2.0, Qt.DashLine))
            ereignis.accept()
            return
        super().mouseMoveEvent(ereignis)

    def mouseReleaseEvent(self, ereignis) -> None:  # noqa: N802
        if self._ziehen_von is not None:
            ziel = self._port_unter_locker(ereignis.scenePos())
            start = self._ziehen_von
            self._ziehen_beenden()
            if ziel is not None and ziel[0] != start[0]:
                self._verbindung_anlegen(start, ziel)
            ereignis.accept()
            return
        super().mouseReleaseEvent(ereignis)
        # Nach einem Verschieben die Linien nachziehen.
        self.verbindungen_neu_zeichnen()

    def _ziehen_beenden(self) -> None:
        if self._gummiband is not None:
            self.removeItem(self._gummiband)
            self._gummiband = None
        self._ziehen_von = None

    # ------------------------------------------------------------------
    # Verbindung anlegen

    def _verbindung_anlegen(self, start, ziel) -> None:
        a_bauteil, a_port = start
        b_bauteil, b_port = ziel

        erlaubt, grund, orientierung = self.controller.verbindung_moeglich(
            a_bauteil, a_port, b_bauteil, b_port
        )
        if not erlaubt:
            QMessageBox.information(None, "Verbindung nicht moeglich", grund)
            return

        von, von_port, _nach, _nach_port = orientierung
        art = self.controller.pool.port(
            self.controller.anlage.bauteile[von].typ, von_port
        ).art

        bahn = ""
        if art == "bahn":
            bahn = self._bahn_bestimmen()
            if bahn is None:
                return

        ok, ergebnis = self.controller.verbindung_ziehen(
            a_bauteil, a_port, b_bauteil, b_port, bahn
        )
        if not ok:
            QMessageBox.information(None, "Verbindung nicht moeglich", ergebnis)
            return
        self.aktualisieren()
        self.signale.geaendert.emit()

    def _bahn_bestimmen(self) -> str | None:
        bahnen = self.controller.bahnen()
        if not bahnen:
            QMessageBox.warning(
                None,
                "Keine Bahn vorhanden",
                "Lege zuerst oben eine Materialbahn an, bevor du eine "
                "Bahn-Verbindung ziehst.",
            )
            return None
        namen = [f"{b.id} ({b.kuerzel}) – {b.bezeichnung}" for b in bahnen]
        ids = [b.id for b in bahnen]
        vorgabe = ids.index(self._aktive_bahn) if self._aktive_bahn in ids else 0
        auswahl, ok = QInputDialog.getItem(
            None, "Bahn waehlen", "Materialbahn:", namen, vorgabe, editable=False
        )
        if not ok:
            return None
        return ids[namen.index(auswahl)]

    # ------------------------------------------------------------------
    # Port-Treffer: streng (nur direkt auf dem Port) und locker (mit Toleranz)

    def _port_unter_streng(self, szenen_punkt) -> tuple[str, str] | None:
        """Nur wenn der Punkt wirklich auf einem Portkreis liegt."""
        for item in self.items(szenen_punkt):
            if isinstance(item, BauteilItem):
                port = item.port_unter(szenen_punkt, toleranz=0.0)
                if port is not None:
                    return (item.bauteil_id, port)
        return None

    def _port_unter_locker(self, szenen_punkt) -> tuple[str, str] | None:
        """Mit Toleranz, damit das Ziel leichter zu treffen ist."""
        for bauteil_id, item in self._items.items():
            port = item.port_unter(szenen_punkt, toleranz=10.0)
            if port is not None:
                return (bauteil_id, port)
        return None

    # ------------------------------------------------------------------
    # Kontextmenue

    def contextMenuEvent(self, ereignis: QGraphicsSceneContextMenuEvent) -> None:  # noqa: N802
        verbindung = self._verbindung_unter(ereignis.scenePos())
        if verbindung is not None:
            self._verbindung_menue(verbindung, ereignis)
            return

        item = self._bauteil_item_unter(ereignis.scenePos())
        if item is None:
            super().contextMenuEvent(ereignis)
            return

        # Wenn das angeklickte Bauteil zur Auswahl gehoert, auf die ganze
        # Auswahl wirken; sonst nur auf dieses eine.
        ausgewaehlt = self._ausgewaehlte_ids()
        if item.bauteil_id in ausgewaehlt and len(ausgewaehlt) > 1:
            ziel_ids = ausgewaehlt
        else:
            ziel_ids = [item.bauteil_id]

        menue = QMenu()
        if len(ziel_ids) > 1:
            aktion_umbenennen = None
            aktion_duplizieren = menue.addAction(f"{len(ziel_ids)} duplizieren")
            menue.addSeparator()
            aktion_loeschen = menue.addAction(f"{len(ziel_ids)} löschen")
        else:
            aktion_umbenennen = menue.addAction("Umbenennen …")
            aktion_duplizieren = menue.addAction("Duplizieren")
            menue.addSeparator()
            aktion_loeschen = menue.addAction("Löschen")

        gewaehlt = menue.exec(ereignis.screenPos())
        if gewaehlt is None:
            return
        if gewaehlt == aktion_loeschen:
            self._mehrere_loeschen(ziel_ids)
        elif gewaehlt == aktion_duplizieren:
            self._mehrere_duplizieren(ziel_ids)
        elif aktion_umbenennen is not None and gewaehlt == aktion_umbenennen:
            self._umbenennen(ziel_ids[0], ereignis)

    def _ausgewaehlte_ids(self) -> list[str]:
        return [
            item.bauteil_id
            for item in self.selectedItems()
            if isinstance(item, BauteilItem)
        ]

    def _mehrere_loeschen(self, ids: list[str]) -> None:
        ids_menge = set(ids)
        # Jede betroffene Verbindung nur einmal zaehlen, auch wenn beide
        # Endbauteile zur Auswahl gehoeren.
        betroffene_kanten = {
            v.id
            for v in self.controller.anlage.verbindungen.values()
            if v.von in ids_menge or v.nach in ids_menge
        }
        anzahl_kanten = len(betroffene_kanten)

        if anzahl_kanten == 0:
            frage = f"{len(ids)} Bauteil(e) löschen?"
        else:
            frage = (
                f"{len(ids)} Bauteil(e) und {anzahl_kanten} Verbindung(en) löschen?"
            )
        antwort = QMessageBox.question(None, "Löschen", frage)
        if antwort != QMessageBox.Yes:
            return
        self.controller.bauteile_entfernen(ids)
        self.aktualisieren()
        self.signale.geaendert.emit()

    def _mehrere_duplizieren(self, ids: list[str]) -> None:
        neue = self.controller.bauteile_duplizieren(ids)
        self.aktualisieren()
        # Die neuen Kopien gleich auswaehlen.
        self.clearSelection()
        for neu in neue:
            item = self._items.get(neu)
            if item is not None:
                item.setSelected(True)
        self.signale.geaendert.emit()

    # ------------------------------------------------------------------
    # Verbindungs-Kontextmenue

    def _verbindung_menue(self, verbindung_id: str, ereignis) -> None:
        v = self.controller.anlage.verbindungen[verbindung_id]
        menue = QMenu()
        aktion_bahn = menue.addAction("Bahn aendern …") if v.art == "bahn" else None
        aktion_loeschen = menue.addAction("Verbindung löschen")

        gewaehlt = menue.exec(ereignis.screenPos())
        if gewaehlt == aktion_loeschen:
            self.controller.verbindung_entfernen(verbindung_id)
            self.aktualisieren()
            self.signale.geaendert.emit()
        elif aktion_bahn is not None and gewaehlt == aktion_bahn:
            bahn = self._bahn_bestimmen()
            if bahn is not None:
                self.controller.verbindung_bahn_setzen(verbindung_id, bahn)
                self.aktualisieren()
                self.signale.geaendert.emit()

    def _verbindung_unter(self, punkt) -> str | None:
        for kandidat in self.items(punkt):
            if isinstance(kandidat, VerbindungItem):
                return kandidat.verbindung_id
        return None

    def _bauteil_item_unter(self, punkt) -> BauteilItem | None:
        for kandidat in self.items(punkt):
            if isinstance(kandidat, BauteilItem):
                return kandidat
        return None

    def _umbenennen(self, bauteil_id: str, ereignis) -> None:
        neu, ok = QInputDialog.getText(
            None, "Bauteil umbenennen", "Neue id:", text=bauteil_id
        )
        if not ok or not neu or neu == bauteil_id:
            return
        try:
            self.controller.bauteil_umbenennen(bauteil_id, neu)
        except Exception as fehler:
            QMessageBox.critical(None, "Umbenennen nicht moeglich", str(fehler))
            return
        self.aktualisieren()
        self.signale.geaendert.emit()

    # ------------------------------------------------------------------
    # Rueckmeldung beim Verschieben

    def bauteil_verschoben(self, bauteil_id: str, neu: tuple[float, float]) -> None:
        self.controller.bauteil_verschieben(bauteil_id, neu)
        self.verbindungen_neu_zeichnen()
        self.signale.geaendert.emit()


class LeinwandAnsicht(QGraphicsView):
    def __init__(self, szene: Leinwand, parent: QWidget | None = None) -> None:
        super().__init__(szene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        # Rubberband ist wieder aktiv; das Port-Ziehen faengt den Klick
        # bereits in der Szene ab, bevor das Rubberband startet.
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, ereignis) -> None:  # noqa: N802
        if ereignis.modifiers() & Qt.ControlModifier:
            faktor = 1.15 if ereignis.angleDelta().y() > 0 else 1 / 1.15
            self.scale(faktor, faktor)
        else:
            super().wheelEvent(ereignis)

    def keyPressEvent(self, ereignis) -> None:  # noqa: N802
        if ereignis.key() == Qt.Key_Delete:
            szene = self.scene()
            ids = [
                item.bauteil_id
                for item in szene.selectedItems()
                if isinstance(item, BauteilItem)
            ]
            if ids:
                szene._mehrere_loeschen(ids)
            return
        super().keyPressEvent(ereignis)