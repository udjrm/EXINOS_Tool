"""Laden und Pruefen der Masterdatei bauteilpool.json.

Die Datei ist die gemeinsame Quelle von Frontend und Backend und wird vom
Frontend NIE veraendert. Darstellungsangaben (symbol, groesse,
Portpositionen) stehen in der Overlay-Datei pool_darstellung.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Werte, die das Feld rolle an einem lage-Port annehmen darf.
ROLLE_LEISTUNG = "leistung"
ROLLE_MESSUNG = "messung"

#: Werte des Feldes rolle_layout einer Verbindungsart (Festlegung L1/L2).
LAYOUT_SPUR = "spur"
LAYOUT_STRUKTUR = "struktur"
LAYOUT_ANKER_SPUR = "anker_spur"
LAYOUT_ANKER_SEITLICH = "anker_seitlich"
LAYOUT_NACH_PORT_ROLLE = "nach_port_rolle"

GUELTIGE_LAYOUTROLLEN = {
    LAYOUT_SPUR,
    LAYOUT_STRUKTUR,
    LAYOUT_ANKER_SPUR,
    LAYOUT_ANKER_SEITLICH,
    LAYOUT_NACH_PORT_ROLLE,
}

#: Abbildung der ueberholten Sammelbezeichnung "anker" auf die getrennten
#: Werte aus L2. Nur fuer Pools vor der L1/L2-Anpassung.
MIGRATION_ANKER = {"material": LAYOUT_ANKER_SPUR}


class PoolFehler(Exception):
    """Die Pooldatei ist unbrauchbar."""


@dataclass(frozen=True)
class Port:
    """Eine Portdefinition eines Bauteiltyps."""

    name: str
    art: str
    richtung: str
    max: int | None = 1
    pflicht: bool = False
    rolle: str | None = None

    @property
    def unbegrenzt(self) -> bool:
        """max = null bedeutet unbegrenzt viele Verbindungen."""
        return self.max is None

    @property
    def ist_ausgang(self) -> bool:
        return self.richtung == "aus"

    def passt_zu(self, anderer: Port) -> bool:
        """Gleiche Art und entgegengesetzte Richtung (Grundlage von C-2)."""
        return self.art == anderer.art and self.richtung != anderer.richtung


@dataclass(frozen=True)
class Typ:
    """Ein Bauteiltyp aus dem Pool."""

    typ: str
    bezeichnung: str
    kurz: str
    kategorie: str
    platzierbar: bool
    gestellfest_standard: bool
    ports: dict[str, Port] = field(default_factory=dict)

    def port(self, name: str) -> Port | None:
        return self.ports.get(name)

    def pflichtports(self) -> list[Port]:
        return [p for p in self.ports.values() if p.pflicht]

    def ports_der_art(self, art: str) -> list[Port]:
        return [p for p in self.ports.values() if p.art == art]

    @property
    def hat_bahnports(self) -> bool:
        """Entscheidet ueber die Zugehoerigkeit zur Bahnspur im Layout.

        Bewusst nach Ports und nicht nach Kategorie: klemmrolle steht in
        der Kategorie Bahnfuehrung ohne bahn-Ports, bahnkantensensor in
        der Kategorie Sensorik mit bahn-Ports.
        """
        return any(p.art == "bahn" for p in self.ports.values())


@dataclass(frozen=True)
class Verbindungsart:
    """Eine Verbindungsart mit ihrer Rolle im Auto-Layout."""

    name: str
    domaene: str
    gerichtet: bool
    bezeichnung: str
    rolle_layout: str
    rolle_layout_map: dict[str, str] = field(default_factory=dict)
    rolle_layout_default: str = ROLLE_LEISTUNG


@dataclass
class Pool:
    """Der geladene Bauteilpool."""

    version: str
    verbindungsarten: dict[str, Verbindungsart]
    typen: dict[str, Typ]
    warnungen: list[str] = field(default_factory=list)
    quelle: Path | None = None

    # ------------------------------------------------------------------
    # Laden
    # ------------------------------------------------------------------

    @classmethod
    def laden(cls, pfad: str | Path) -> Pool:
        pfad = Path(pfad)
        try:
            rohdaten = json.loads(pfad.read_text(encoding="utf-8"))
        except FileNotFoundError as fehler:
            raise PoolFehler(f"Pooldatei nicht gefunden: {pfad}") from fehler
        except json.JSONDecodeError as fehler:
            raise PoolFehler(f"Pooldatei {pfad} ist kein gueltiges JSON: {fehler}") from fehler
        pool = cls.aus_rohdaten(rohdaten)
        pool.quelle = pfad
        return pool

    @classmethod
    def aus_rohdaten(cls, rohdaten: dict) -> Pool:
        warnungen: list[str] = []

        version = str(rohdaten.get("version", "")).strip()
        if not version:
            warnungen.append("Die Pooldatei nennt keine version.")

        arten = cls._arten_lesen(rohdaten.get("verbindungsarten", {}), warnungen)
        if not arten:
            raise PoolFehler("Die Pooldatei enthaelt keine verbindungsarten.")

        typen = cls._typen_lesen(rohdaten.get("typen", []), arten, warnungen)
        if not typen:
            raise PoolFehler("Die Pooldatei enthaelt keine typen.")

        return cls(
            version=version,
            verbindungsarten=arten,
            typen=typen,
            warnungen=warnungen,
        )

    @staticmethod
    def _arten_lesen(roh: dict, warnungen: list[str]) -> dict[str, Verbindungsart]:
        arten: dict[str, Verbindungsart] = {}
        for name, eintrag in roh.items():
            rolle_layout = str(eintrag.get("rolle_layout", LAYOUT_STRUKTUR))

            # Pools vor der L1/L2-Anpassung tragen noch "anker" und bei
            # lage pauschal "struktur". Beides wird toleriert und gemeldet.
            if rolle_layout == "anker":
                ersatz = MIGRATION_ANKER.get(name, LAYOUT_ANKER_SEITLICH)
                warnungen.append(
                    f"Verbindungsart {name!r}: rolle_layout 'anker' ist ueberholt, "
                    f"es gilt {ersatz!r} (Festlegung L2). Bitte die Pooldatei nachziehen."
                )
                rolle_layout = ersatz
            if name == "lage" and rolle_layout == LAYOUT_STRUKTUR:
                warnungen.append(
                    "Verbindungsart 'lage': rolle_layout 'struktur' ist ueberholt, "
                    "es gilt 'nach_port_rolle' mit "
                    "{leistung: struktur, messung: anker_seitlich} (Festlegung L1). "
                    "Bitte die Pooldatei nachziehen."
                )
                rolle_layout = LAYOUT_NACH_PORT_ROLLE

            if rolle_layout not in GUELTIGE_LAYOUTROLLEN:
                raise PoolFehler(
                    f"Verbindungsart {name!r}: unbekanntes rolle_layout {rolle_layout!r}."
                )

            abbildung = dict(eintrag.get("rolle_layout_map") or {})
            if rolle_layout == LAYOUT_NACH_PORT_ROLLE and not abbildung:
                abbildung = {
                    ROLLE_LEISTUNG: LAYOUT_STRUKTUR,
                    ROLLE_MESSUNG: LAYOUT_ANKER_SEITLICH,
                }
            for rolle, ziel in abbildung.items():
                if ziel not in GUELTIGE_LAYOUTROLLEN or ziel == LAYOUT_NACH_PORT_ROLLE:
                    raise PoolFehler(
                        f"Verbindungsart {name!r}: rolle_layout_map[{rolle!r}] "
                        f"hat den unzulaessigen Wert {ziel!r}."
                    )

            arten[name] = Verbindungsart(
                name=name,
                domaene=str(eintrag.get("domaene", "")),
                gerichtet=bool(eintrag.get("gerichtet", False)),
                bezeichnung=str(eintrag.get("bezeichnung", name)),
                rolle_layout=rolle_layout,
                rolle_layout_map=abbildung,
                rolle_layout_default=str(
                    eintrag.get("rolle_layout_default", ROLLE_LEISTUNG)
                ),
            )
        return arten

    @staticmethod
    def _typen_lesen(
        roh: list, arten: dict[str, Verbindungsart], warnungen: list[str]
    ) -> dict[str, Typ]:
        typen: dict[str, Typ] = {}
        for eintrag in roh:
            name = str(eintrag.get("typ", "")).strip()
            if not name:
                raise PoolFehler("Ein Typeintrag hat kein Feld 'typ'.")
            if name in typen:
                raise PoolFehler(f"Der Typ {name!r} ist mehrfach definiert.")

            ports: dict[str, Port] = {}
            for port_roh in eintrag.get("ports", []):
                port = Pool._port_lesen(name, port_roh, arten, warnungen)
                if port.name in ports:
                    raise PoolFehler(
                        f"Typ {name!r}: Port {port.name!r} ist mehrfach definiert."
                    )
                ports[port.name] = port

            typen[name] = Typ(
                typ=name,
                bezeichnung=str(eintrag.get("bezeichnung", name)),
                kurz=str(eintrag.get("kurz", name)),
                kategorie=str(eintrag.get("kategorie", "")),
                platzierbar=bool(eintrag.get("platzierbar", True)),
                gestellfest_standard=bool(eintrag.get("gestellfest_standard", False)),
                ports=ports,
            )
        return typen

    @staticmethod
    def _port_lesen(
        typ: str, roh: dict, arten: dict[str, Verbindungsart], warnungen: list[str]
    ) -> Port:
        name = str(roh.get("name", "")).strip()
        if not name:
            raise PoolFehler(f"Typ {typ!r}: ein Port hat kein Feld 'name'.")

        art = str(roh.get("art", "")).strip()
        if art not in arten:
            raise PoolFehler(f"Typ {typ!r}, Port {name!r}: unbekannte art {art!r}.")

        richtung = str(roh.get("richtung", "")).strip()
        if richtung not in {"ein", "aus"}:
            raise PoolFehler(
                f"Typ {typ!r}, Port {name!r}: richtung muss 'ein' oder 'aus' sein."
            )

        # Der Schluessel heisst "max"; null bedeutet unbegrenzt. Fehlt das
        # Feld, gilt 1.
        if "max" in roh:
            rohwert = roh["max"]
            hoechstzahl = None if rohwert is None else int(rohwert)
        else:
            hoechstzahl = 1
        if hoechstzahl is not None and hoechstzahl < 1:
            raise PoolFehler(
                f"Typ {typ!r}, Port {name!r}: max muss null oder mindestens 1 sein."
            )

        rolle = roh.get("rolle")
        rolle = str(rolle).strip() if rolle else None
        if rolle and rolle not in {ROLLE_LEISTUNG, ROLLE_MESSUNG}:
            raise PoolFehler(
                f"Typ {typ!r}, Port {name!r}: unbekannte rolle {rolle!r}."
            )
        if rolle and art != "lage":
            warnungen.append(
                f"Typ {typ!r}, Port {name!r}: Feld 'rolle' ist nur bei art 'lage' "
                "vorgesehen und wird ignoriert."
            )

        return Port(
            name=name,
            art=art,
            richtung=richtung,
            max=hoechstzahl,
            pflicht=bool(roh.get("pflicht", False)),
            rolle=rolle,
        )

    # ------------------------------------------------------------------
    # Abfragen
    # ------------------------------------------------------------------

    def typ(self, name: str) -> Typ | None:
        return self.typen.get(name)

    def port(self, typ_name: str, port_name: str) -> Port | None:
        typ = self.typen.get(typ_name)
        return typ.port(port_name) if typ else None

    def platzierbare_typen(self) -> list[Typ]:
        return [t for t in self.typen.values() if t.platzierbar]

    def kategorien(self) -> dict[str, list[Typ]]:
        """Typen nach Kategorie gruppiert, fuer die Palette (E-2)."""
        gruppen: dict[str, list[Typ]] = {}
        for typ in self.platzierbare_typen():
            gruppen.setdefault(typ.kategorie, []).append(typ)
        for liste in gruppen.values():
            liste.sort(key=lambda t: t.bezeichnung)
        return gruppen

    def anzahl_portdefinitionen(self, nur_platzierbar: bool = True) -> int:
        """Grundgesamtheit der Abdeckungskennzahl (v1.3: 71)."""
        quelle = self.platzierbare_typen() if nur_platzierbar else self.typen.values()
        return sum(len(t.ports) for t in quelle)

    def layout_rolle(self, art: str, port_rolle: str | None = None) -> str:
        """Loest die Layoutrolle einer Kante auf (Festlegung L1/L2).

        Bei art 'lage' entscheidet die rolle des Ports: leistung ergibt
        struktur, messung ergibt anker_seitlich.
        """
        verbindungsart = self.verbindungsarten.get(art)
        if verbindungsart is None:
            raise PoolFehler(f"Unbekannte Verbindungsart {art!r}.")
        if verbindungsart.rolle_layout != LAYOUT_NACH_PORT_ROLLE:
            return verbindungsart.rolle_layout
        rolle = port_rolle or verbindungsart.rolle_layout_default
        return verbindungsart.rolle_layout_map.get(rolle, LAYOUT_STRUKTUR)