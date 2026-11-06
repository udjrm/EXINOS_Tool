"""Rueckgaengig und Wiederholen (E-4, E-5), ohne Qt.

Jede Aenderung am Modell laeuft ueber einen Befehl. Der Befehlsstapel ist
die einzige Stelle, die Aenderungen rueckgaengig macht. Die Qt-Schicht
spiegelt spaeter nur den Zustand; QUndoStack wird ein duenner Adapter.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager

from ..core.modell import Anlage, Bauteil, Verbindung

GRENZE_STANDARD = 100


class Befehl:
    """Basisklasse. ausfuehren() gilt auch fuer das Wiederholen."""

    text = "Änderung"

    def ausfuehren(self, anlage: Anlage) -> None:
        raise NotImplementedError

    def rueckgaengig(self, anlage: Anlage) -> None:
        raise NotImplementedError

    def verschmelzen(self, andere: Befehl) -> bool:
        """Nimmt einen unmittelbar nachfolgenden Befehl auf (z. B. Ziehen per Maus)."""
        return False


class BauteilHinzufuegen(Befehl):
    def __init__(self, bauteil: Bauteil) -> None:
        self._bauteil = copy.deepcopy(bauteil)
        self.text = f"Bauteil {bauteil.id} hinzufügen"

    def ausfuehren(self, anlage: Anlage) -> None:
        anlage.hinzufuegen(copy.deepcopy(self._bauteil))

    def rueckgaengig(self, anlage: Anlage) -> None:
        anlage.entferne_bauteil(self._bauteil.id)

class BauteilDuplizieren(Befehl):
    """Kopiert ein Bauteil mit neuer id und leichtem Versatz (ohne Verbindungen)."""

    def __init__(self, quell_id: str, neue_id: str, versatz: tuple[float, float] = (30.0, 30.0)) -> None:
        self.quell_id = quell_id
        self.neue_id = neue_id
        self._versatz = versatz
        self.text = f"Bauteil {quell_id} duplizieren"

    def ausfuehren(self, anlage: Anlage) -> None:
        import copy

        if self.quell_id not in anlage.bauteile:
            raise KeyError(f"Bauteil {self.quell_id!r} ist nicht vorhanden.")
        kopie = copy.deepcopy(anlage.bauteile[self.quell_id])
        kopie.id = self.neue_id
        kopie.x = kopie.x + self._versatz[0]
        kopie.y = kopie.y + self._versatz[1]
        anlage.hinzufuegen(kopie)

    def rueckgaengig(self, anlage: Anlage) -> None:
        anlage.entferne_bauteil(self.neue_id)


class BauteilEntfernen(Befehl):
    def __init__(self, bauteil_id: str) -> None:
        self.bauteil_id = bauteil_id
        self.text = f"Bauteil {bauteil_id} entfernen"
        self._gesichert: tuple[Bauteil, list[Verbindung]] | None = None

    def ausfuehren(self, anlage: Anlage) -> None:
        if self.bauteil_id not in anlage.bauteile:
            raise KeyError(f"Bauteil {self.bauteil_id!r} ist nicht vorhanden.")
        bauteil = copy.deepcopy(anlage.bauteile[self.bauteil_id])
        verbindungen = [copy.deepcopy(v) for v in anlage.kanten_von(self.bauteil_id)]
        anlage.entferne_bauteil(self.bauteil_id)
        self._gesichert = (bauteil, verbindungen)

    def rueckgaengig(self, anlage: Anlage) -> None:
        if self._gesichert is None:
            return
        bauteil, verbindungen = self._gesichert
        anlage.hinzufuegen(copy.deepcopy(bauteil))
        for verbindung in verbindungen:
            anlage.verbinden(copy.deepcopy(verbindung))


class VerbindungHinzufuegen(Befehl):
    def __init__(self, verbindung: Verbindung) -> None:
        self._verbindung = copy.deepcopy(verbindung)
        self.text = f"Verbindung {verbindung.id} anlegen"

    def ausfuehren(self, anlage: Anlage) -> None:
        anlage.verbinden(copy.deepcopy(self._verbindung))

    def rueckgaengig(self, anlage: Anlage) -> None:
        anlage.verbindungen.pop(self._verbindung.id, None)


class VerbindungEntfernen(Befehl):
    def __init__(self, verbindung_id: str) -> None:
        self.verbindung_id = verbindung_id
        self.text = f"Verbindung {verbindung_id} löschen"
        self._gesichert: Verbindung | None = None

    def ausfuehren(self, anlage: Anlage) -> None:
        if self.verbindung_id not in anlage.verbindungen:
            raise KeyError(f"Verbindung {self.verbindung_id!r} ist nicht vorhanden.")
        self._gesichert = copy.deepcopy(anlage.verbindungen[self.verbindung_id])
        anlage.verbindungen.pop(self.verbindung_id)

    def rueckgaengig(self, anlage: Anlage) -> None:
        if self._gesichert is not None:
            anlage.verbinden(copy.deepcopy(self._gesichert))


class BauteilVerschieben(Befehl):
    """Verschieben per Maus. Aufeinanderfolgende Schritte verschmelzen zu einem."""

    def __init__(self, bauteil_id: str, neu: tuple[float, float]) -> None:
        self.bauteil_id = bauteil_id
        self.neu = (float(neu[0]), float(neu[1]))
        self.text = f"Bauteil {bauteil_id} verschieben"
        self._alt: tuple[float, float] | None = None

    def ausfuehren(self, anlage: Anlage) -> None:
        bauteil = anlage.bauteile[self.bauteil_id]
        if self._alt is None:
            self._alt = (bauteil.x, bauteil.y)
        bauteil.x, bauteil.y = self.neu

    def rueckgaengig(self, anlage: Anlage) -> None:
        if self._alt is not None:
            bauteil = anlage.bauteile[self.bauteil_id]
            bauteil.x, bauteil.y = self._alt

    def verschmelzen(self, andere: Befehl) -> bool:
        if isinstance(andere, BauteilVerschieben) and andere.bauteil_id == self.bauteil_id:
            self.neu = andere.neu
            return True
        return False


class BauteilUmbenennen(Befehl):
    def __init__(self, alt: str, neu: str) -> None:
        self.alt = alt
        self.neu = neu
        self.text = f"{alt} umbenennen in {neu}"

    def ausfuehren(self, anlage: Anlage) -> None:
        anlage.umbenennen(self.alt, self.neu)

    def rueckgaengig(self, anlage: Anlage) -> None:
        anlage.umbenennen(self.neu, self.alt)


class EigenschaftSetzen(Befehl):
    """Setzt ein Feld eines Bauteils oder einer Verbindung, z. B. die Bahn (W-2)."""

    def __init__(self, art: str, objekt_id: str, feld: str, wert: object) -> None:
        if art not in ("bauteil", "verbindung"):
            raise ValueError("art muss 'bauteil' oder 'verbindung' sein.")
        self.art = art
        self.objekt_id = objekt_id
        self.feld = feld
        self.wert = wert
        self.text = f"{feld} von {objekt_id} ändern"
        self._alt: object = None
        self._gesetzt = False

    def _objekt(self, anlage: Anlage):
        if self.art == "bauteil":
            return anlage.bauteile[self.objekt_id]
        return anlage.verbindungen[self.objekt_id]

    def ausfuehren(self, anlage: Anlage) -> None:
        objekt = self._objekt(anlage)
        if not self._gesetzt:
            self._alt = getattr(objekt, self.feld)
            self._gesetzt = True
        setattr(objekt, self.feld, self.wert)

    def rueckgaengig(self, anlage: Anlage) -> None:
        setattr(self._objekt(anlage), self.feld, self._alt)


class MakroBefehl(Befehl):
    """Mehrere Befehle als ein Schritt. Entsteht aus Befehlsstapel.makro()."""

    def __init__(self, text: str, befehle: list[Befehl]) -> None:
        self.text = text
        self._befehle = list(befehle)

    def ausfuehren(self, anlage: Anlage) -> None:
        for befehl in self._befehle:
            befehl.ausfuehren(anlage)

    def rueckgaengig(self, anlage: Anlage) -> None:
        for befehl in reversed(self._befehle):
            befehl.rueckgaengig(anlage)


class Befehlsstapel:
    def __init__(self, anlage: Anlage, grenze: int = GRENZE_STANDARD) -> None:
        self._anlage = anlage
        self._grenze = grenze
        self._zurueck: list[Befehl] = []
        self._vor: list[Befehl] = []
        self._makro: list[Befehl] | None = None

    # ------------------------------------------------------------------

    def ausfuehren(self, befehl: Befehl) -> None:
        """Fuehrt aus. Schlaegt die Ausfuehrung fehl, wird nichts gespeichert."""
        befehl.ausfuehren(self._anlage)
        if self._makro is not None:
            self._makro.append(befehl)
            return
        self._ablegen(befehl)

    def _ablegen(self, befehl: Befehl) -> None:
        if not (self._zurueck and self._zurueck[-1].verschmelzen(befehl)):
            self._zurueck.append(befehl)
        self._vor.clear()
        if len(self._zurueck) > self._grenze:
            del self._zurueck[0]

    @contextmanager
    def makro(self, text: str) -> Iterator[None]:
        """Alle Befehle im Block werden zu einem Schritt. Bei Fehler wird alles zurueckgenommen."""
        if self._makro is not None:
            raise RuntimeError("Makros koennen nicht verschachtelt werden.")
        self._makro = []
        try:
            yield
        except BaseException:
            for befehl in reversed(self._makro):
                befehl.rueckgaengig(self._anlage)
            self._makro = None
            raise
        else:
            teile = self._makro
            self._makro = None
            if teile:
                self._ablegen(MakroBefehl(text, teile))

    def rueckgaengig(self) -> bool:
        if not self._zurueck:
            return False
        befehl = self._zurueck.pop()
        befehl.rueckgaengig(self._anlage)
        self._vor.append(befehl)
        return True

    def wiederholen(self) -> bool:
        if not self._vor:
            return False
        befehl = self._vor.pop()
        befehl.ausfuehren(self._anlage)
        self._zurueck.append(befehl)
        return True

    # ------------------------------------------------------------------

    @property
    def kann_rueckgaengig(self) -> bool:
        return bool(self._zurueck)

    @property
    def kann_wiederholen(self) -> bool:
        return bool(self._vor)

    @property
    def beschriftung_rueckgaengig(self) -> str:
        return self._zurueck[-1].text if self._zurueck else ""

    @property
    def beschriftung_wiederholen(self) -> str:
        return self._vor[-1].text if self._vor else ""