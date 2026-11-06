"""Datenmodell der Anlage.

Qt-frei und ohne externe Abhaengigkeiten, damit Pruefung, Import, Export
und Layout als reine pytest-Laeufe ohne Bildschirm testbar sind.

Grundsatz: Alle Querverweise laufen ueber id-Strings, niemals ueber
Objektreferenzen. Das haelt Kopieren, Umbenennen und Undo einfach.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

#: Zulaessige Zeichen einer id (Pruefung P-1).
ID_MUSTER = re.compile(r"^[A-Za-z0-9_]+$")

#: Pseudotyp fuer Materialbahnen. Steht im Pool mit platzierbar = false und
#: erscheint in components.csv als eigene Zeile (W-5), ist aber kein Bauteil.
TYP_MATERIALBAHN = "materialbahn"

#: Pseudotyp fuer den Maschinenrahmen. Wird ausschliesslich vom Backend aus
#: der Spalte gestellfest erzeugt; das Frontend schreibt ihn nie.
TYP_RAHMEN = "rahmen"


@dataclass
class Bauteil:
    """Eine Komponenteninstanz auf der Arbeitsflaeche.

    Die Felder id bis bemerkung gehen nach components.csv. Die Felder ab x
    sind reine Darstellung und stehen nur in der Projektdatei.
    """

    id: str
    typ: str
    bezeichnung: str = ""
    materialpfad: str = ""
    baugruppe: str = ""
    gestellfest: str = ""
    bemerkung: str = ""

    x: float = 0.0
    y: float = 0.0
    drehung: int = 0
    gespiegelt: bool = False


@dataclass
class Verbindung:
    """Eine Verbindung zwischen zwei Ports.

    Die Orientierung ist verbindlich: von/von_port ist immer der Port mit
    richtung "aus", nach/nach_port immer der mit richtung "ein". Das gilt
    unabhaengig davon, ob die Verbindungsart physikalisch kausal ist.
    """

    id: str
    von: str
    von_port: str
    nach: str
    nach_port: str
    art: str
    bahn: str = ""

    knickpunkte: list[tuple[float, float]] = field(default_factory=list)

    @property
    def quelle(self) -> tuple[str, str]:
        return (self.von, self.von_port)

    @property
    def ziel(self) -> tuple[str, str]:
        return (self.nach, self.nach_port)

    def partner(self, bauteil_id: str) -> str | None:
        """Gibt das jeweils andere Bauteil zurueck, sonst None."""
        if self.von == bauteil_id:
            return self.nach
        if self.nach == bauteil_id:
            return self.von
        return None


@dataclass
class Bahn:
    """Eine Materialbahn.

    id und bezeichnung gehen nach components.csv, kuerzel in die Spalte
    materialpfad. Die Farbe ist reine Darstellung und bleibt in der
    Projektdatei.
    """

    id: str
    bezeichnung: str = ""
    kuerzel: str = ""
    farbe: str = "#1F77B4"


@dataclass
class Anlage:
    """Die vollstaendige Anlage: Bauteile, Verbindungen, Materialbahnen."""

    bauteile: dict[str, Bauteil] = field(default_factory=dict)
    verbindungen: dict[str, Verbindung] = field(default_factory=dict)
    bahnen: dict[str, Bahn] = field(default_factory=dict)

    name: str = ""
    bearbeiter: str = ""

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def hinzufuegen(self, bauteil: Bauteil) -> None:
        if bauteil.id in self.bauteile:
            raise KeyError(f"Bauteil-id {bauteil.id!r} ist bereits vergeben.")
        self.bauteile[bauteil.id] = bauteil

    def verbinden(self, verbindung: Verbindung) -> None:
        if verbindung.id in self.verbindungen:
            raise KeyError(f"Verbindungs-id {verbindung.id!r} ist bereits vergeben.")
        self.verbindungen[verbindung.id] = verbindung

    def bahn_hinzufuegen(self, bahn: Bahn) -> None:
        if bahn.id in self.bahnen:
            raise KeyError(f"Bahn-id {bahn.id!r} ist bereits vergeben.")
        self.bahnen[bahn.id] = bahn

    def entferne_bauteil(self, bauteil_id: str) -> list[str]:
        """Entfernt ein Bauteil samt seinen Verbindungen (C-5).

        Gibt die ids der mitentfernten Verbindungen zurueck, damit ein
        Undo-Befehl sie wiederherstellen kann.
        """
        self.bauteile.pop(bauteil_id, None)
        betroffen = [
            v_id
            for v_id, v in self.verbindungen.items()
            if v.von == bauteil_id or v.nach == bauteil_id
        ]
        for v_id in betroffen:
            del self.verbindungen[v_id]
        return betroffen

    def umbenennen(self, alt: str, neu: str) -> None:
        """Benennt ein Bauteil um und zieht alle Verweise nach (E-3)."""
        if alt == neu:
            return
        if neu in self.bauteile:
            raise KeyError(f"Bauteil-id {neu!r} ist bereits vergeben.")
        bauteil = self.bauteile.pop(alt)
        bauteil.id = neu
        self.bauteile[neu] = bauteil
        for verbindung in self.verbindungen.values():
            if verbindung.von == alt:
                verbindung.von = neu
            if verbindung.nach == alt:
                verbindung.nach = neu


    def freie_id(self, typ: str) -> str:
        """Liefert eine noch nicht vergebene id der Form Typ_1, Typ_2 ..."""
        basis = typ.capitalize()
        nummer = 1
        while f"{basis}_{nummer}" in self.bauteile:
            nummer += 1
        return f"{basis}_{nummer}"

    # ------------------------------------------------------------------
    # Abfragen
    # ------------------------------------------------------------------

    def alle_ids(self) -> list[str]:
        """Alle ids, die in components.csv landen: Bauteile und Bahnen."""
        return list(self.bauteile) + list(self.bahnen)

    def belegung(self) -> dict[tuple[str, str], list[str]]:
        """Bildet (bauteil_id, portname) auf die ids der Verbindungen ab."""
        ergebnis: dict[tuple[str, str], list[str]] = {}
        for verbindung in self.verbindungen.values():
            ergebnis.setdefault(verbindung.quelle, []).append(verbindung.id)
            ergebnis.setdefault(verbindung.ziel, []).append(verbindung.id)
        return ergebnis

    def kanten_von(self, bauteil_id: str) -> list[Verbindung]:
        """Alle Verbindungen, an denen das Bauteil beteiligt ist."""
        return [
            v
            for v in self.verbindungen.values()
            if v.von == bauteil_id or v.nach == bauteil_id
        ]

    def kanten_der_art(self, *arten: str) -> list[Verbindung]:
        menge = set(arten)
        return [v for v in self.verbindungen.values() if v.art in menge]

    def kanten_der_bahn(self, bahn_id: str) -> list[Verbindung]:
        return [
            v
            for v in self.verbindungen.values()
            if v.art == "bahn" and v.bahn == bahn_id
        ]

    def hat_verbindungen(self, bauteil_id: str) -> bool:
        return any(
            v.von == bauteil_id or v.nach == bauteil_id
            for v in self.verbindungen.values()
        )

    # ------------------------------------------------------------------
    # Strukturfingerabdruck (Z-7)
    # ------------------------------------------------------------------

    def kanonische_struktur(self) -> list[str]:
        """Kanonische, sortierte Darstellung des exportrelevanten Inhalts.

        Enthaelt genau die Felder, die nach components.csv und
        connections.csv gehen. Position, Drehung, Knickpunkte und
        Bahnfarbe bleiben bewusst aussen vor: Das blosse Verschieben
        eines Symbols darf Analyseergebnisse nicht veralten lassen.
        """
        zeilen: list[str] = []
        for bahn in sorted(self.bahnen.values(), key=lambda b: b.id):
            zeilen.append(f"M|{bahn.id}|{bahn.bezeichnung}|{bahn.kuerzel}")
        for bauteil in sorted(self.bauteile.values(), key=lambda b: b.id):
            zeilen.append(
                "B|"
                + "|".join(
                    [
                        bauteil.id,
                        bauteil.typ,
                        bauteil.bezeichnung,
                        bauteil.materialpfad,
                        bauteil.baugruppe,
                        bauteil.gestellfest,
                        bauteil.bemerkung,
                    ]
                )
            )
        for verbindung in sorted(self.verbindungen.values(), key=lambda v: v.id):
            zeilen.append(
                "V|"
                + "|".join(
                    [
                        verbindung.id,
                        verbindung.von,
                        verbindung.von_port,
                        verbindung.nach,
                        verbindung.nach_port,
                        verbindung.art,
                        verbindung.bahn,
                    ]
                )
            )
        return zeilen

    def strukturfingerabdruck(self) -> str:
        """SHA-256 ueber die kanonische Struktur.

        Analyseergebnisse speichern den Fingerabdruck, bei dem sie
        entstanden sind. Weicht er ab, gelten sie als veraltet (Z-7).
        """
        inhalt = "\n".join(self.kanonische_struktur())
        return hashlib.sha256(inhalt.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Vergleich (Abnahme 1: Mengenvergleich, nicht Textdiff)
    # ------------------------------------------------------------------

    def inhaltsgleich(self, andere: Anlage) -> bool:
        return set(self.kanonische_struktur()) == set(andere.kanonische_struktur())

    def unterschiede(self, andere: Anlage) -> tuple[list[str], list[str]]:
        """Gibt (nur_hier, nur_dort) als sortierte Listen zurueck."""
        hier = set(self.kanonische_struktur())
        dort = set(andere.kanonische_struktur())
        return sorted(hier - dort), sorted(dort - hier)