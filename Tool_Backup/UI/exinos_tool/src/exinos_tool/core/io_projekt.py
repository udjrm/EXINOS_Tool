"""Projektdatei .anlage (JSON) mit schema_version (F-1, F-2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .modell import Anlage, Bahn, Bauteil, Verbindung

SCHEMA_VERSION = "1.0"


class ProjektFehler(Exception):
    """Die Projektdatei ist unbrauchbar oder zu neu."""


@dataclass
class Projekt:
    """Eine Projektdatei: Anlage, Darstellung und Analysezustand."""

    anlage: Anlage = field(default_factory=Anlage)
    anmerkungen: list[dict] = field(default_factory=list)
    nwa_bewertung: dict = field(default_factory=dict)
    analyseergebnis: dict = field(default_factory=dict)
    parameterwerte: dict = field(default_factory=dict)
    fingerabdruck_analyse: str = ""
    pool_version: str = ""
    letzter_amesim_code: str = ""

    @property
    def analyse_aktuell(self) -> bool:
        """Z-7: Ergebnisse gelten nur zum Fingerabdruck, bei dem sie entstanden."""
        if not self.fingerabdruck_analyse:
            return False
        return self.fingerabdruck_analyse == self.anlage.strukturfingerabdruck()


def _bauteil_als_dict(bauteil: Bauteil) -> dict:
    return {
        "id": bauteil.id,
        "typ": bauteil.typ,
        "bezeichnung": bauteil.bezeichnung,
        "materialpfad": bauteil.materialpfad,
        "baugruppe": bauteil.baugruppe,
        "gestellfest": bauteil.gestellfest,
        "bemerkung": bauteil.bemerkung,
        "x": bauteil.x,
        "y": bauteil.y,
        "drehung": bauteil.drehung,
        "gespiegelt": bauteil.gespiegelt,
    }


def _verbindung_als_dict(verbindung: Verbindung) -> dict:
    return {
        "id": verbindung.id,
        "von": verbindung.von,
        "von_port": verbindung.von_port,
        "nach": verbindung.nach,
        "nach_port": verbindung.nach_port,
        "art": verbindung.art,
        "bahn": verbindung.bahn,
        "knickpunkte": [list(punkt) for punkt in verbindung.knickpunkte],
    }


def speichere(projekt: Projekt, pfad: str | Path) -> None:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    daten = {
        "schema_version": SCHEMA_VERSION,
        "pool_version": projekt.pool_version,
        "projekt": {
            "name": projekt.anlage.name,
            "bearbeiter": projekt.anlage.bearbeiter,
        },
        "bahnen": [
            {
                "id": b.id,
                "bezeichnung": b.bezeichnung,
                "kuerzel": b.kuerzel,
                "farbe": b.farbe,
            }
            for b in projekt.anlage.bahnen.values()
        ],
        "bauteile": [
            _bauteil_als_dict(b) for b in projekt.anlage.bauteile.values()
        ],
        "verbindungen": [
            _verbindung_als_dict(v) for v in projekt.anlage.verbindungen.values()
        ],
        "anmerkungen": projekt.anmerkungen,
        "nwa_bewertung": projekt.nwa_bewertung,
        "analyseergebnis": projekt.analyseergebnis,
        "parameterwerte": projekt.parameterwerte,
        "fingerabdruck_analyse": projekt.fingerabdruck_analyse,
        "letzter_amesim_code": projekt.letzter_amesim_code,
    }
    pfad.write_text(
        json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def lade(pfad: str | Path) -> Projekt:
    pfad = Path(pfad)
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as fehler:
        raise ProjektFehler(f"{pfad.name} ist kein gueltiges JSON: {fehler}") from fehler

    version = str(daten.get("schema_version", ""))
    if not version:
        raise ProjektFehler(
            f"{pfad.name} nennt keine schema_version und kann nicht geladen werden."
        )
    if version > SCHEMA_VERSION:
        raise ProjektFehler(
            f"{pfad.name} verwendet schema_version {version}. Dieses Werkzeug "
            f"unterstuetzt hoechstens {SCHEMA_VERSION}. Bitte aktualisieren."
        )

    anlage = Anlage(
        name=daten.get("projekt", {}).get("name", ""),
        bearbeiter=daten.get("projekt", {}).get("bearbeiter", ""),
    )
    for eintrag in daten.get("bahnen", []):
        anlage.bahn_hinzufuegen(Bahn(**eintrag))
    for eintrag in daten.get("bauteile", []):
        anlage.hinzufuegen(Bauteil(**eintrag))
    for eintrag in daten.get("verbindungen", []):
        knickpunkte = [tuple(p) for p in eintrag.pop("knickpunkte", [])]
        anlage.verbinden(Verbindung(**eintrag, knickpunkte=knickpunkte))

    return Projekt(
        anlage=anlage,
        anmerkungen=daten.get("anmerkungen", []),
        nwa_bewertung=daten.get("nwa_bewertung", {}),
        analyseergebnis=daten.get("analyseergebnis", {}),
        parameterwerte=daten.get("parameterwerte", {}),
        fingerabdruck_analyse=daten.get("fingerabdruck_analyse", ""),
        pool_version=daten.get("pool_version", ""),
        letzter_amesim_code=daten.get("letzter_amesim_code", ""),
    )