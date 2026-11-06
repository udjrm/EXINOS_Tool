"""Bewertungskriterien der NWA aus nwa_kriterien.csv.

Festlegungen:
- Verbindungsschluessel ist kriterium_id, nicht der Freitext.
- Gewichte stehen als Anteile mit Komma und werden NICHT normiert.
  Summen von 1,0001 (Vereinzelung) und 1,0000 (Stapeln) sind gewollt.
- kuerzel ist optional. Fehlt es, wird die kriterium_id als Spaltenkopf genutzt.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .zahlen import ZahlFehler, zahl_lesen

PFLICHTSPALTEN = ("zielgroesse", "kriterium_id")
TOLERANZ_SUMME = 0.0002


class NwaFehler(ValueError):
    """Die Kriteriendatei ist unbrauchbar."""


@dataclass(frozen=True)
class Kriterium:
    zielgroesse: str
    kriterium_id: str
    kuerzel: str
    kriterium: str
    rpz: float | None
    gewicht: float


def lies_kriterien(pfad: str | Path) -> dict[str, list[Kriterium]]:
    """Liest die Datei und gruppiert sie nach Zielgroesse."""
    pfad = Path(pfad)
    if not pfad.exists():
        raise NwaFehler(f"Datei nicht gefunden: {pfad}")

    ergebnis: dict[str, list[Kriterium]] = {}
    with pfad.open("r", encoding="utf-8-sig", newline="") as datei:
        leser = csv.DictReader(datei, delimiter=";")
        fehlend = [s for s in PFLICHTSPALTEN if s not in (leser.fieldnames or [])]
        if fehlend:
            raise NwaFehler(f"{pfad.name}: fehlende Spalten {', '.join(fehlend)}.")

        for nummer, zeile in enumerate(leser, start=2):
            kid = (zeile.get("kriterium_id") or "").strip()
            if not kid:
                continue
            try:
                gewicht = zahl_lesen(zeile.get("gewicht"))
                rpz = zahl_lesen(zeile.get("rpz"))
            except ZahlFehler as fehler:
                raise NwaFehler(f"{pfad.name}, Zeile {nummer}: {fehler}") from fehler
            kriterium = (zeile.get("kriterium") or zeile.get("bezeichnung") or "").strip()
            if not kriterium:
                raise NwaFehler(f"{pfad.name}, Zeile {nummer}: Kriterium fehlt.")
            if gewicht is None and rpz is None:
                raise NwaFehler(f"{pfad.name}, Zeile {nummer}: Gewicht oder RPZ fehlt.")

            zielgroesse = zeile["zielgroesse"].strip()
            liste = ergebnis.setdefault(zielgroesse, [])
            if any(k.kriterium_id == kid for k in liste):
                raise NwaFehler(
                    f"{pfad.name}, Zeile {nummer}: kriterium_id {kid!r} kommt in "
                    f"{zielgroesse!r} mehrfach vor."
                )
            liste.append(
                Kriterium(
                    zielgroesse=zielgroesse,
                    kriterium_id=kid,
                    kuerzel=(zeile.get("kuerzel") or kid).strip(),
                    kriterium=kriterium,
                    rpz=rpz,
                    gewicht=gewicht if gewicht is not None else 0.0,
                )
            )
    for zielgroesse, liste in ergebnis.items():
        if any(k.gewicht == 0.0 and k.rpz is not None for k in liste):
            if any(k.gewicht != 0.0 for k in liste):
                raise NwaFehler(
                    f"{pfad.name}: gewicht bei allen Kriterien oder bei keinem "
                    f"setzen ({zielgroesse})."
                )
            summe_rpz = sum(k.rpz or 0.0 for k in liste)
            if summe_rpz <= 0:
                raise NwaFehler(f"{pfad.name}: RPZ-Summe fuer {zielgroesse} ist 0.")
            ergebnis[zielgroesse] = [
                Kriterium(
                    zielgroesse=k.zielgroesse,
                    kriterium_id=k.kriterium_id,
                    kuerzel=k.kuerzel,
                    kriterium=k.kriterium,
                    rpz=k.rpz,
                    gewicht=(k.rpz or 0.0) / summe_rpz,
                )
                for k in liste
            ]
    return ergebnis


def gewichtssumme(kriterien: list[Kriterium]) -> float:
    return sum(k.gewicht for k in kriterien)


def gewichte_pruefen(ergebnis: dict[str, list[Kriterium]]) -> list[str]:
    """Meldet Summen, die um mehr als die Toleranz von 1 abweichen."""
    meldungen: list[str] = []
    for zielgroesse, liste in ergebnis.items():
        summe = gewichtssumme(liste)
        if abs(summe - 1.0) > TOLERANZ_SUMME:
            meldungen.append(
                f"Zielgroesse {zielgroesse}: Summe {summe:.4f} weicht von 1 ab. "
                "Die Gewichte werden nicht normiert."
            )
    return meldungen