"""Kommandozeile fuer den headless-Betrieb.

Erlaubt es, Abnahme 1 und 3 ohne jede Oberflaeche zu belegen:

    exinos-tool pruefen beispiele/EXINOS
    exinos-tool exportieren beispiele/EXINOS -o tmp/EXINOS
    exinos-tool layout beispiele/Coil2Stack
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.darstellung import Darstellung
from .core.io_csv import lies_anlage, schreibe_anlage
from .core.layout import ordne_an
from .core.pool import Pool
from .core.pruefung import pruefe

STANDARD_POOL = Path("konfiguration/bauteilpool.json")
STANDARD_DARSTELLUNG = Path("konfiguration/pool_darstellung.json")


def _pool_laden(pfad: Path) -> Pool:
    pool = Pool.laden(pfad)
    for meldung in pool.warnungen:
        print(f"WARNUNG;pool;{meldung}")
    return pool


def befehl_pruefen(args: argparse.Namespace) -> int:
    pool = _pool_laden(args.pool)
    anlage = lies_anlage(args.ordner)
    bericht = pruefe(anlage, pool)

    if bericht.befunde:
        print(bericht.protokoll())
    fehler, warnungen, hinweise = bericht.zusammenfassung()
    print(
        f"INFO;zusammenfassung;{args.ordner.name}: {fehler} Fehler, "
        f"{warnungen} Warnungen, {hinweise} Hinweise"
    )
    return 0 if bericht.exportfaehig else 1


def befehl_exportieren(args: argparse.Namespace) -> int:
    pool = _pool_laden(args.pool)
    anlage = lies_anlage(args.ordner)
    bericht = pruefe(anlage, pool)
    if not bericht.exportfaehig:
        print(bericht.protokoll())
        print("FEHLER;export;Export nicht moeglich, es liegen Fehler vor.")
        return 1
    schreibe_anlage(anlage, args.ausgabe)
    print(f"INFO;export;Geschrieben nach {args.ausgabe}")
    return 0


def befehl_layout(args: argparse.Namespace) -> int:
    pool = _pool_laden(args.pool)
    darstellung = Darstellung.laden(args.darstellung, pool)
    for meldung in darstellung.meldungen:
        print(f"INFO;darstellung;{meldung}")

    anlage = lies_anlage(args.ordner)
    ergebnis = ordne_an(anlage, pool)
    for meldung in ergebnis.meldungen:
        print(f"WARNUNG;layout;{meldung}")

    statistik = ergebnis.statistik()
    for schluessel in sorted(statistik):
        print(f"INFO;layout;{schluessel}: {statistik[schluessel]}")
    print(f"INFO;layout;Restblock: {len(ergebnis.restblock)}")
    return 0 if not ergebnis.restblock else 1


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(prog="exinos-tool")
    zerleger.add_argument("--pool", type=Path, default=STANDARD_POOL)
    unterbefehle = zerleger.add_subparsers(dest="befehl", required=True)

    p = unterbefehle.add_parser("pruefen", help="P-1 bis P-8 ausfuehren")
    p.add_argument("ordner", type=Path)
    p.set_defaults(funktion=befehl_pruefen)

    e = unterbefehle.add_parser("exportieren", help="Struktur-CSVs schreiben")
    e.add_argument("ordner", type=Path)
    e.add_argument("-o", "--ausgabe", type=Path, required=True)
    e.set_defaults(funktion=befehl_exportieren)

    l = unterbefehle.add_parser("layout", help="Automatische Anordnung testen")
    l.add_argument("ordner", type=Path)
    l.add_argument("--darstellung", type=Path, default=STANDARD_DARSTELLUNG)
    l.set_defaults(funktion=befehl_layout)

    args = zerleger.parse_args(argv)
    return args.funktion(args)


if __name__ == "__main__":
    sys.exit(main())