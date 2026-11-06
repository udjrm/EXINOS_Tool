"""Lesen und Schreiben der Schnittstellendateien components.csv und
connections.csv.

Festlegungen aus Lastenheft 1.2:
- UTF-8, Trennzeichen ';', eine Kopfzeile
- Freitextfelder enthalten kein Semikolon
- beim Import bleiben alle ids erhalten (Bauteile und Verbindungen)
- Materialbahnen stehen als eigene Zeile mit typ = materialbahn und dem
  Kuerzel in der Spalte materialpfad
"""

from __future__ import annotations

import csv
from pathlib import Path

from .modell import TYP_MATERIALBAHN, TYP_RAHMEN, Anlage, Bahn, Bauteil, Verbindung

TRENNZEICHEN = ";"
KODIERUNG_LESEN = "utf-8-sig"
KODIERUNG_SCHREIBEN = "utf-8"

SPALTEN_COMPONENTS = [
    "id",
    "typ",
    "bezeichnung",
    "materialpfad",
    "baugruppe",
    "gestellfest",
    "bemerkung",
]

SPALTEN_CONNECTIONS = [
    "id",
    "von",
    "von_port",
    "nach",
    "nach_port",
    "art",
    "bahn",
]

#: Standardfarben fuer importierte Bahnen, in Reihenfolge des Auftretens.
STANDARDFARBEN = [
    "#1F77B4",
    "#D62728",
    "#2CA02C",
    "#FF7F0E",
    "#9467BD",
    "#8C564B",
]


class CsvFehler(Exception):
    """Eine CSV-Datei ist unbrauchbar oder ein Feld ist unzulaessig."""


def _pruefe_kopfzeile(gelesen: list[str] | None, erwartet: list[str], pfad: Path) -> None:
    if not gelesen:
        raise CsvFehler(f"{pfad.name}: Die Datei ist leer oder hat keine Kopfzeile.")
    fehlend = [spalte for spalte in erwartet if spalte not in gelesen]
    if fehlend:
        raise CsvFehler(
            f"{pfad.name}: Es fehlen die Spalten {', '.join(fehlend)}. "
            f"Erwartet wird: {TRENNZEICHEN.join(erwartet)}"
        )


def _feld(zeile: dict, name: str) -> str:
    wert = zeile.get(name)
    return wert.strip() if isinstance(wert, str) else ""


def _pruefe_freitext(wert: str, pfad_name: str, zeilennummer: int, spalte: str) -> None:
    if TRENNZEICHEN in wert:
        raise CsvFehler(
            f"{pfad_name}, Zeile {zeilennummer}, Spalte {spalte}: "
            f"Freitextfelder duerfen kein {TRENNZEICHEN!r} enthalten."
        )


# ----------------------------------------------------------------------
# Lesen
# ----------------------------------------------------------------------


def lies_components(pfad: str | Path, anlage: Anlage | None = None) -> Anlage:
    """Liest components.csv in eine Anlage.

    Zeilen mit typ = materialbahn werden zu Bahn-Objekten, alle anderen zu
    Bauteilen. Zeilen mit typ = rahmen werden uebersprungen und gemeldet:
    den Rahmen erzeugt ausschliesslich das Backend aus der Spalte
    gestellfest.
    """
    pfad = Path(pfad)
    anlage = anlage if anlage is not None else Anlage()

    with pfad.open("r", encoding=KODIERUNG_LESEN, newline="") as datei:
        leser = csv.DictReader(datei, delimiter=TRENNZEICHEN)
        _pruefe_kopfzeile(leser.fieldnames, SPALTEN_COMPONENTS, pfad)

        farbindex = 0
        for nummer, zeile in enumerate(leser, start=2):
            kennung = _feld(zeile, "id")
            if not kennung:
                continue
            typ = _feld(zeile, "typ")

            for spalte in ("bezeichnung", "bemerkung"):
                _pruefe_freitext(_feld(zeile, spalte), pfad.name, nummer, spalte)

            if typ == TYP_RAHMEN:
                raise CsvFehler(
                    f"{pfad.name}, Zeile {nummer}: Der Typ 'rahmen' gehoert nicht in "
                    "components.csv. Er wird vom Backend aus der Spalte gestellfest "
                    "erzeugt."
                )

            if typ == TYP_MATERIALBAHN:
                anlage.bahn_hinzufuegen(
                    Bahn(
                        id=kennung,
                        bezeichnung=_feld(zeile, "bezeichnung"),
                        kuerzel=_feld(zeile, "materialpfad"),
                        farbe=STANDARDFARBEN[farbindex % len(STANDARDFARBEN)],
                    )
                )
                farbindex += 1
                continue

            anlage.hinzufuegen(
                Bauteil(
                    id=kennung,
                    typ=typ,
                    bezeichnung=_feld(zeile, "bezeichnung"),
                    materialpfad=_feld(zeile, "materialpfad"),
                    baugruppe=_feld(zeile, "baugruppe"),
                    gestellfest=_feld(zeile, "gestellfest"),
                    bemerkung=_feld(zeile, "bemerkung"),
                )
            )
    return anlage


def lies_connections(pfad: str | Path, anlage: Anlage | None = None) -> Anlage:
    """Liest connections.csv. Die ids bleiben unveraendert erhalten."""
    pfad = Path(pfad)
    anlage = anlage if anlage is not None else Anlage()

    with pfad.open("r", encoding=KODIERUNG_LESEN, newline="") as datei:
        leser = csv.DictReader(datei, delimiter=TRENNZEICHEN)
        _pruefe_kopfzeile(leser.fieldnames, SPALTEN_CONNECTIONS, pfad)

        for nummer, zeile in enumerate(leser, start=2):
            kennung = _feld(zeile, "id")
            if not kennung:
                continue
            if kennung in anlage.verbindungen:
                raise CsvFehler(
                    f"{pfad.name}, Zeile {nummer}: Die Verbindungs-id {kennung!r} "
                    "kommt mehrfach vor."
                )
            anlage.verbinden(
                Verbindung(
                    id=kennung,
                    von=_feld(zeile, "von"),
                    von_port=_feld(zeile, "von_port"),
                    nach=_feld(zeile, "nach"),
                    nach_port=_feld(zeile, "nach_port"),
                    art=_feld(zeile, "art"),
                    bahn=_feld(zeile, "bahn"),
                )
            )
    return anlage


def lies_anlage(ordner: str | Path, name: str = "") -> Anlage:
    """Liest ein Paar components.csv und connections.csv aus einem Ordner."""
    ordner = Path(ordner)
    anlage = Anlage(name=name or ordner.name)
    lies_components(ordner / "components.csv", anlage)
    lies_connections(ordner / "connections.csv", anlage)
    return anlage


# ----------------------------------------------------------------------
# Schreiben
# ----------------------------------------------------------------------


def _schreiber(datei, spalten: list[str]) -> csv.DictWriter:
    schreiber = csv.DictWriter(
        datei,
        fieldnames=spalten,
        delimiter=TRENNZEICHEN,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    schreiber.writeheader()
    return schreiber


def schreibe_components(anlage: Anlage, pfad: str | Path) -> None:
    """Schreibt components.csv.

    Die Materialbahnen stehen zuerst, danach die Bauteile in der
    Reihenfolge ihrer Anlage. Fuer die Abnahme ist nur der Inhalt als
    Menge massgeblich, die Zeilenreihenfolge darf abweichen.
    """
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)

    with pfad.open("w", encoding=KODIERUNG_SCHREIBEN, newline="") as datei:
        schreiber = _schreiber(datei, SPALTEN_COMPONENTS)

        for bahn in anlage.bahnen.values():
            _pruefe_freitext(bahn.bezeichnung, pfad.name, 0, "bezeichnung")
            schreiber.writerow(
                {
                    "id": bahn.id,
                    "typ": TYP_MATERIALBAHN,
                    "bezeichnung": bahn.bezeichnung,
                    "materialpfad": bahn.kuerzel,
                    "baugruppe": "",
                    "gestellfest": "",
                    "bemerkung": "",
                }
            )

        for bauteil in anlage.bauteile.values():
            _pruefe_freitext(bauteil.bezeichnung, pfad.name, 0, "bezeichnung")
            _pruefe_freitext(bauteil.bemerkung, pfad.name, 0, "bemerkung")
            schreiber.writerow(
                {
                    "id": bauteil.id,
                    "typ": bauteil.typ,
                    "bezeichnung": bauteil.bezeichnung,
                    "materialpfad": bauteil.materialpfad,
                    "baugruppe": bauteil.baugruppe,
                    "gestellfest": bauteil.gestellfest,
                    "bemerkung": bauteil.bemerkung,
                }
            )


def schreibe_connections(anlage: Anlage, pfad: str | Path) -> None:
    """Schreibt connections.csv in Orientierung aus -> ein."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)

    with pfad.open("w", encoding=KODIERUNG_SCHREIBEN, newline="") as datei:
        schreiber = _schreiber(datei, SPALTEN_CONNECTIONS)
        for verbindung in anlage.verbindungen.values():
            schreiber.writerow(
                {
                    "id": verbindung.id,
                    "von": verbindung.von,
                    "von_port": verbindung.von_port,
                    "nach": verbindung.nach,
                    "nach_port": verbindung.nach_port,
                    "art": verbindung.art,
                    "bahn": verbindung.bahn if verbindung.art == "bahn" else "",
                }
            )


def schreibe_anlage(anlage: Anlage, ordner: str | Path) -> None:
    """Schreibt beide Strukturdateien in einen Austauschordner."""
    ordner = Path(ordner)
    schreibe_components(anlage, ordner / "components.csv")
    schreibe_connections(anlage, ordner / "connections.csv")