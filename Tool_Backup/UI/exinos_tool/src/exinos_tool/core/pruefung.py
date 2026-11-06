"""Pruefungen P-1 bis P-8 vor dem Export.

Jede Pruefung ist eine Funktion (anlage, pool) -> Iterable[Befund]. Eine
neue Pruefung erfordert eine Funktion und einen Eintrag in der Registry,
sonst keine Aenderung. Jede Pruefung ist einzeln testbar.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from .modell import ID_MUSTER, Anlage
from .pool import Pool

#: Nur Bauteile dieses Typs sind von P-6 ausgenommen. Der Typ rahmen
#: entfaellt hier, weil das Frontend ihn nie schreibt.
AUSNAHME_P6: frozenset[str] = frozenset()


class Schwere(enum.IntEnum):
    """Schweregrade in der Reihenfolge des Protokollformats.

    Der ganzzahlige Wert dient der Sortierung: FEHLER zuerst.
    """

    FEHLER = 0
    WARNUNG = 1
    HINWEIS = 2
    INFO = 3


@dataclass(frozen=True)
class Befund:
    """Ein einzelnes Pruefergebnis."""

    schwere: Schwere
    code: str
    text: str
    elemente: tuple[str, ...] = ()

    def protokollzeile(self) -> str:
        """Zeile im Format SCHWERE;quelle;text fuer analysis_log.txt."""
        return f"{self.schwere.name};{self.code};{self.text}"


@dataclass
class Pruefbericht:
    """Das Gesamtergebnis eines Prueflaufs."""

    befunde: list[Befund] = field(default_factory=list)

    @property
    def fehler(self) -> list[Befund]:
        return [b for b in self.befunde if b.schwere is Schwere.FEHLER]

    @property
    def warnungen(self) -> list[Befund]:
        return [b for b in self.befunde if b.schwere is Schwere.WARNUNG]

    @property
    def hinweise(self) -> list[Befund]:
        return [b for b in self.befunde if b.schwere is Schwere.HINWEIS]

    @property
    def exportfaehig(self) -> bool:
        """Export und Analyse sind nur ohne Fehler moeglich."""
        return not self.fehler

    def zusammenfassung(self) -> tuple[int, int, int]:
        """(Fehler, Warnungen, Hinweise) - die Abnahmekennzahl."""
        return (len(self.fehler), len(self.warnungen), len(self.hinweise))

    def protokoll(self) -> str:
        return "\n".join(b.protokollzeile() for b in self.befunde)


# ----------------------------------------------------------------------
# Einzelpruefungen
# ----------------------------------------------------------------------


def p1_ids(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Jede id ist eindeutig und enthaelt nur Buchstaben, Ziffern und _."""
    gesehen: set[str] = set()
    for kennung in anlage.alle_ids():
        if kennung in gesehen:
            yield Befund(
                Schwere.FEHLER, "P-1", f"Die id {kennung!r} ist mehrfach vergeben.",
                (kennung,),
            )
        gesehen.add(kennung)
        if not ID_MUSTER.match(kennung):
            yield Befund(
                Schwere.FEHLER,
                "P-1",
                f"Die id {kennung!r} enthaelt unzulaessige Zeichen.",
                (kennung,),
            )

    for v_id in anlage.verbindungen:
        if not ID_MUSTER.match(v_id):
            yield Befund(
                Schwere.FEHLER,
                "P-1",
                f"Die Verbindungs-id {v_id!r} enthaelt unzulaessige Zeichen.",
                (v_id,),
            )


def p2_typen_und_ports(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Jeder Typ steht im Pool, jeder Port gehoert zu seinem Typ."""
    for bauteil in anlage.bauteile.values():
        typ = pool.typ(bauteil.typ)
        if typ is None:
            yield Befund(
                Schwere.FEHLER,
                "P-2",
                f"Bauteil {bauteil.id!r}: Der Typ {bauteil.typ!r} steht nicht im Pool.",
                (bauteil.id,),
            )
        elif not typ.platzierbar:
            yield Befund(
                Schwere.FEHLER,
                "P-2",
                f"Bauteil {bauteil.id!r}: Der Typ {bauteil.typ!r} ist nicht "
                "platzierbar und darf nicht in components.csv stehen.",
                (bauteil.id,),
            )

    for verbindung in anlage.verbindungen.values():
        for rolle, bauteil_id, port_name in (
            ("von", verbindung.von, verbindung.von_port),
            ("nach", verbindung.nach, verbindung.nach_port),
        ):
            bauteil = anlage.bauteile.get(bauteil_id)
            if bauteil is None:
                yield Befund(
                    Schwere.FEHLER,
                    "P-2",
                    f"Verbindung {verbindung.id!r}: Das Bauteil {bauteil_id!r} "
                    f"({rolle}) ist nicht vorhanden.",
                    (verbindung.id,),
                )
                continue
            typ = pool.typ(bauteil.typ)
            if typ is None:
                continue
            if typ.port(port_name) is None:
                yield Befund(
                    Schwere.FEHLER,
                    "P-2",
                    f"Verbindung {verbindung.id!r}: Der Typ {bauteil.typ!r} hat "
                    f"keinen Port {port_name!r}.",
                    (verbindung.id, bauteil_id),
                )


def p3_art_und_richtung(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Gleiche art, zulaessige Richtung und eingehaltene Hoechstbelegung."""
    for verbindung in anlage.verbindungen.values():
        von_bauteil = anlage.bauteile.get(verbindung.von)
        nach_bauteil = anlage.bauteile.get(verbindung.nach)
        if von_bauteil is None or nach_bauteil is None:
            continue  # bereits durch P-2 gemeldet

        von_port = pool.port(von_bauteil.typ, verbindung.von_port)
        nach_port = pool.port(nach_bauteil.typ, verbindung.nach_port)
        if von_port is None or nach_port is None:
            continue

        if von_port.art != nach_port.art:
            yield Befund(
                Schwere.FEHLER,
                "P-3a",
                f"Verbindung {verbindung.id!r}: Die Ports haben verschiedene Arten "
                f"({von_port.art} und {nach_port.art}).",
                (verbindung.id,),
            )
        elif verbindung.art != von_port.art:
            yield Befund(
                Schwere.FEHLER,
                "P-3a",
                f"Verbindung {verbindung.id!r}: Die Spalte art lautet "
                f"{verbindung.art!r}, die Ports haben die Art {von_port.art!r}.",
                (verbindung.id,),
            )

        if von_port.richtung != "aus" or nach_port.richtung != "ein":
            yield Befund(
                Schwere.FEHLER,
                "P-3b",
                f"Verbindung {verbindung.id!r}: Die Orientierung muss aus -> ein "
                f"sein. {verbindung.von}.{verbindung.von_port} ist "
                f"{von_port.richtung!r}, {verbindung.nach}.{verbindung.nach_port} "
                f"ist {nach_port.richtung!r}.",
                (verbindung.id,),
            )

    belegung = anlage.belegung()
    for (bauteil_id, port_name), verbindungen in sorted(belegung.items()):
        bauteil = anlage.bauteile.get(bauteil_id)
        if bauteil is None:
            continue
        port = pool.port(bauteil.typ, port_name)
        if port is None or port.unbegrenzt:
            continue
        if len(verbindungen) > port.max:
            yield Befund(
                Schwere.FEHLER,
                "P-3c",
                f"Port {bauteil_id}.{port_name} ist {len(verbindungen)}-fach belegt, "
                f"zulaessig sind {port.max}.",
                (bauteil_id, *sorted(verbindungen)),
            )


def p4_bahnketten(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Jede Bahn ist eine lueckenlose Kette ohne Verzweigung und Zyklus."""
    for bahn_id in sorted(anlage.bahnen):
        kanten = anlage.kanten_der_bahn(bahn_id)
        if not kanten:
            yield Befund(
                Schwere.FEHLER,
                "P-4",
                f"Bahn {bahn_id!r}: Es ist keine Verbindung zugeordnet.",
                (bahn_id,),
            )
            continue

        knoten: set[str] = set()
        ausgang: dict[str, int] = {}
        eingang: dict[str, int] = {}
        for kante in kanten:
            knoten.update((kante.von, kante.nach))
            ausgang[kante.von] = ausgang.get(kante.von, 0) + 1
            eingang[kante.nach] = eingang.get(kante.nach, 0) + 1

        verzweigt = sorted(k for k in knoten if ausgang.get(k, 0) > 1)
        zusammengefuehrt = sorted(k for k in knoten if eingang.get(k, 0) > 1)
        if verzweigt:
            yield Befund(
                Schwere.FEHLER,
                "P-4",
                f"Bahn {bahn_id!r}: Verzweigung bei {', '.join(verzweigt)}.",
                (bahn_id, *verzweigt),
            )
        if zusammengefuehrt:
            yield Befund(
                Schwere.FEHLER,
                "P-4",
                f"Bahn {bahn_id!r}: Zusammenfuehrung bei "
                f"{', '.join(zusammengefuehrt)}.",
                (bahn_id, *zusammengefuehrt),
            )

        quellen = sorted(k for k in knoten if eingang.get(k, 0) == 0)
        senken = sorted(k for k in knoten if ausgang.get(k, 0) == 0)
        if len(quellen) != 1 or len(senken) != 1:
            yield Befund(
                Schwere.FEHLER,
                "P-4",
                f"Bahn {bahn_id!r}: Es muss genau einen Anfang und genau ein Ende "
                f"geben, gefunden wurden {len(quellen)} und {len(senken)}.",
                (bahn_id,),
            )

        # Faengt den Fall "Kette plus getrennter Zyklus" ab.
        if len(kanten) != len(knoten) - 1:
            yield Befund(
                Schwere.FEHLER,
                "P-4",
                f"Bahn {bahn_id!r}: {len(knoten)} Knoten bei {len(kanten)} Kanten. "
                f"Eine Kette braucht {len(knoten) - 1} Kanten.",
                (bahn_id,),
            )


def p5_bahnzuordnung(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Jede bahn-Verbindung ist einer vorhandenen Bahn zugeordnet."""
    for verbindung in anlage.verbindungen.values():
        if verbindung.art != "bahn":
            if verbindung.bahn:
                yield Befund(
                    Schwere.WARNUNG,
                    "P-5",
                    f"Verbindung {verbindung.id!r} ist keine Bahnverbindung, traegt "
                    f"aber die Bahn {verbindung.bahn!r}.",
                    (verbindung.id,),
                )
            continue
        if not verbindung.bahn:
            yield Befund(
                Schwere.FEHLER,
                "P-5",
                f"Verbindung {verbindung.id!r}: Es ist keine Bahn zugeordnet.",
                (verbindung.id,),
            )
        elif verbindung.bahn not in anlage.bahnen:
            yield Befund(
                Schwere.FEHLER,
                "P-5",
                f"Verbindung {verbindung.id!r}: Die Bahn {verbindung.bahn!r} ist "
                "nicht angelegt.",
                (verbindung.id,),
            )


def p6_isolierte(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Kein Bauteil steht ohne Verbindung da.

    Materialbahnen sind keine Bauteile und deshalb von vornherein
    ausgenommen.
    """
    for bauteil_id in sorted(anlage.bauteile):
        bauteil = anlage.bauteile[bauteil_id]
        if bauteil.typ in AUSNAHME_P6:
            continue
        if not anlage.hat_verbindungen(bauteil_id):
            yield Befund(
                Schwere.WARNUNG,
                "P-6",
                f"Bauteil {bauteil_id!r} hat keine Verbindung.",
                (bauteil_id,),
            )


def p7_pflichtports(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Kein Pflicht-Port ist frei."""
    belegung = anlage.belegung()
    for bauteil_id in sorted(anlage.bauteile):
        bauteil = anlage.bauteile[bauteil_id]
        typ = pool.typ(bauteil.typ)
        if typ is None:
            continue
        for port in typ.pflichtports():
            if not belegung.get((bauteil_id, port.name)):
                yield Befund(
                    Schwere.WARNUNG,
                    "P-7",
                    f"Pflicht-Port {bauteil_id}.{port.name} ist nicht belegt.",
                    (bauteil_id,),
                )


def p8_antriebe(anlage: Anlage, pool: Pool) -> Iterator[Befund]:
    """Jeder Antrieb hat mindestens einen Signaleingang.

    Die Pruefung gilt ausschliesslich fuer den Typ 'antrieb'. Andere Typen
    mit Signaleingang sind ueber P-7 abgedeckt, sofern der Port Pflicht ist.
    """
    for bauteil_id in sorted(anlage.bauteile):
        bauteil = anlage.bauteile[bauteil_id]
        if bauteil.typ != "antrieb":
            continue
        hat_signal = any(
            v.art == "signal" and v.nach == bauteil_id
            for v in anlage.verbindungen.values()
        )
        if not hat_signal:
            yield Befund(
                Schwere.HINWEIS,
                "P-8",
                f"Antrieb {bauteil_id!r} hat keinen Signaleingang.",
                (bauteil_id,),
            )


# ----------------------------------------------------------------------
# Registry und Gesamtlauf
# ----------------------------------------------------------------------

Pruefung = Callable[[Anlage, Pool], Iterable[Befund]]

REGISTRY: list[tuple[str, Pruefung]] = [
    ("P-1", p1_ids),
    ("P-2", p2_typen_und_ports),
    ("P-3", p3_art_und_richtung),
    ("P-4", p4_bahnketten),
    ("P-5", p5_bahnzuordnung),
    ("P-6", p6_isolierte),
    ("P-7", p7_pflichtports),
    ("P-8", p8_antriebe),
]


def pruefe(anlage: Anlage, pool: Pool) -> Pruefbericht:
    """Fuehrt alle Pruefungen aus und sortiert nach Schwere (Z-6)."""
    befunde: list[Befund] = []
    for _code, pruefung in REGISTRY:
        befunde.extend(pruefung(anlage, pool))
    befunde.sort(key=lambda b: (b.schwere, b.code, b.text))
    return Pruefbericht(befunde=befunde)

# ----------------------------------------------------------------------
# Live-Pruefung fuer die UI: Darf eine Verbindung angelegt werden?
# ----------------------------------------------------------------------


def verbindung_moeglich(
    anlage: Anlage,
    pool: Pool,
    a_bauteil: str,
    a_port: str,
    b_bauteil: str,
    b_port: str,
) -> tuple[bool, str, tuple[str, str, str, str] | None]:
    """Prueft, ob zwei Ports verbunden werden duerfen (C-2, P-3).

    Gibt zurueck:
      (erlaubt, grund, orientierung)
    orientierung ist (von, von_port, nach, nach_port) in verbindlicher
    Richtung aus->ein, oder None, wenn die Verbindung nicht erlaubt ist.
    """
    if a_bauteil == b_bauteil:
        return False, "Ein Bauteil kann nicht mit sich selbst verbunden werden.", None

    bt_a = anlage.bauteile.get(a_bauteil)
    bt_b = anlage.bauteile.get(b_bauteil)
    if bt_a is None or bt_b is None:
        return False, "Ein beteiligtes Bauteil ist nicht vorhanden.", None

    port_a = pool.port(bt_a.typ, a_port)
    port_b = pool.port(bt_b.typ, b_port)
    if port_a is None or port_b is None:
        return False, "Ein Port ist im Pool nicht bekannt.", None

    if port_a.art != port_b.art:
        return (
            False,
            f"Verschiedene Arten: {port_a.art} und {port_b.art}.",
            None,
        )
    if not port_a.passt_zu(port_b):
        return (
            False,
            "Die Ports haben nicht entgegengesetzte Richtungen (aus und ein).",
            None,
        )

    # Verbindliche Orientierung festlegen: aus -> ein.
    if port_a.richtung == "aus":
        von, von_port, nach, nach_port = a_bauteil, a_port, b_bauteil, b_port
        p_von, p_nach = port_a, port_b
    else:
        von, von_port, nach, nach_port = b_bauteil, b_port, a_bauteil, a_port
        p_von, p_nach = port_b, port_a

    # Hoechstbelegung je Port pruefen (P-3c).
    def belegung(bauteil: str, port_name: str) -> int:
        return sum(
            1
            for v in anlage.verbindungen.values()
            if (v.von == bauteil and v.von_port == port_name)
            or (v.nach == bauteil and v.nach_port == port_name)
        )

    if not p_von.unbegrenzt and belegung(von, von_port) >= p_von.max:
        return (
            False,
            f"{von}.{von_port} ist bereits voll belegt (max {p_von.max}).",
            None,
        )
    if not p_nach.unbegrenzt and belegung(nach, nach_port) >= p_nach.max:
        return (
            False,
            f"{nach}.{nach_port} ist bereits voll belegt (max {p_nach.max}).",
            None,
        )

    return True, "", (von, von_port, nach, nach_port)