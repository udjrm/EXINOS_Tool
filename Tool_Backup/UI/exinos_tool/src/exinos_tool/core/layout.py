"""Automatische Anordnung der Anlage (F-3).

Verfahren nach den Festlegungen L1 bis L6 sowie F1 bis F3:

  Schritt 0  Bahnspur        bahn-Kanten, Tiefe 0, x nach Kettenindex
  Schritt 1  Struktur-BFS    welle, lage(leistung), pneumatik, vakuum.
                             Kind-Tiefe = Eltern-Tiefe + Zweigvorzeichen.
                             Das Vorzeichen wird beim ersten Schritt weg
                             vom Ankerknoten festgelegt und im Zweig
                             beibehalten.
  Schritt 2  Ankerknoten     Fixpunktiteration in Runden. Je Runde:
                               Phase 1: anker_spur (material), Tiefe 0,
                                        danach Strukturbaum vollstaendig
                               Phase 2: anker_seitlich (signal, lage-messung),
                                        Median ueber Partner aus strikt
                                        frueheren Runden
  Schritt 3  Rest           nicht erreichbare Bauteile in einen Block

Tie-Break Struktur: Zweigvorzeichen > Tiefe > alphabetische Elternid.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .modell import Anlage, Verbindung
from .pool import (
    LAYOUT_ANKER_SEITLICH,
    LAYOUT_ANKER_SPUR,
    LAYOUT_STRUKTUR,
    Pool,
)

HERKUNFT_SPUR = "spur"
HERKUNFT_STRUKTUR = "struktur"
HERKUNFT_ANKER_SPUR = "anker_spur"
HERKUNFT_ANKER_SEITLICH = "anker_seitlich"
HERKUNFT_REST = "rest"


@dataclass(frozen=True)
class Einstellungen:
    dx: float = 180.0
    dy: float = 140.0
    dy_spur: float = 900.0
    mindestabstand: float = 150.0
    rest_x: float = -400.0
    rest_dy: float = 120.0


@dataclass
class Platzierung:
    bauteil_id: str
    spur: int
    tiefe: int
    x: float = 0.0
    y: float = 0.0
    runde: int = 0
    herkunft: str = HERKUNFT_REST


@dataclass
class Layoutergebnis:
    platzierungen: dict[str, Platzierung] = field(default_factory=dict)
    meldungen: list[str] = field(default_factory=list)

    def statistik(self) -> dict[str, int]:
        zaehler: Counter[str] = Counter()
        for platzierung in self.platzierungen.values():
            if platzierung.herkunft == HERKUNFT_STRUKTUR:
                schluessel = "struktur_unten" if platzierung.tiefe < 0 else "struktur_oben"
                zaehler[schluessel] += 1
            else:
                zaehler[platzierung.herkunft] += 1
        return dict(zaehler)

    @property
    def restblock(self) -> list[str]:
        return sorted(
            p.bauteil_id
            for p in self.platzierungen.values()
            if p.herkunft == HERKUNFT_REST
        )


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------


def _median_tiefe(werte: list[int]) -> int:
    """Median der Tiefen. Bei gerader Anzahl vom Nullpunkt weg runden (F2).

    Ergibt der Median genau 0, liefert die Funktion 0. Der Aufrufer
    weicht dann auf das positive Vorzeichen aus.
    """
    sortiert = sorted(werte)
    anzahl = len(sortiert)
    if anzahl % 2 == 1:
        return sortiert[anzahl // 2]
    mitte = (sortiert[anzahl // 2 - 1] + sortiert[anzahl // 2]) / 2
    if mitte > 0:
        return math.ceil(mitte)
    if mitte < 0:
        return math.floor(mitte)
    return 0


def _median_x(werte: list[float]) -> float:
    """Median der x-Werte, bei gerader Anzahl das arithmetische Mittel."""
    sortiert = sorted(werte)
    anzahl = len(sortiert)
    if anzahl % 2 == 1:
        return sortiert[anzahl // 2]
    return (sortiert[anzahl // 2 - 1] + sortiert[anzahl // 2]) / 2


def _haeufigste_spur(werte: list[int]) -> int:
    zaehler = Counter(werte)
    hoechste = max(zaehler.values())
    return min(spur for spur, anzahl in zaehler.items() if anzahl == hoechste)


# ----------------------------------------------------------------------
# Hauptklasse
# ----------------------------------------------------------------------


class _Layouter:
    def __init__(self, anlage: Anlage, pool: Pool, einstellungen: Einstellungen):
        self.anlage = anlage
        self.pool = pool
        self.e = einstellungen
        self.ergebnis = Layoutergebnis()
        self.struktur: dict[str, list[Verbindung]] = {}
        self.anker: dict[str, list[tuple[Verbindung, str]]] = {}

    # -- Vorbereitung --------------------------------------------------

    def _rolle(self, verbindung: Verbindung) -> str:
        """Layoutrolle einer Kante. Bei lage entscheidet die Port-rolle (L1)."""
        port_rolle = None
        von_bauteil = self.anlage.bauteile.get(verbindung.von)
        if von_bauteil is not None:
            port = self.pool.port(von_bauteil.typ, verbindung.von_port)
            port_rolle = port.rolle if port else None
        if port_rolle is None:
            nach_bauteil = self.anlage.bauteile.get(verbindung.nach)
            if nach_bauteil is not None:
                port = self.pool.port(nach_bauteil.typ, verbindung.nach_port)
                port_rolle = port.rolle if port else None
        return self.pool.layout_rolle(verbindung.art, port_rolle)

    def _kanten_einordnen(self) -> None:
        for verbindung in self.anlage.verbindungen.values():
            if verbindung.von not in self.anlage.bauteile:
                continue
            if verbindung.nach not in self.anlage.bauteile:
                continue
            rolle = self._rolle(verbindung)
            if rolle == LAYOUT_STRUKTUR:
                self.struktur.setdefault(verbindung.von, []).append(verbindung)
                self.struktur.setdefault(verbindung.nach, []).append(verbindung)
            elif rolle in (LAYOUT_ANKER_SPUR, LAYOUT_ANKER_SEITLICH):
                self.anker.setdefault(verbindung.von, []).append((verbindung, rolle))
                self.anker.setdefault(verbindung.nach, []).append((verbindung, rolle))

    # -- Schritt 0: Bahnspur -------------------------------------------

    def _spuren(self) -> None:
        for spurindex, bahn_id in enumerate(sorted(self.anlage.bahnen)):
            kanten = self.anlage.kanten_der_bahn(bahn_id)
            if not kanten:
                continue
            nachfolger = {k.von: k.nach for k in kanten}
            ziele = {k.nach for k in kanten}
            start = sorted(k.von for k in kanten if k.von not in ziele)
            if not start:
                self.ergebnis.meldungen.append(
                    f"Bahn {bahn_id!r}: kein eindeutiger Anfang, die Spur wird "
                    "nach Bauteil-id geordnet."
                )
                start = [sorted(k.von for k in kanten)[0]]

            aktuell: str | None = start[0]
            index = 0
            besucht: set[str] = set()
            while aktuell and aktuell not in besucht:
                besucht.add(aktuell)
                if aktuell not in self.ergebnis.platzierungen:
                    self.ergebnis.platzierungen[aktuell] = Platzierung(
                        bauteil_id=aktuell,
                        spur=spurindex,
                        tiefe=0,
                        x=index * self.e.dx,
                        runde=0,
                        herkunft=HERKUNFT_SPUR,
                    )
                index += 1
                aktuell = nachfolger.get(aktuell)

    # -- Schritt 1: Struktur-BFS ---------------------------------------

    def _struktur_bfs(self, startknoten: list[str], runde: int) -> None:
        """Breitensuche ueber Strukturkanten ab den gegebenen Knoten.

        Kind-Tiefe = Eltern-Tiefe + Zweigvorzeichen. Das Vorzeichen wird
        beim ersten Schritt vom Startknoten festgelegt und im ganzen Zweig
        beibehalten. Bereits platzierte Knoten werden nicht ueberschrieben.
        """
        # Eintrag der Welle: (bauteil_id, zweigvorzeichen, tiefe, spur, x)
        welle: list[tuple[str, int, int, int, float]] = []
        for knoten in sorted(startknoten):
            p = self.ergebnis.platzierungen[knoten]
            welle.append((knoten, 0, p.tiefe, p.spur, p.x))

        while welle:
            # Je Partner den besten Kandidaten nach Tie-Break behalten.
            # Kandidat: (partner, zweig, tiefe, spur, x, elternid)
            kandidaten: dict[str, tuple] = {}
            for knoten, vorzeichen, eltern_tiefe, spur, x in welle:
                for verbindung in self.struktur.get(knoten, ()):
                    if verbindung.von == knoten:
                        partner, schritt = verbindung.nach, +1
                    else:
                        partner, schritt = verbindung.von, -1
                    if partner in self.ergebnis.platzierungen:
                        continue

                    zweig = schritt if vorzeichen == 0 else vorzeichen
                    tiefe = eltern_tiefe + zweig
                    if tiefe == 0:
                        # Tiefe 0 bleibt Bahnbauteilen und anker_spur vorbehalten.
                        tiefe = zweig

                    kandidat = (partner, zweig, tiefe, spur, x, knoten)
                    vorhanden = kandidaten.get(partner)
                    if vorhanden is None or self._besser(kandidat, vorhanden):
                        kandidaten[partner] = kandidat

            neue_welle: list[tuple[str, int, int, int, float]] = []
            for partner in sorted(kandidaten):
                _id, zweig, tiefe, spur, x, _eltern = kandidaten[partner]
                self.ergebnis.platzierungen[partner] = Platzierung(
                    bauteil_id=partner,
                    spur=spur,
                    tiefe=tiefe,
                    x=x,
                    runde=runde,
                    herkunft=HERKUNFT_STRUKTUR,
                )
                neue_welle.append((partner, zweig, tiefe, spur, x))
            welle = neue_welle

    @staticmethod
    def _besser(kandidat: tuple, vorhanden: tuple) -> bool:
        """Tie-Break: Zweigvorzeichen > Tiefe (Betrag) > alphabetische Elternid.

        Eintraege: (id, zweig, tiefe, spur, x, elternid)
        """

        def schluessel(eintrag: tuple) -> tuple:
            zweig = eintrag[1]
            tiefe = eintrag[2]
            elternid = eintrag[5]
            return (0 if zweig > 0 else 1, abs(tiefe), elternid)

        return schluessel(kandidat) < schluessel(vorhanden)

    # -- Schritt 2: Ankerknoten ----------------------------------------

    def _offene_knoten(self) -> list[str]:
        """Unplatzierte Bauteile, die mindestens eine Ankerkante haben."""
        return [
            b_id
            for b_id in sorted(self.anker)
            if b_id in self.anlage.bauteile
            and b_id not in self.ergebnis.platzierungen
        ]

    def _fruehe_partner(self, b_id: str, runde: int) -> list[tuple[Platzierung, str]]:
        """Ankerpartner aus strikt frueheren Runden (F3)."""
        partner: list[tuple[Platzierung, str]] = []
        for verbindung, rolle in self.anker.get(b_id, []):
            gegen = verbindung.partner(b_id)
            if gegen is None:
                continue
            platzierung = self.ergebnis.platzierungen.get(gegen)
            if platzierung is None or platzierung.runde >= runde:
                continue
            partner.append((platzierung, rolle))
        return partner

    def _anker(self) -> None:
        """Fixpunktiteration. Jede Runde hat zwei Phasen.

        Phase 1 setzt anker_spur-Knoten und baut ihren Strukturbaum vollstaendig
        auf. Phase 2 setzt seitliche Anker nur fuer Knoten, die danach noch
        offen sind. So kann ein seitlicher Anker, der strukturell unter einem
        Spur-Anker haengt, nicht mit einer Fallback-Tiefe den Teilbaum vorgeben.
        """
        runde = 1
        while True:
            geschehen = False

            for b_id in self._offene_knoten():
                if b_id in self.ergebnis.platzierungen:
                    continue
                partner = self._fruehe_partner(b_id, runde)
                spur_partner = [p for p, r in partner if r == LAYOUT_ANKER_SPUR]
                if spur_partner:
                    self._anker_spur_platzieren(b_id, spur_partner, runde)
                    self._struktur_bfs([b_id], runde)
                    geschehen = True

            for b_id in self._offene_knoten():
                if b_id in self.ergebnis.platzierungen:
                    continue
                partner = self._fruehe_partner(b_id, runde)
                if partner:
                    self._anker_seitlich_platzieren(b_id, partner, runde)
                    self._struktur_bfs([b_id], runde)
                    geschehen = True

            if not geschehen:
                break
            runde += 1

    def _anker_spur_platzieren(
        self, b_id: str, partner: list[Platzierung], runde: int
    ) -> None:
        """anker_spur: Fortsetzung der Bahn, Tiefe bleibt 0 (F1)."""
        self.ergebnis.platzierungen[b_id] = Platzierung(
            bauteil_id=b_id,
            spur=_haeufigste_spur([p.spur for p in partner]),
            tiefe=0,
            x=max(p.x for p in partner) + self.e.dx,
            runde=runde,
            herkunft=HERKUNFT_ANKER_SPUR,
        )

    def _anker_seitlich_platzieren(
        self, b_id: str, partner: list[tuple[Platzierung, str]], runde: int
    ) -> None:
        """anker_seitlich: Median ueber die Partner (F2)."""
        tiefe = _median_tiefe([p.tiefe for p, _ in partner])
        if tiefe == 0:
            tiefe = 1  # Fallback auf das positive Vorzeichen (F2)
        self.ergebnis.platzierungen[b_id] = Platzierung(
            bauteil_id=b_id,
            spur=_haeufigste_spur([p.spur for p, _ in partner]),
            tiefe=tiefe,
            x=_median_x([p.x for p, _ in partner]),
            runde=runde,
            herkunft=HERKUNFT_ANKER_SEITLICH,
        )

    # -- Schritt 3: Rest -----------------------------------------------

    def _rest(self) -> None:
        offen = [
            b_id
            for b_id in sorted(self.anlage.bauteile)
            if b_id not in self.ergebnis.platzierungen
        ]
        if not offen:
            return
        self.ergebnis.meldungen.append(
            f"{len(offen)} Bauteile sind ueber keine Kante erreichbar und stehen "
            "im Restblock: " + ", ".join(offen)
        )
        for lauf, b_id in enumerate(offen):
            self.ergebnis.platzierungen[b_id] = Platzierung(
                bauteil_id=b_id,
                spur=0,
                tiefe=0,
                x=self.e.rest_x,
                y=lauf * self.e.rest_dy,
                runde=-1,
                herkunft=HERKUNFT_REST,
            )

    # -- Abschluss -----------------------------------------------------

    def _entzerren(self) -> None:
        """Schiebt Bauteile derselben Zeile auseinander (Mindestabstand)."""
        zeilen: dict[tuple[int, int], list[Platzierung]] = {}
        for platzierung in self.ergebnis.platzierungen.values():
            if platzierung.herkunft == HERKUNFT_REST:
                continue
            zeilen.setdefault((platzierung.spur, platzierung.tiefe), []).append(
                platzierung
            )
        for eintraege in zeilen.values():
            eintraege.sort(key=lambda p: (p.x, p.bauteil_id))
            for vorher, aktuell in zip(eintraege, eintraege[1:]):
                if aktuell.x - vorher.x < self.e.mindestabstand:
                    aktuell.x = vorher.x + self.e.mindestabstand

    def _y_berechnen(self) -> None:
        for platzierung in self.ergebnis.platzierungen.values():
            if platzierung.herkunft == HERKUNFT_REST:
                continue
            # Negative Tiefe liegt unterhalb der Spur, positive oberhalb.
            platzierung.y = (
                platzierung.spur * self.e.dy_spur - platzierung.tiefe * self.e.dy
            )

    def lauf(self) -> Layoutergebnis:
        self._kanten_einordnen()
        self._spuren()
        self._struktur_bfs(
            [
                p.bauteil_id
                for p in self.ergebnis.platzierungen.values()
                if p.herkunft == HERKUNFT_SPUR
            ],
            runde=0,
        )
        self._anker()
        self._rest()
        self._entzerren()
        self._y_berechnen()
        return self.ergebnis


# ----------------------------------------------------------------------


def berechne_layout(
    anlage: Anlage, pool: Pool, einstellungen: Einstellungen | None = None
) -> Layoutergebnis:
    """Berechnet die Anordnung, ohne die Anlage zu veraendern."""
    return _Layouter(anlage, pool, einstellungen or Einstellungen()).lauf()


def ordne_an(
    anlage: Anlage, pool: Pool, einstellungen: Einstellungen | None = None
) -> Layoutergebnis:
    """Berechnet die Anordnung und schreibt sie in die Bauteile (F-3)."""
    ergebnis = berechne_layout(anlage, pool, einstellungen)
    for platzierung in ergebnis.platzierungen.values():
        bauteil = anlage.bauteile.get(platzierung.bauteil_id)
        if bauteil is not None:
            bauteil.x = platzierung.x
            bauteil.y = platzierung.y
    return ergebnis