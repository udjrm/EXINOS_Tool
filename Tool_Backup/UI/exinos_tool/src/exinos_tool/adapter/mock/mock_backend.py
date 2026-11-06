"""Mock-Backend: Platzhalter fuer die echte Analyse.

Aufruf (Arbeitsverzeichnis = Austauschordner):
    python -m exinos_tool.adapter.mock.mock_backend <funktion>

Das Programm importiert nichts aus exinos_tool. Es arbeitet nur mit der
Standardbibliothek und laesst sich deshalb auch als Vorlage fuer das
echte Backend lesen.

Alle Werte, die als PLATZHALTER gekennzeichnet sind, sind feste Annahmen
und keine Ergebnisse einer Analyse.

Ausgabe: jede Meldung als SCHWERE;quelle;text auf stdout und in
analysis_log.txt. Fehler beenden das Programm mit Exitcode 1.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

VERSION = "mock-0.3.0"
TYPEN_OHNE_BAUTEIL = frozenset({"materialbahn", "rahmen"})

# PLATZHALTER: Schwellen nach Lastenheft D-5 (relativ zum Maximum).
ABC_SCHWELLE_A = 0.20
ABC_SCHWELLE_B = 0.05

# PLATZHALTER: feste Vorschlaege (0, 1 oder 3). Alles andere gilt als 1.
VORSCHLAG_STANDARD = 1
VORSCHLAG_PLATZHALTER: dict[str, dict[str, int]] = {
    "antrieb": {"VE1": 3, "VE3": 3, "ST1": 3},
    "handhabungssystem": {"VE1": 3, "VE2": 3, "VE3": 3, "VE4": 3, "ST1": 3, "ST2": 3},
    "regler": {"VE1": 0, "ST1": 0},
}

# PLATZHALTER: Parameterliste je Klasse nach D-6. A erhaelt 6, B 3, C 1.
PARAMETER_JE_KLASSE = {"A": 6, "B": 3, "C": 1}

# Spiegel von konfiguration/nwa_kriterien.csv. Ein Test prueft die Gleichheit.
KRITERIEN: list[tuple[str, str, str, str, str, str]] = [
    ("Vereinzelung", "VE1", "MG-BZ", "Ungenauigkeiten in der Masshaltigkeit der Elektrodenblaetter aufgrund ungenauer Bahnzugregelung", "336", "0,4884"),
    ("Vereinzelung", "VE2", "BS-BF", "Beschaedigungen der Elektrodenblaetter aufgrund ungenauer Bahnfuehrung", "160", "0,2326"),
    ("Vereinzelung", "VE3", "MG-BF", "Ungenauigkeiten in der Masshaltigkeit der Elektrodenblaetter aufgrund ungenauer Bahnfuehrung", "112", "0,1628"),
    ("Vereinzelung", "VE4", "BS-BZ", "Beschaedigungen der Elektrodenblaetter aufgrund ungenauer Bahnzugregelung", "80", "0,1163"),
    ("Stapeln", "ST1", "SEP-BZ", "Beschaedigungen des Separators aufgrund ungenauer Bahnzugregelung", "360", "0,5696"),
    ("Stapeln", "ST2", "SEP-BF", "Beschaedigungen des Separators aufgrund ungenauer Bahnfuehrung", "160", "0,2532"),
    ("Stapeln", "ST3", "POS-GR", "Positioniergenauigkeit der Greifer beim Stapeln zu ungenau", "56", "0,0886"),
    ("Stapeln", "ST4", "POS-TI", "Positioniergenauigkeit des Tisches beim Stapeln zu ungenau", "56", "0,0886"),
]

# PLATZHALTER: Parameterkatalog. Name, Bezeichnung, Einheit, Datentyp,
# Standardwert, min, max, auswahl, pflicht, gruppe, beschreibung.
PARAMETER: list[tuple[str, ...]] = [
    ("radius", "Radius", "m", "zahl", "0,05", "0,01", "2", "", "ja", "Geometrie", "Wirkradius der Rolle bzw. Walze"),
    ("breite", "Breite", "m", "zahl", "0,30", "0,05", "3", "", "ja", "Geometrie", "Bahnbreite am Bauteil"),
    ("masse", "Masse", "kg", "zahl", "2", "0,01", "500", "", "ja", "Massen", "Bewegte Masse"),
    ("anzahl", "Anzahl", "-", "ganzzahl", "2", "1", "20", "", "nein", "Geometrie", "Anzahl gleichartiger Elemente"),
    ("regelung", "Regelungsart", "-", "auswahl", "PI", "", "", "P|PI|PID", "nein", "Regelung", "Reglerstruktur"),
    ("bemerkung", "Bemerkung", "-", "text", "", "", "", "", "nein", "Regelung", "Freitext zur Annahme"),
]

SPALTEN_KRITERIEN = ["zielgroesse", "kriterium_id", "kuerzel", "kriterium", "rpz", "gewicht"]
SPALTEN_KLASSEN = ["klasse_id", "klasse_label", "bauteile"]
SPALTEN_VORSCHLAG = ["zielgroesse", "klasse_id", "klasse_label", "bauteile", "kriterium_id", "vorschlag"]
SPALTEN_ERGEBNIS = ["component_id", "klasse_id", "klasse_label", "n", "AS", "PS", "NW", "B_ges", "abc"]
SPALTEN_PARAMETER = [
    "component_id", "parameter", "bezeichnung", "einheit", "datentyp",
    "standardwert", "min", "max", "auswahl", "pflicht", "gruppe", "beschreibung",
]
SPALTEN_PARAMETERWERTE = ["component_id", "parameter", "wert", "quelle"]


class Abbruch(Exception):
    """Die Funktion kann nicht weiterarbeiten. Die Meldung steht im Protokoll."""


class Protokoll:
    def __init__(self, ordner: Path, befehl: str):
        self.ordner = ordner
        self.befehl = befehl
        self.zeilen: list[str] = []
        self.fehler = False

    def _schreibe(self, stufe: str, text: str) -> None:
        zeile = f"{stufe};{self.befehl};{text}"
        print(zeile)
        self.zeilen.append(zeile)

    def info(self, text: str) -> None:
        self._schreibe("INFO", text)

    def warnung(self, text: str) -> None:
        self._schreibe("WARNUNG", text)

    def melde_fehler(self, text: str) -> None:
        self.fehler = True
        self._schreibe("FEHLER", text)

    def abbruch(self, text: str) -> None:
        self.melde_fehler(text)
        raise Abbruch(text)

    def speichern(self) -> None:
        if not self.zeilen:
            return
        with (self.ordner / "analysis_log.txt").open("a", encoding="utf-8", newline="") as datei:
            datei.write("\n".join(self.zeilen) + "\n")


def lies(p: Protokoll, name: str) -> list[dict[str, str]]:
    pfad = p.ordner / name
    if not pfad.exists():
        p.abbruch(f"Datei {name} fehlt im Austauschordner.")
    with pfad.open("r", encoding="utf-8-sig", newline="") as datei:
        return list(csv.DictReader(datei, delimiter=";"))


def schreibe(ordner: Path, name: str, spalten: list[str], zeilen: list[dict[str, str]]) -> None:
    with (ordner / name).open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=spalten, delimiter=";", lineterminator="\n")
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def dezimal(wert: float, nachkommastellen: int = 4) -> str:
    return f"{wert:.{nachkommastellen}f}".replace(".", ",")


def zahl(text: str) -> float:
    return float(text.strip().replace(",", "."))


# ----------------------------------------------------------------------
# Schritt 1: Klassen, DSM, NWA-Vorschlaege
# ----------------------------------------------------------------------


def klassen_und_dsm(ordner: Path, p: Protokoll) -> None:
    komponenten = lies(p, "components.csv")
    verbindungen = lies(p, "connections.csv")

    bauteile = [z for z in komponenten if z["id"] and z["typ"] not in TYPEN_OHNE_BAUTEIL]
    if not bauteile:
        p.abbruch("components.csv enthaelt keine Bauteile.")

    typ_von = {z["id"]: z["typ"] for z in bauteile}
    klassen: dict[str, list[str]] = {}
    for bauteil_id, typ in typ_von.items():
        klassen.setdefault(typ, []).append(bauteil_id)
    klassen_ids = sorted(klassen)
    index = {klasse: i for i, klasse in enumerate(klassen_ids)}

    # PLATZHALTER: je Typ eine Klasse (D-4).
    matrix = [[0] * len(klassen_ids) for _ in klassen_ids]
    for v in verbindungen:
        a = typ_von.get(v["von"])
        b = typ_von.get(v["nach"])
        if a is None or b is None:
            p.warnung(f"Verbindung {v['id']}: {v['von']} oder {v['nach']} fehlt in components.csv.")
            continue
        if a == b:
            continue
        # Direkte Verbindung in beliebiger Richtung ergibt 3, sonst 0 (D-4).
        matrix[index[a]][index[b]] = 3
        matrix[index[b]][index[a]] = 3

    schreibe(
        ordner,
        "classes.csv",
        SPALTEN_KLASSEN,
        [
            {"klasse_id": k, "klasse_label": k, "bauteile": "|".join(sorted(klassen[k]))}
            for k in klassen_ids
        ],
    )
    schreibe(
        ordner,
        "dsm_matrix.csv",
        ["klasse_id", *klassen_ids],
        [
            {
                "klasse_id": k,
                **{
                    j: "X" if k == j else str(matrix[index[k]][index[j]])
                    for j in klassen_ids
                },
            }
            for k in klassen_ids
        ],
    )
    schreibe(
        ordner,
        "nwa_kriterien.csv",
        SPALTEN_KRITERIEN,
        [dict(zip(SPALTEN_KRITERIEN, eintrag)) for eintrag in KRITERIEN],
    )

    zielgroessen = list(dict.fromkeys(eintrag[0] for eintrag in KRITERIEN))
    vorschlaege: list[dict[str, str]] = []
    for zielgroesse in zielgroessen:
        kriterien_ids = [e[1] for e in KRITERIEN if e[0] == zielgroesse]
        for klasse in klassen_ids:
            for kid in kriterien_ids:
                vorschlaege.append(
                    {
                        "zielgroesse": zielgroesse,
                        "klasse_id": klasse,
                        "klasse_label": klasse,
                        "bauteile": "|".join(sorted(klassen[klasse])),
                        "kriterium_id": kid,
                        "vorschlag": str(VORSCHLAG_PLATZHALTER.get(klasse, {}).get(kid, VORSCHLAG_STANDARD)),
                    }
                )
    schreibe(ordner, "nwa_vorschlag.csv", SPALTEN_VORSCHLAG, vorschlaege)

    p.info(
        f"{len(klassen_ids)} Klassen aus {len(bauteile)} Bauteilen, "
        f"DSM {len(klassen_ids)}x{len(klassen_ids)}, Zielgroessen: {', '.join(zielgroessen)}."
    )


# ----------------------------------------------------------------------
# Schritt 2: NWA-Bewertung, AS, PS, NW, B_ges, ABC
# ----------------------------------------------------------------------


def nwa_und_abc(ordner: Path, p: Protokoll) -> None:
    klassen_zeilen = lies(p, "classes.csv")
    dsm_zeilen = lies(p, "dsm_matrix.csv")
    kriterien_zeilen = lies(p, "nwa_kriterien.csv")
    bewertung_zeilen = lies(p, "nwa_bewertung.csv")

    zielgroessen = {z["zielgroesse"] for z in bewertung_zeilen}
    if len(zielgroessen) != 1:
        p.abbruch("nwa_bewertung.csv muss genau eine Zielgroesse enthalten.")
    zielgroesse = zielgroessen.pop()

    gewichte = {
        z["kriterium_id"]: zahl(z["gewicht"])
        for z in kriterien_zeilen
        if z["zielgroesse"] == zielgroesse
    }
    if not gewichte:
        p.abbruch(f"Die Zielgroesse {zielgroesse!r} steht nicht in nwa_kriterien.csv.")

    bewertung: dict[tuple[str, str], int] = {}
    for z in bewertung_zeilen:
        try:
            wert = int(z["bewertung"])
        except ValueError:
            p.abbruch(f"Bewertung {z['bewertung']!r} ist keine ganze Zahl.")
        if wert not in (0, 1, 3):
            p.abbruch(f"Bewertung {wert} ist unzulaessig, erlaubt sind 0, 1 und 3.")
        bewertung[(z["klasse_id"], z["kriterium_id"])] = wert

    klassen = {z["klasse_id"]: z for z in klassen_zeilen}
    for klasse in klassen:
        for kid in gewichte:
            if (klasse, kid) not in bewertung:
                p.abbruch(f"Bewertung fehlt: Klasse {klasse}, Kriterium {kid}.")

    dsm = {z["klasse_id"]: z for z in dsm_zeilen}
    ids = list(klassen)
    as_ = {k: sum(int(dsm[k][j]) for j in ids if j != k) for k in ids}
    ps_ = {k: sum(int(dsm[j][k]) for j in ids if j != k) for k in ids}
    nw = {k: sum(bewertung[(k, kid)] * gewichte[kid] for kid in gewichte) for k in ids}
    b_ges = {k: as_[k] * nw[k] for k in ids}

    maximum = max(b_ges.values(), default=0.0)
    if maximum <= 0:
        p.warnung("Kein B_ges groesser 0. Alle Klassen werden als C eingestuft.")

    def stufe(wert: float) -> str:
        if maximum <= 0:
            return "C"
        if wert >= ABC_SCHWELLE_A * maximum:
            return "A"
        if wert >= ABC_SCHWELLE_B * maximum:
            return "B"
        return "C"

    zeilen: list[dict[str, str]] = []
    for k in ids:
        bauteile = [b for b in klassen[k]["bauteile"].split("|") if b]
        abc = stufe(b_ges[k])
        p.info(
            f"Klasse {k}: AS={as_[k]} PS={ps_[k]} NW={dezimal(nw[k])} "
            f"B_ges={dezimal(b_ges[k])} ABC={abc}"
        )
        for bauteil in bauteile:
            zeilen.append(
                {
                    "component_id": bauteil,
                    "klasse_id": k,
                    "klasse_label": klassen[k]["klasse_label"],
                    "n": str(len(bauteile)),
                    "AS": str(as_[k]),
                    "PS": str(ps_[k]),
                    "NW": dezimal(nw[k]),
                    "B_ges": dezimal(b_ges[k]),
                    "abc": abc,
                }
            )
    zeilen.sort(key=lambda z: z["component_id"])
    schreibe(ordner, "analysis_result.csv", SPALTEN_ERGEBNIS, zeilen)
    p.info(f"Zielgroesse {zielgroesse}: {len(zeilen)} Bauteile eingestuft.")


# ----------------------------------------------------------------------
# Parameteranfrage
# ----------------------------------------------------------------------


def parameteranfrage(ordner: Path, p: Protokoll) -> None:
    ergebnis = lies(p, "analysis_result.csv")
    zeilen: list[dict[str, str]] = []
    for z in ergebnis:
        stufe = z["abc"].strip()
        if stufe not in PARAMETER_JE_KLASSE:
            p.abbruch(f"Bauteil {z['component_id']}: unbekannte ABC-Klasse {stufe!r}.")
        for eintrag in PARAMETER[: PARAMETER_JE_KLASSE[stufe]]:
            (name, bezeichnung, einheit, datentyp, standard,
             minimum, maximum, auswahl, pflicht, gruppe, beschreibung) = eintrag
            zeilen.append(
                {
                    "component_id": z["component_id"],
                    "parameter": name,
                    "bezeichnung": bezeichnung,
                    "einheit": einheit,
                    "datentyp": datentyp,
                    "standardwert": standard,
                    "min": minimum,
                    "max": maximum,
                    "auswahl": auswahl,
                    "pflicht": pflicht,
                    "gruppe": gruppe,
                    "beschreibung": beschreibung,
                }
            )
    schreibe(ordner, "parameter_request.csv", SPALTEN_PARAMETER, zeilen)
    p.info(f"{len(ergebnis)} Bauteile, {len(zeilen)} abzufragende Parameter.")


# ----------------------------------------------------------------------
# Code-Erzeugung (Platzhalter)
# ----------------------------------------------------------------------


def amesim_code_erzeugen(ordner: Path, p: Protokoll) -> None:
    komponenten = lies(p, "components.csv")
    verbindungen = lies(p, "connections.csv")
    parameter = lies(p, "parameters.csv")

    bauteile = [z for z in komponenten if z["id"] and z["typ"] not in TYPEN_OHNE_BAUTEIL]
    werte: dict[str, dict[str, str]] = {}
    for z in parameter:
        werte.setdefault(z["component_id"], {})[z["parameter"]] = z["wert"]

    ohne = [b["id"] for b in bauteile if b["id"] not in werte]
    if ohne:
        p.warnung("Ohne Parameter: " + ", ".join(ohne))

    zeilen = [
        "# PLATZHALTER - Code-Erzeugung noch nicht implementiert.",
        "# Diese Datei ist kein lauffaehiger Amesim-Code.",
        f"# Projekt: {ordner.name}",
        f"# Erzeugt: {dt.datetime.now().isoformat(timespec='seconds')} mit {VERSION}",
        "#",
        "# Bauteile (id, typ, Parameter):",
    ]
    for b in bauteile:
        paare = "; ".join(f"{n}={w}" for n, w in sorted(werte.get(b["id"], {}).items()))
        zeilen.append(f"# {b['id']} ({b['typ']}): {paare or 'keine Parameter'}")
    zeilen += ["#", "# Verbindungen:"]
    for v in verbindungen:
        zeilen.append(
            f"# {v['id']} ({v['art']}): {v['von']}.{v['von_port']} -> {v['nach']}.{v['nach_port']}"
        )

    text = "\n".join(zeilen) + "\n"
    compile(text, "amesim_modell.py", "exec")  # Syntaxpruefung
    (ordner / "amesim_modell.py").write_text(text, encoding="utf-8")

    p.warnung("Platzhalter: Die Datei enthaelt keinen lauffaehigen Amesim-Code.")
    p.info(f"amesim_modell.py geschrieben: {len(bauteile)} Bauteile, {len(verbindungen)} Verbindungen.")


# ----------------------------------------------------------------------
# Einstieg
# ----------------------------------------------------------------------

FUNKTIONEN = {
    "klassen_und_dsm": klassen_und_dsm,
    "nwa_und_abc": nwa_und_abc,
    "parameteranfrage": parameteranfrage,
    "amesim_code_erzeugen": amesim_code_erzeugen,
}


def _utf8_ausgabe() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def main(argumente: list[str] | None = None) -> int:
    _utf8_ausgabe()
    argumente = sys.argv[1:] if argumente is None else list(argumente)
    if not argumente:
        print("FEHLER;aufruf;Kein Befehl angegeben.")
        return 1

    befehl = argumente[0]
    if befehl == "version":
        print(f"INFO;version;{VERSION}")
        return 0
    if befehl not in FUNKTIONEN:
        print(f"FEHLER;aufruf;Unbekannter Befehl {befehl!r}.")
        return 1

    ordner = Path.cwd()
    protokoll = Protokoll(ordner, befehl)
    try:
        FUNKTIONEN[befehl](ordner, protokoll)
    except Abbruch:
        pass
    except Exception as fehler:  # nie einen Traceback ueber die Grenze geben
        protokoll.melde_fehler(f"Unerwarteter Fehler: {type(fehler).__name__}: {fehler}")
    finally:
        protokoll.speichern()
    return 1 if protokoll.fehler else 0


if __name__ == "__main__":
    sys.exit(main())