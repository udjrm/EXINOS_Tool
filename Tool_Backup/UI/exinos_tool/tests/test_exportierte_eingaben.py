from __future__ import annotations

import csv
from pathlib import Path

from exinos_tool.app.controller import Controller
from exinos_tool.core.io_csv import lies_anlage
from exinos_tool.core.io_projekt import Projekt
from exinos_tool.core.nwa import lies_kriterien
from exinos_tool.core.pool import Pool
from exinos_tool.adapter.prozess import backend_laden


def test_strukturanalyse_verwendet_manipulierte_export_csvs(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    pool = Pool.laden(root / "konfiguration" / "bauteilpool.json")
    backend = backend_laden(root / "konfiguration" / "config.json")
    anlage = lies_anlage(root / "beispiele" / "Coil2Stack", "Coil2Stack")
    controller = Controller(
        pool,
        backend,
        tmp_path / "Exports",
        lies_kriterien(root / "konfiguration" / "nwa_kriterien.csv"),
        projekt=Projekt(anlage=anlage),
    )

    controller.pruefen()
    erfolg, _ = controller.exportieren(controller.austauschbasis)
    assert erfolg
    ordner = controller.aktueller_ordner()
    components = ordner / "components.csv"

    with components.open("r", encoding="utf-8", newline="") as datei:
        rows = list(csv.DictReader(datei, delimiter=";"))
    rows[0]["bezeichnung"] = "MANUELL_GEANDERT"
    with components.open("w", encoding="utf-8", newline="") as datei:
        writer = csv.DictWriter(datei, fieldnames=rows[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    ergebnis = controller.struktur_analysieren()

    assert ergebnis.erfolg, ergebnis.meldung
    assert "MANUELL_GEANDERT" in (ordner / "instances.csv").read_text(
        encoding="utf-8"
    )
