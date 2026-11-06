"""Traegt fuer jeden platzierbaren Typ 'symbol': '<typ>.svg' in
pool_darstellung.json ein. Idempotent: mehrfaches Ausfuehren schadet nicht.

Aufruf aus dem Projektwurzelverzeichnis:
    python skripte/symbole_eintragen.py
"""

from __future__ import annotations

import json
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
POOL = WURZEL / "konfiguration" / "bauteilpool.json"
OVERLAY = WURZEL / "konfiguration" / "pool_darstellung.json"
SYMBOLE = WURZEL / "ressourcen" / "symbole"


def main() -> None:
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    platzierbar = [
        t["typ"] for t in pool["typen"] if t.get("platzierbar", True)
    ]

    if OVERLAY.exists():
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    else:
        overlay = {"fuer_pool_version": pool.get("version", ""), "typen": {}}
    overlay.setdefault("typen", {})

    fehlende_dateien = []
    for typ in platzierbar:
        dateiname = f"{typ}.svg"
        if not (SYMBOLE / dateiname).exists():
            fehlende_dateien.append(dateiname)
        eintrag = overlay["typen"].setdefault(typ, {})
        eintrag["symbol"] = dateiname

    OVERLAY.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"{len(platzierbar)} Typen mit Symbol versehen.")
    if fehlende_dateien:
        print("WARNUNG: Fuer diese Typen fehlt die SVG-Datei:")
        for name in fehlende_dateien:
            print(f"  - {name}")
    else:
        print("Alle SVG-Dateien vorhanden.")


if __name__ == "__main__":
    main()