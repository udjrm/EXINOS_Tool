"""Anwendungssteuerung (Schicht 3, ohne Qt).

Der Controller ist die einzige Stelle, die den Projektzustand veraendert.
Lange Backend-Aufrufe liefert er als Auftrag (siehe worker.py).
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..adapter.basis import Backend, Ergebnis
from ..core.io_csv import schreibe_anlage
from ..core.io_projekt import Projekt, lade, speichere
from ..core.modell import Anlage, Bauteil, Verbindung
from ..core.nwa import Kriterium
from ..core.pool import Pool
from ..core.pruefung import Pruefbericht, pruefe
from ..core.zahlen import ZahlFehler, ganzzahl_lesen, zahl_lesen, zahl_schreiben
from .befehle import (
    BauteilDuplizieren,
    BauteilEntfernen,
    BauteilHinzufuegen,
    BauteilUmbenennen,
    BauteilVerschieben,
    Befehlsstapel,
    EigenschaftSetzen,
    VerbindungEntfernen,
    VerbindungHinzufuegen,
)
from .worker import Auftrag
from .zustand import (
    Freigabe,
    Schritt,
    Zustand,
    ergebnis_aktuell,
    freigaben_fuer,
    pruefung_gueltig,
    veraltet,
)

ERLAUBTE_BEWERTUNGEN = (0, 1, 3)
REIHENFOLGE_SCHWERE = {"FEHLER": 0, "WARNUNG": 1, "HINWEIS": 2, "INFO": 3}


class SchrittFehler(Exception):
    """Ein Schritt ist im aktuellen Zustand nicht erlaubt."""


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------


def _lies(pfad: Path) -> list[dict[str, str]]:
    with pfad.open("r", encoding="utf-8-sig", newline="") as datei:
        return [dict(zeile) for zeile in csv.DictReader(datei, delimiter=";")]


def _schreibe(pfad: Path, spalten: list[str], zeilen: list[dict[str, str]]) -> None:
    with pfad.open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.DictWriter(
            datei, fieldnames=spalten, delimiter=";", lineterminator="\n"
        )
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def _schluessel(bauteil_id: str, parameter: str) -> str:
    return f"{bauteil_id}|{parameter}"


def protokoll_lesen(text: str) -> list[tuple[str, str, str]]:
    """Liest analysis_log.txt. Zeilen ohne Praefix gelten als INFO (Festlegung)."""
    eintraege: list[tuple[str, str, str]] = []
    for zeile in text.splitlines():
        if not zeile.strip():
            continue
        teile = zeile.split(";", 2)
        if len(teile) == 3 and teile[0] in REIHENFOLGE_SCHWERE:
            eintraege.append((teile[0], teile[1], teile[2]))
        else:
            eintraege.append(("INFO", "", zeile))
    eintraege.sort(key=lambda e: REIHENFOLGE_SCHWERE[e[0]])
    return eintraege


def pruefe_wert(zeile: dict[str, str], roh: str) -> tuple[str | None, str]:
    """Prueft einen Eingabewert gegen die Abfrage (Q-2).

    Gibt (Fehlermeldung oder None, normierter Wert) zurueck.
    """
    wert = roh.strip()
    if ";" in wert:
        return "Ein Wert darf kein Semikolon enthalten.", wert

    datentyp = zeile.get("datentyp", "text")
    if datentyp == "text":
        return None, wert

    if datentyp == "auswahl":
        optionen = [o for o in zeile.get("auswahl", "").split("|") if o]
        if wert not in optionen:
            return f"Erlaubt sind: {' | '.join(optionen)}.", wert
        return None, wert

    if not wert:
        return "Der Wert fehlt.", wert

    try:
        if datentyp == "ganzzahl":
            zahl: float | int = ganzzahl_lesen(wert)
        else:
            zahl = zahl_lesen(wert)
    except ZahlFehler as fehler:
        return str(fehler), wert

    if zahl is None:
        return "Der Wert fehlt.", wert

    minimum = zahl_lesen(zeile.get("min") or None)
    maximum = zahl_lesen(zeile.get("max") or None)
    if minimum is not None and zahl < minimum:
        return f"Der Wert liegt unter dem Minimum {zeile['min']}.", wert
    if maximum is not None and zahl > maximum:
        return f"Der Wert liegt über dem Maximum {zeile['max']}.", wert

    if datentyp == "zahl":
        return None, zahl_schreiben(float(zahl))
    return None, str(int(zahl))


# ----------------------------------------------------------------------
# Controller
# ----------------------------------------------------------------------


class Controller:
    def __init__(
        self,
        pool: Pool,
        backend: Backend,
        austauschbasis: Path,
        kriterien: dict[str, list[Kriterium]],
        projekt: Projekt | None = None,
    ) -> None:
        self.pool = pool
        self.backend = backend
        self.austauschbasis = Path(austauschbasis)
        self.kriterien = kriterien
        self.projekt = projekt or Projekt()
        self.projekt.pool_version = pool.version
        self._befehle = Befehlsstapel(self.projekt.anlage)
        self._pruefung_fp: str | None = None
        self._pruefung_ok = False
        self._struktur_fp: str | None = None
        self._abc_fp: str | None = None
        # Zielordner fuer den Export, einmal gewaehlt und dann gemerkt.
        self.export_basis: Path | None = None
        self._analyse_ordner: Path | None = None

    # ------------------------------------------------------------------
    # Zustand
    # ------------------------------------------------------------------

    @property
    def anlage(self) -> Anlage:
        return self.projekt.anlage

    def zustand(self) -> Zustand:
        return Zustand(
            struktur_fingerabdruck=self.anlage.strukturfingerabdruck(),
            pruefung_fingerabdruck=self._pruefung_fp,
            pruefung_ok=self._pruefung_ok,
            struktur_analyse_fingerabdruck=self._struktur_fp,
            abc_fingerabdruck=self._abc_fp,
            parameter_vollstaendig=self.parameter_vollstaendig(),
        )

    def freigaben(self) -> dict[Schritt, Freigabe]:
        return freigaben_fuer(self.zustand())

    def aktueller_ordner(self) -> Path:
        if self._analyse_ordner is None:
            self._analyse_ordner = self.austauschbasis / self.export_ordnername()
        return self._analyse_ordner

    def _ordner(self) -> Path:
        ordner = self.aktueller_ordner()
        ordner.mkdir(parents=True, exist_ok=True)
        return ordner

    # ------------------------------------------------------------------
    # Aufbau (Schritt 1) ueber den Befehlsstapel
    # ------------------------------------------------------------------

    def bauteil_anlegen(self, bauteil: Bauteil) -> None:
        self._befehle.ausfuehren(BauteilHinzufuegen(bauteil))

    def verbindung_anlegen(self, verbindung: Verbindung) -> None:
        self._befehle.ausfuehren(VerbindungHinzufuegen(verbindung))

    def bauteil_entfernen(self, bauteil_id: str) -> None:
        self._befehle.ausfuehren(BauteilEntfernen(bauteil_id))

    def verbindung_entfernen(self, verbindung_id: str) -> None:
        self._befehle.ausfuehren(VerbindungEntfernen(verbindung_id))

    def bauteil_verschieben(self, bauteil_id: str, neu: tuple[float, float]) -> None:
        self._befehle.ausfuehren(BauteilVerschieben(bauteil_id, neu))

    def bauteil_umbenennen(self, alt: str, neu: str) -> None:
        self._befehle.ausfuehren(BauteilUmbenennen(alt, neu))

    def bauteil_duplizieren(self, bauteil_id: str) -> str:
        """Dupliziert ein Bauteil und gibt die neue id zurueck."""
        typ = self.anlage.bauteile[bauteil_id].typ
        neue_id = self.anlage.freie_id(typ)
        self._befehle.ausfuehren(BauteilDuplizieren(bauteil_id, neue_id))
        return neue_id

    def eigenschaft_setzen(self, art: str, objekt_id: str, feld: str, wert: object) -> None:
        self._befehle.ausfuehren(EigenschaftSetzen(art, objekt_id, feld, wert))

    def rueckgaengig(self) -> bool:
        return self._befehle.rueckgaengig()

    def wiederholen(self) -> bool:
        return self._befehle.wiederholen()

    @property
    def befehlsstapel(self) -> Befehlsstapel:
        return self._befehle

    def verbindung_moeglich(self, a_bauteil, a_port, b_bauteil, b_port):
        """Prueft, ob eine Verbindung erlaubt ist. Nutzt die Kernregeln."""
        from ..core.pruefung import verbindung_moeglich as _pruefen

        return _pruefen(self.anlage, self.pool, a_bauteil, a_port, b_bauteil, b_port)

    def verbindung_ziehen(self, a_bauteil, a_port, b_bauteil, b_port, bahn=""):
        """Legt eine Verbindung an, wenn sie erlaubt ist. Gibt (ok, grund) zurueck."""
        from ..core.modell import Verbindung

        erlaubt, grund, orientierung = self.verbindung_moeglich(
            a_bauteil, a_port, b_bauteil, b_port
        )
        if not erlaubt:
            return False, grund

        von, von_port, nach, nach_port = orientierung
        art = self.pool.port(self.anlage.bauteile[von].typ, von_port).art
        verbindung = Verbindung(
            id=self._freie_verbindungs_id(),
            von=von,
            von_port=von_port,
            nach=nach,
            nach_port=nach_port,
            art=art,
            bahn=bahn if art == "bahn" else "",
        )
        self.verbindung_anlegen(verbindung)
        return True, verbindung.id

    def _freie_verbindungs_id(self) -> str:
        nummer = 1
        while f"V{nummer:02d}" in self.anlage.verbindungen:
            nummer += 1
        return f"V{nummer:02d}"

    def verbindung_bahn_setzen(self, verbindung_id: str, bahn: str) -> None:
        self.eigenschaft_setzen("verbindung", verbindung_id, "bahn", bahn)

    def bauteile_entfernen(self, bauteil_ids: list[str]) -> None:
        """Entfernt mehrere Bauteile als einen Undo-Schritt."""
        ids = [b for b in bauteil_ids if b in self.anlage.bauteile]
        if not ids:
            return
        with self._befehle.makro(f"{len(ids)} Bauteile entfernen"):
            for bauteil_id in ids:
                self._befehle.ausfuehren(BauteilEntfernen(bauteil_id))

    def bauteile_duplizieren(self, bauteil_ids: list[str]) -> list[str]:
        """Dupliziert mehrere Bauteile als einen Undo-Schritt. Gibt die neuen ids zurueck."""
        ids = [b for b in bauteil_ids if b in self.anlage.bauteile]
        if not ids:
            return []
        neue: list[str] = []
        with self._befehle.makro(f"{len(ids)} Bauteile duplizieren"):
            for bauteil_id in ids:
                typ = self.anlage.bauteile[bauteil_id].typ
                neue_id = self.anlage.freie_id(typ)
                self._befehle.ausfuehren(BauteilDuplizieren(bauteil_id, neue_id))
                neue.append(neue_id)
        return neue

    # ------------------------------------------------------------------
    # Export der Struktur-CSVs (Abnahme 3)
    # ------------------------------------------------------------------

    def export_ordnername(self) -> str:
        """Baut 'NAME_DDMMYYYY_HHMM', z. B. EXINOS_05112026_1837."""
        import datetime as _dt
        import re

        roh = self.anlage.name or "Anlage"
        sauber = re.sub(r"[^A-Za-z0-9_-]+", "_", roh).strip("_") or "Anlage"
        zeit = _dt.datetime.now().strftime("%d%m%Y_%H%M")
        return f"{sauber}_{zeit}"

    def exportieren(self, zielbasis) -> tuple[bool, str]:
        """Schreibt components.csv und connections.csv.

        Gibt (erfolg, meldung) zurueck. Bei Erfolg ist meldung der Pfad
        des angelegten Ordners. Export nur bei fehlerfreier Pruefung.
        """
        # Immer frisch pruefen, damit der Export nie veraltet ist.
        bericht = self.pruefen()
        if not bericht.exportfaehig:
            fehler, warnungen, _ = bericht.zusammenfassung()
            return (
                False,
                f"Export nicht moeglich: {fehler} Fehler, {warnungen} Warnung(en). "
                "Bitte zuerst die Pruefung bereinigen.",
            )

        basis = Path(zielbasis)
        basis.mkdir(parents=True, exist_ok=True)
        name = self.export_ordnername()
        ordner = basis / name
        nummer = 2
        while ordner.exists():
            ordner = basis / f"{name}_{nummer:02d}"
            nummer += 1
        ordner.mkdir(parents=True, exist_ok=True)

        try:
            schreibe_anlage(self.anlage, ordner)
        except Exception as fehler:
            return False, f"Schreiben fehlgeschlagen: {fehler}"
        self._analyse_ordner = ordner
        return True, str(ordner)

    def projektname_setzen(self, name: str) -> None:
        self.anlage.name = name.strip()
        self._analyse_ordner = None

    # ------------------------------------------------------------------
    # Materialbahnen (Schritt 1.5)
    # ------------------------------------------------------------------

    def bahnen(self) -> list:
        """Alle Bahnen der Anlage, nach id sortiert."""
        return [self.anlage.bahnen[k] for k in sorted(self.anlage.bahnen)]

    def bahn_anlegen(self, bahn_id: str, bezeichnung: str, kuerzel: str, farbe: str):
        """Legt eine Materialbahn an. kuerzel ist der Materialpfad (An/Ka/El/Se)."""
        from ..core.modell import Bahn

        if bahn_id in self.anlage.bahnen:
            raise KeyError(f"Bahn-id {bahn_id!r} ist bereits vergeben.")
        bahn = Bahn(id=bahn_id, bezeichnung=bezeichnung, kuerzel=kuerzel, farbe=farbe)
        self.anlage.bahn_hinzufuegen(bahn)
        return bahn

    def bahn_aendern(self, bahn_id: str, bezeichnung: str, kuerzel: str, farbe: str) -> None:
        bahn = self.anlage.bahnen[bahn_id]
        bahn.bezeichnung = bezeichnung
        bahn.kuerzel = kuerzel
        bahn.farbe = farbe

    def bahn_entfernen(self, bahn_id: str) -> None:
        """Entfernt eine Bahn. Verbindungen, die sie nutzen, verlieren ihre Zuordnung."""
        self.anlage.bahnen.pop(bahn_id, None)
        for verbindung in self.anlage.verbindungen.values():
            if verbindung.art == "bahn" and verbindung.bahn == bahn_id:
                verbindung.bahn = ""

    # ------------------------------------------------------------------
    # Pruefung (Schritt 2)
    # ------------------------------------------------------------------

    def pruefen(self) -> Pruefbericht:
        bericht = pruefe(self.anlage, self.pool)
        self._pruefung_fp = self.anlage.strukturfingerabdruck()
        self._pruefung_ok = bericht.exportfaehig
        return bericht

    # ------------------------------------------------------------------
    # Struktur-Analyse, Stufe 1
    # ------------------------------------------------------------------

    def struktur_auftrag(self) -> Auftrag:
        if not pruefung_gueltig(self.zustand()):
            raise SchrittFehler("Vor der NWA ist eine Prüfung ohne Fehler nötig.")
        fp = self.anlage.strukturfingerabdruck()
        ordner = self._ordner()
        fehlend = [
            name
            for name in ("components.csv", "connections.csv")
            if not (ordner / name).is_file()
        ]
        if fehlend:
            raise SchrittFehler(
                "Die exportierten Eingabedateien fehlen: " + ", ".join(fehlend)
            )
        return Auftrag(
            "klassen_und_dsm",
            ordner,
            self.backend.klassen_und_dsm,
            lambda e: self._struktur_abschliessen(e, fp, ordner),
        )

    def struktur_analysieren(self) -> Ergebnis:
        """Synchrone Variante, z. B. fuer Skripte und Tests."""
        auftrag = self.struktur_auftrag()
        return auftrag.abschliessen(auftrag.ausfuehren())

    def _struktur_aktuell(self) -> bool:
        return (
            self._struktur_fp is not None
            and self._struktur_fp == self.anlage.strukturfingerabdruck()
        )

    def _struktur_abschliessen(self, ergebnis: Ergebnis, fp: str, ordner: Path) -> Ergebnis:
        if not ergebnis.erfolg:
            return ergebnis
        try:
            self.projekt.analyseergebnis["struktur"] = {
                "fingerabdruck": fp,
                "klassen": _lies(ordner / "classes.csv"),
                "vorschlaege": [],
            }
            self._struktur_fp = fp
            self._abc_fp = None
        except FileNotFoundError as fehler:
            return Ergebnis(False, f"Ausgabedatei fehlt: {Path(fehler.filename).name}")
        return ergebnis

    # ------------------------------------------------------------------
    # NWA-Bewertung und Stufe 2
    # ------------------------------------------------------------------

    def zielgroessen(self) -> list[str]:
        return sorted(self.kriterien.keys())

    def kriterien_fuer(self, zielgroesse: str) -> list[Kriterium]:
        if zielgroesse not in self.kriterien:
            raise SchrittFehler(f"Die Zielgröße {zielgroesse!r} ist nicht bekannt.")
        return list(self.kriterien[zielgroesse])

    def klassen(self) -> list[dict[str, str]]:
        return list(self.projekt.analyseergebnis.get("struktur", {}).get("klassen", []))

    def dsm_matrix(self) -> list[dict[str, str]]:
        """Liest die DSM-Matrix fuer die Pruefung in der Oberflaeche."""
        pfad = self.aktueller_ordner() / "dsm_matrix.csv"
        if not pfad.exists():
            return []
        return _lies(pfad)

    def nwa_ergebnis(self) -> list[dict[str, str]]:
        pfad = self.aktueller_ordner() / "nwa_klassen.csv"
        if not pfad.exists():
            return []
        return _lies(pfad)

    def nwa_auftrag(self) -> Auftrag:
        """Backend-Auftrag für die NWA-Stufe."""
        ordner = self._ordner()
        return Auftrag(
            "nwa",
            ordner,
            self.backend.nwa,
            lambda e: e,
        )

    def nwa_analysieren(self) -> Ergebnis:
        """Fuehrt nur nwa.py aus."""
        auftrag = self.nwa_auftrag()
        return auftrag.abschliessen(auftrag.ausfuehren())

    def abc_auftrag(self) -> Auftrag:
        ordner = self._ordner()
        fp = self.anlage.strukturfingerabdruck()
        return Auftrag(
            "abc",
            ordner,
            self.backend.abc,
            lambda e: self._abc_abschliessen(e, fp, ordner),
        )

    def abc_analysieren(self) -> Ergebnis:
        """Fuehrt nur abc.py aus und liest dessen Ergebnis ein."""
        auftrag = self.abc_auftrag()
        return auftrag.abschliessen(auftrag.ausfuehren())

    def _abc_abschliessen(self, ergebnis: Ergebnis, fp: str, ordner: Path) -> Ergebnis:
        if not ergebnis.erfolg:
            return ergebnis
        try:
            self.projekt.analyseergebnis["abc"] = {
                "fingerabdruck": fp,
                "ergebnis": _lies(ordner / "analysis_result.csv"),
            }
            self._abc_fp = fp
        except FileNotFoundError as fehler:
            return Ergebnis(False, f"Ausgabedatei fehlt: {Path(fehler.filename).name}")
        return ergebnis

    # ------------------------------------------------------------------
    # Parameter (Schritt 5)
    # ------------------------------------------------------------------

    def abc_ergebnis(self) -> list[dict[str, str]]:
        return list(self.projekt.analyseergebnis.get("abc", {}).get("ergebnis", []))

    def parameter_anfrage(self) -> list[dict[str, str]]:
        """Liest parameter_request.csv, wenn sie existiert. Ruft nicht zustand() auf."""
        ordner = self.aktueller_ordner()
        if not (ordner / "parameter_request.csv").exists():
            return []
        try:
            return _lies(ordner / "parameter_request.csv")
        except FileNotFoundError:
            return []

    def parameter_auftrag(self) -> Auftrag:
        """Backend-Auftrag für Parameteranfrage."""
        ordner = self._ordner()
        return Auftrag(
            "parameteranfrage",
            ordner,
            self.backend.parameteranfrage,
            lambda e: self._parameter_abschliessen(e, ordner),
        )

    def parameter_abfragen(self) -> Ergebnis:
        """Synchrone Variante."""
        auftrag = self.parameter_auftrag()
        return auftrag.abschliessen(auftrag.ausfuehren())

    def _parameter_abschliessen(self, ergebnis: Ergebnis, ordner: Path) -> Ergebnis:
        if ergebnis.erfolg:
            try:
                self.projekt.parameterwerte.clear()
            except FileNotFoundError:
                pass
        return ergebnis

    def parameter_vollstaendig(self) -> bool:
        """Alle Pflichtparameter haben Werte. Ruft nicht zustand() auf."""
        anfrage = self.parameter_anfrage()
        werte = self.projekt.parameterwerte
        pflicht = [z for z in anfrage if z.get("pflicht") == "ja"]
        return all(
            _schluessel(z["component_id"], z["parameter"]) in werte for z in pflicht
        )

    def parameter_setzen(
        self, bauteil_id: str, parameter: str, wert: str
    ) -> tuple[str | None, str]:
        """Prüft und speichert einen Parameterwert (Q-8)."""
        anfrage = self.parameter_anfrage()
        eintrag = next(
            (
                z
                for z in anfrage
                if z["component_id"] == bauteil_id and z["parameter"] == parameter
            ),
            None,
        )
        if eintrag is None:
            return f"Parameter nicht gefunden: {bauteil_id}.{parameter}", ""
        fehler, normiert = pruefe_wert(eintrag, wert)
        if fehler:
            return fehler, ""
        self.projekt.parameterwerte[_schluessel(bauteil_id, parameter)] = normiert
        return None, normiert

    # ------------------------------------------------------------------
    # Code-Erzeugung (Schritt 6)
    # ------------------------------------------------------------------

    def parameter_schreiben(self) -> Ergebnis:
        """Schreibt parameters.csv aus den gespeicherten Werten (Q-8)."""
        anfrage = self.parameter_anfrage()
        ordner = self._ordner()
        zeilen: list[dict[str, str]] = []
        for z in anfrage:
            schluessel = _schluessel(z["component_id"], z["parameter"])
            wert = self.projekt.parameterwerte.get(schluessel, z["standardwert"])
            zeilen.append(
                {
                    "component_id": z["component_id"],
                    "parameter": z["parameter"],
                    "wert": wert,
                    "quelle": "eingabe"
                    if schluessel in self.projekt.parameterwerte
                    else "standard",
                }
            )
        _schreibe(
            ordner / "parameters.csv",
            ["component_id", "parameter", "wert", "quelle"],
            zeilen,
        )
        return Ergebnis(True)

    def code_auftrag(self) -> Auftrag:
        """Backend-Auftrag für Code-Erzeugung."""
        ergebnis = self.parameter_schreiben()
        if not ergebnis.erfolg:
            raise SchrittFehler(ergebnis.meldung)
        ordner = self._ordner()
        return Auftrag(
            "amesim_code_erzeugen",
            ordner,
            self.backend.amesim_code_erzeugen,
            lambda e: self._code_abschliessen(e, ordner),
        )

    def code_erzeugen(self) -> Ergebnis:
        """Synchrone Variante."""
        auftrag = self.code_auftrag()
        return auftrag.abschliessen(auftrag.ausfuehren())

    def _code_abschliessen(self, ergebnis: Ergebnis, ordner: Path) -> Ergebnis:
        if ergebnis.erfolg:
            try:
                self.projekt.letzter_amesim_code = (
                    ordner / "amesim_modell.py"
                ).read_text(encoding="utf-8")
            except FileNotFoundError:
                pass
        return ergebnis

    def code_text(self) -> str:
        return self.projekt.letzter_amesim_code or ""

    # ------------------------------------------------------------------
    # Persistierung
    # ------------------------------------------------------------------

    def speichern(self, pfad: Path) -> None:
        self.projekt.fingerabdruck_analyse = self.anlage.strukturfingerabdruck()
        speichere(self.projekt, pfad)

    @classmethod
    def laden(
        cls, pfad: Path, pool: Pool, backend: Backend, kriterien: dict, austauschbasis: Path
    ) -> Controller:
        projekt = lade(pfad)
        controller = cls(pool, backend, austauschbasis, kriterien, projekt)
        fp = (
            projekt.strukturfingerabdruck()
            if hasattr(projekt, "strukturfingerabdruck")
            else None
        )
        if fp and projekt.analyseergebnis.get("struktur", {}).get("fingerabdruck") == fp:
            controller._struktur_fp = fp
        if fp and projekt.analyseergebnis.get("abc", {}).get("fingerabdruck") == fp:
            controller._abc_fp = fp
        return controller