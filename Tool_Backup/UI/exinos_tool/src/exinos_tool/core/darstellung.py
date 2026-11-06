"""Overlay mit den Darstellungsangaben (pool_darstellung.json).

bauteilpool.json ist die Masterdatei und wird vom Frontend nie veraendert.
Symbol, Groesse und Portpositionen stehen in dieser getrennten Datei.
Fehlt ein Eintrag, greift ein Notverhalten, damit ein neuer Typ allein
ueber den Pool benutzbar ist (R-4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .pool import Pool, Typ

SEITEN = ("links", "oben", "rechts", "unten")

#: Notverhalten, wenn das Overlay nichts angibt.
STANDARDGROESSE = (80.0, 80.0)


@dataclass(frozen=True)
class PortDarstellung:
    """Position eines Ports am Symbolrand.

    versatz 0..1: bei links und rechts von oben nach unten,
    bei oben und unten von links nach rechts.
    """

    seite: str
    versatz: float


@dataclass(frozen=True)
class TypDarstellung:
    typ: str
    symbol: str | None
    groesse: tuple[float, float]
    ports: dict[str, PortDarstellung]
    ersatzsymbol: bool = False

    @property
    def breite(self) -> float:
        return self.groesse[0]

    @property
    def hoehe(self) -> float:
        return self.groesse[1]


def effektive_seite(seite: str, drehung: int, gespiegelt: bool) -> str:
    """Rechnet eine Portseite auf Drehung und Spiegelung um (B-7).

    Die Drehung erfolgt in 90-Grad-Schritten im Uhrzeigersinn, die
    Spiegelung an der senkrechten Achse (links und rechts tauschen).
    """
    index = SEITEN.index(seite)
    index = (index + (drehung // 90)) % len(SEITEN)
    seite = SEITEN[index]
    if gespiegelt and seite in ("links", "rechts"):
        seite = "rechts" if seite == "links" else "links"
    return seite


def port_versatz(darstellung: TypDarstellung, portname: str) -> tuple[float, float]:
    """Gibt die Portposition als Versatz vom linken oberen Symboleck zurueck."""
    port = darstellung.ports.get(portname)
    if port is None:
        return (darstellung.breite / 2, darstellung.hoehe / 2)
    breite, hoehe = darstellung.groesse
    if port.seite == "links":
        return (0.0, hoehe * port.versatz)
    if port.seite == "rechts":
        return (breite, hoehe * port.versatz)
    if port.seite == "oben":
        return (breite * port.versatz, 0.0)
    return (breite * port.versatz, hoehe)


@dataclass
class Darstellung:
    """Das geladene Overlay, bereits mit dem Pool abgeglichen."""

    typen: dict[str, TypDarstellung] = field(default_factory=dict)
    meldungen: list[str] = field(default_factory=list)
    quelle: Path | None = None

    # ------------------------------------------------------------------

    @classmethod
    def laden(cls, pfad: str | Path | None, pool: Pool) -> Darstellung:
        """Laedt das Overlay und ergaenzt fehlende Angaben.

        Ein fehlender Pfad oder eine fehlende Datei ist kein Fehler: Dann
        wird fuer jeden Typ vollstaendig das Notverhalten verwendet.
        """
        rohdaten: dict = {}
        quelle = Path(pfad) if pfad else None
        meldungen: list[str] = []

        if quelle and quelle.exists():
            rohdaten = json.loads(quelle.read_text(encoding="utf-8"))
            fuer_version = str(rohdaten.get("fuer_pool_version", ""))
            if fuer_version and fuer_version != pool.version:
                meldungen.append(
                    f"Die Darstellungsdatei ist fuer Poolversion {fuer_version} "
                    f"gedacht, geladen wurde {pool.version}."
                )
        elif quelle:
            meldungen.append(
                f"Darstellungsdatei {quelle.name} nicht gefunden. Alle Typen "
                "verwenden das Notverhalten."
            )

        standard = rohdaten.get("standard", {})
        standardgroesse = tuple(standard.get("groesse", STANDARDGROESSE))
        eintraege = rohdaten.get("typen", {})

        typen: dict[str, TypDarstellung] = {}
        for typ in pool.platzierbare_typen():
            typen[typ.typ] = cls._typ_aufbauen(
                typ, eintraege.get(typ.typ, {}), standardgroesse, meldungen
            )

        unbekannt = sorted(set(eintraege) - set(typen))
        for name in unbekannt:
            meldungen.append(
                f"Die Darstellungsdatei kennt den Typ {name!r}, der Pool nicht."
            )

        return cls(typen=typen, meldungen=meldungen, quelle=quelle)

    @staticmethod
    def _typ_aufbauen(
        typ: Typ, eintrag: dict, standardgroesse: tuple, meldungen: list[str]
    ) -> TypDarstellung:
        symbol = eintrag.get("symbol")
        if not symbol:
            meldungen.append(
                f"Typ {typ.typ!r}: kein Symbol hinterlegt, es wird ein "
                "Ersatzrechteck gezeichnet."
            )

        groesse = tuple(eintrag.get("groesse", standardgroesse))

        roh_ports = eintrag.get("ports", {})
        ports: dict[str, PortDarstellung] = {}
        ohne_position: list[str] = []
        for name, port in typ.ports.items():
            angabe = roh_ports.get(name)
            if angabe and angabe.get("seite") in SEITEN:
                ports[name] = PortDarstellung(
                    seite=str(angabe["seite"]),
                    versatz=float(angabe.get("versatz", 0.5)),
                )
            else:
                ohne_position.append(name)

        if ohne_position:
            meldungen.append(
                f"Typ {typ.typ!r}: keine Position fuer "
                f"{', '.join(sorted(ohne_position))}. Die Ports werden "
                "automatisch verteilt (ein links, aus rechts)."
            )
            ports.update(
                Darstellung._automatisch_verteilen(typ, ohne_position, ports)
            )

        return TypDarstellung(
            typ=typ.typ,
            symbol=symbol,
            groesse=(float(groesse[0]), float(groesse[1])),
            ports=ports,
            ersatzsymbol=not symbol,
        )

    @staticmethod
    def _automatisch_verteilen(
        typ: Typ, namen: list[str], belegt: dict[str, PortDarstellung]
    ) -> dict[str, PortDarstellung]:
        """Notverhalten: Eingaenge links, Ausgaenge rechts, gleichmaessig."""
        gruppen: dict[str, list[str]] = {"links": [], "rechts": []}
        for name in sorted(namen):
            seite = "links" if typ.ports[name].richtung == "ein" else "rechts"
            gruppen[seite].append(name)

        ergebnis: dict[str, PortDarstellung] = {}
        for seite, liste in gruppen.items():
            vorhanden = sum(1 for p in belegt.values() if p.seite == seite)
            gesamt = len(liste) + vorhanden
            for lauf, name in enumerate(liste, start=vorhanden + 1):
                ergebnis[name] = PortDarstellung(
                    seite=seite, versatz=lauf / (gesamt + 1)
                )
        return ergebnis

    # ------------------------------------------------------------------

    def fuer(self, typ_name: str) -> TypDarstellung:
        """Gibt die Darstellung eines Typs zurueck, notfalls eine Ersatzform."""
        vorhanden = self.typen.get(typ_name)
        if vorhanden is not None:
            return vorhanden
        return TypDarstellung(
            typ=typ_name,
            symbol=None,
            groesse=STANDARDGROESSE,
            ports={},
            ersatzsymbol=True,
        )

    def position(
        self, typ_name: str, portname: str, drehung: int = 0, gespiegelt: bool = False
    ) -> tuple[float, float]:
        """Portposition relativ zum Symbol, unter Beruecksichtigung von B-7."""
        darstellung = self.fuer(typ_name)
        port = darstellung.ports.get(portname)
        if port is None:
            return (darstellung.breite / 2, darstellung.hoehe / 2)
        gedreht = TypDarstellung(
            typ=darstellung.typ,
            symbol=darstellung.symbol,
            groesse=darstellung.groesse,
            ports={
                portname: PortDarstellung(
                    seite=effektive_seite(port.seite, drehung, gespiegelt),
                    versatz=port.versatz,
                )
            },
        )
        return port_versatz(gedreht, portname)

    def symbol_pfad(self, typ_name: str):
        """Voller Pfad zur SVG-Datei eines Typs, oder None.

        Sucht die Datei im Ordner 'symbole' neben der Overlay-Datei und,
        falls das nichts ergibt, im Projektordner unter ressourcen/symbole.
        """
        from pathlib import Path

        form = self.fuer(typ_name)
        if not form.symbol:
            return None

        kandidaten = []
        if self.quelle is not None:
            basis = Path(self.quelle).parent
            kandidaten.append(basis / "symbole" / form.symbol)
            kandidaten.append(basis.parent / "ressourcen" / "symbole" / form.symbol)
        for pfad in kandidaten:
            if pfad.exists():
                return pfad
        return None