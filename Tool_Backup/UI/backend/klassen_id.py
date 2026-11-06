# -*- coding: utf-8 -*-
"""
klassen_id.py
Stabile Bezeichner und eindeutige Anzeigenamen fuer Aequivalenzklassen.

Hintergrund
-----------
Die laufende Nummer K01..Kn ergibt sich aus der Sortierung und ist damit
positionsabhaengig: Kommt eine Klasse hinzu oder faellt eine weg,
verschieben sich alle nachfolgenden Nummern. Als Schluessel in
nwa_bewertung.csv waere das gefaehrlich, weil bereits abgegebene
Bewertungen nach einem neuen Lauf still auf andere Klassen fielen.

Dieses Modul erzeugt deshalb:
  klasse_id     stabil, abgeleitet vom alphabetisch kleinsten Mitglied
  klasse_label  eindeutig, lesbar, mit Baugruppe und Vertreter
  reihenfolge   die laufende Nummer, nur noch zur Anzeige

Verwendung
----------
    from klassen_id import benenne_klassen, lade_bauteile, lade_pool_kurz

    bauteile  = lade_bauteile("ZFalter/components.csv")
    pool_kurz = lade_pool_kurz("bauteilpool.json")
    protokoll = []

    benannt = benenne_klassen(klassen, bauteile, pool_kurz, protokoll)

    for k in benannt:
        print(k.klasse_id, k.klasse_label, k.n)
"""

import csv
import json
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


# ----------------------------------------------------------------------
# Datenhaltung
# ----------------------------------------------------------------------

@dataclass
class BenannteKlasse:
    """Eine Aequivalenzklasse mit stabilem Bezeichner."""
    klasse_id: str                      # z. B. "antrieb__Antrieb_AT_h"
    klasse_label: str                   # z. B. "Antrieb Ablage [Antrieb_AT_h]"
    typ: str                            # Pooltyp, z. B. "antrieb"
    vertreter: str                      # alphabetisch kleinste Mitglieds-id
    baugruppe: str                      # gemeinsame Baugruppe oder ""
    mitglieder: List[str] = field(default_factory=list)
    reihenfolge: str = ""               # bisherige Nummer K01..Kn, nur Anzeige

    @property
    def n(self) -> int:
        return len(self.mitglieder)

    @property
    def bauteile_feld(self) -> str:
        """Mitglieder fuer die Spalte 'bauteile' in nwa_vorschlag.csv."""
        return "|".join(self.mitglieder)


class KlassenBenennungsFehler(Exception):
    """Wird ausgeloest, wenn Bezeichner nicht eindeutig sind."""
    pass


# ----------------------------------------------------------------------
# Lader
# ----------------------------------------------------------------------

def lade_bauteile(pfad: str) -> Dict[str, dict]:
    """
    Liest components.csv und liefert bauteil_id -> Zeile als dict.

    Erwartet UTF-8 und Semikolon als Trennzeichen. Zeilen ohne id
    werden uebersprungen.
    """
    bauteile: Dict[str, dict] = {}
    with open(pfad, encoding="utf-8", newline="") as f:
        for zeile in csv.DictReader(f, delimiter=";"):
            kennung = (zeile.get("id") or "").strip()
            if not kennung:
                continue
            bauteile[kennung] = {
                "typ": (zeile.get("typ") or "").strip(),
                "bezeichnung": (zeile.get("bezeichnung") or "").strip(),
                "materialpfad": (zeile.get("materialpfad") or "").strip(),
                "baugruppe": (zeile.get("baugruppe") or "").strip(),
                "gestellfest": (zeile.get("gestellfest") or "").strip(),
                "bemerkung": (zeile.get("bemerkung") or "").strip(),
            }
    return bauteile


def lade_pool_kurz(pfad: str) -> Dict[str, str]:
    """
    Liest bauteilpool.json und liefert typ -> Kurzname.

    Fehlt das Feld "kurz", wird der Typname selbst verwendet.
    """
    with open(pfad, encoding="utf-8") as f:
        pool = json.load(f)
    return {t["typ"]: t.get("kurz", t["typ"]) for t in pool.get("typen", [])}


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------

def _sortiere_stabil(ids: Sequence[str]) -> List[str]:
    """
    Sortiert Bauteil-ids reproduzierbar.

    Bewusst die einfache Python-Sortierung ueber den String, NICHT
    locale.strcoll: Das Ergebnis muss auf jedem Rechner gleich sein,
    sonst wandern die Bezeichner mit der Spracheinstellung.
    """
    return sorted(ids)


def _gemeinsame_baugruppe(mitglieder: Sequence[str],
                          bauteile: Dict[str, dict],
                          protokoll: List[str]) -> str:
    """
    Ermittelt die Baugruppe einer Klasse.

    Alle Mitglieder sollten dieselbe Baugruppe tragen. Weichen sie ab,
    wird die alphabetisch erste genommen und ein INFO protokolliert -
    das deutet meist auf eine unsaubere Pflege der Spalte hin.
    """
    werte = {(bauteile.get(m, {}).get("baugruppe") or "").strip()
             for m in mitglieder}
    werte.discard("")

    if not werte:
        return ""
    if len(werte) == 1:
        return werte.pop()

    gewaehlt = sorted(werte)[0]
    protokoll.append(
        "INFO;klassenbildung;Klasse mit Vertreter {} hat uneinheitliche "
        "Baugruppen ({}) - verwendet wird {}".format(
            _sortiere_stabil(mitglieder)[0], " / ".join(sorted(werte)), gewaehlt))
    return gewaehlt


def _bilde_label(kurz: str, baugruppe: str, vertreter: str) -> str:
    """
    Baut den Anzeigenamen.

    Form:  "<Kurzname> <Baugruppe> [<Vertreter>]"
    Ohne Baugruppe:  "<Kurzname> [<Vertreter>]"

    Der Vertreter in eckigen Klammern macht das Label per Konstruktion
    eindeutig - auch wenn Typ und Baugruppe mehrfach vorkommen.
    """
    teile = [kurz]
    if baugruppe:
        teile.append(baugruppe)
    return "{} [{}]".format(" ".join(teile), vertreter)


# ----------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------

def benenne_klassen(klassen: Dict[str, Sequence[str]],
                    bauteile: Dict[str, dict],
                    pool_kurz: Dict[str, str],
                    protokoll: List[str] = None) -> List[BenannteKlasse]:
    """
    Vergibt stabile Bezeichner fuer alle Klassen.

    Parameter
    ---------
    klassen : dict
        Abbildung bisherige Klassenbezeichnung -> Liste der Bauteil-ids.
        Beispiel: {"K09_Antrieb_Hubachse_El_n1": ["Antrieb_AT_h"], ...}
        Der Schluessel wird nur noch als Anzeige-Reihenfolge uebernommen.
    bauteile : dict
        Abbildung bauteil_id -> Zeile aus components.csv als dict.
        Benoetigt werden die Schluessel "typ" und "baugruppe".
    pool_kurz : dict
        Abbildung typ -> Kurzname aus bauteilpool.json (Feld "kurz").
    protokoll : list, optional
        Liste, in die Zeilen fuer analysis_log.txt angehaengt werden.

    Rueckgabe
    ---------
    Liste von BenannteKlasse, sortiert nach n absteigend, dann nach
    klasse_id - dieselbe Ordnung wie bisher, nur stabil begruendet.

    Ausnahmen
    ---------
    KlassenBenennungsFehler, wenn ids oder Labels nicht eindeutig sind.
    Das darf nicht stillschweigend durchlaufen.
    """
    if protokoll is None:
        protokoll = []

    ergebnis: List[BenannteKlasse] = []

    for alte_bezeichnung, mitglieder_roh in klassen.items():
        mitglieder = _sortiere_stabil(mitglieder_roh)
        if not mitglieder:
            raise KlassenBenennungsFehler(
                "Klasse {} hat keine Mitglieder".format(alte_bezeichnung))

        vertreter = mitglieder[0]

        typen = {bauteile.get(m, {}).get("typ", "") for m in mitglieder}
        if len(typen) != 1:
            raise KlassenBenennungsFehler(
                "Klasse mit Vertreter {} enthaelt mehrere Typen: {}".format(
                    vertreter, sorted(typen)))
        typ = typen.pop()

        baugruppe = _gemeinsame_baugruppe(mitglieder, bauteile, protokoll)
        kurz = pool_kurz.get(typ, typ)

        ergebnis.append(BenannteKlasse(
            klasse_id="{}__{}".format(typ, vertreter),
            klasse_label=_bilde_label(kurz, baugruppe, vertreter),
            typ=typ,
            vertreter=vertreter,
            baugruppe=baugruppe,
            mitglieder=mitglieder,
            reihenfolge=alte_bezeichnung.split("_")[0],
        ))

    # Anzeigeordnung: grosse Klassen zuerst, dann alphabetisch
    ergebnis.sort(key=lambda k: (-k.n, k.klasse_id))

    pruefe_eindeutig(ergebnis)
    protokoll.append(
        "INFO;klassenbildung;{} Klassen benannt, Bezeichner eindeutig".format(
            len(ergebnis)))

    return ergebnis


def pruefe_eindeutig(klassen: Sequence[BenannteKlasse]) -> None:
    """
    Selbsttest: ids und Labels muessen eindeutig sein.

    Beides ist per Konstruktion eindeutig, solange die Bauteil-ids es
    sind (P-1 stellt das sicher). Die Pruefung faengt den Fall ab, dass
    jemand die Bildungsvorschrift spaeter aendert.
    """
    for feld in ("klasse_id", "klasse_label"):
        gesehen = {}
        for k in klassen:
            wert = getattr(k, feld)
            if wert in gesehen:
                raise KlassenBenennungsFehler(
                    "{} nicht eindeutig: '{}' bei Vertreter {} und {}".format(
                        feld, wert, gesehen[wert], k.vertreter))
            gesehen[wert] = k.vertreter


# ----------------------------------------------------------------------
# Selbsttest
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # Ausschnitt Z-Falter: die beiden Regler, die bisher gleich heissen
    test_bauteile = {
        "Regler_Abw":    {"typ": "regler",      "baugruppe": "Abwicklung"},
        "Taktgeber":     {"typ": "regler",      "baugruppe": "Steuerung"},
        "Rolle_1":       {"typ": "umlenkrolle", "baugruppe": ""},
        "Rolle_2":       {"typ": "umlenkrolle", "baugruppe": ""},
        "Antrieb_Tisch": {"typ": "antrieb",     "baugruppe": "Tisch"},
    }
    test_klassen = {
        "K11_Regler_Se_n1":           ["Regler_Abw"],
        "K12_Regler_Se_n1":           ["Taktgeber"],
        "K01_Umlenkrolle_Se_n6":      ["Rolle_2", "Rolle_1"],
        "K06_Antrieb_Hubachse_Se_n1": ["Antrieb_Tisch"],
    }
    test_kurz = {"regler": "Regler", "umlenkrolle": "Umlenkrolle",
                 "antrieb": "Antrieb"}

    log = []
    for k in benenne_klassen(test_klassen, test_bauteile, test_kurz, log):
        print("{:<28} {:<34} n={}  [{}]".format(
            k.klasse_id, k.klasse_label, k.n, k.reihenfolge))
    print()
    for zeile in log:
        print(zeile)