"""Backend-Workflow fuer die von der UI erzeugten CSV-Dateien.

Der Prozess arbeitet immer in einem Austauschordner. Die drei vorhandenen
Analyseprogramme werden bewusst als getrennte Stufen ausgefuehrt, damit
Fehler und Zwischenprodukte eindeutig dem jeweiligen Schritt zugeordnet
werden koennen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STRUCTURE_STAGES = ("lese_anlage.py", "refine_wl.py", "build_dsm.py")


def _run(script: str, args: list[str], output: Path, cwd: Path = ROOT) -> None:
    env = os.environ.copy()
    env["EXINOS_EXPORT_DIR"] = str(output)
    env["EXINOS_CONFIG_DIR"] = str(ROOT)
    env["EXINOS_FLAT_RUN"] = "1"
    result = subprocess.run(
        [sys.executable, str(ROOT / script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode:
        detail = next(
            (line for line in reversed(result.stderr.splitlines()) if line.strip()),
            f"Exitcode {result.returncode}",
        )
        raise RuntimeError(f"{script}: {detail}")


def _latest_dsm_run(output: Path) -> Path | None:
    runs = [p for p in output.iterdir() if p.is_dir()]
    return max(runs, key=lambda p: p.name) if runs else None


def klassen_und_dsm(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _run("lese_anlage.py", [str(output)], output)
    _run("refine_wl.py", [], output)
    _run("build_dsm.py", [], output)

    for name in (
        "instances.csv",
        "edges.csv",
        "pruefung.txt",
        "classes.csv",
        "dsm_matrix.csv",
        "dsm_edges.csv",
    ):
        if not (output / name).exists():
            raise RuntimeError(f"Pipeline-Ausgabedatei fehlt: {name}")
    _log(output, "klassen_und_dsm", "Strukturanalyse abgeschlossen.")


def _normalise_dsm(output: Path) -> None:
    source = output / "dsm_matrix.csv"
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file, delimiter=";"))
    if len(rows) < 2:
        raise RuntimeError("dsm_matrix.csv ist leer.")
    ids = rows[0][1:-1]
    data = [
        [row[0], *row[1:1 + len(ids)]]
        for row in rows[1:]
        if row and row[0] not in ("PS", "")
    ]
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=";", lineterminator="\n")
        writer.writerow(["klasse_id", *ids])
        writer.writerows(data)


def nwa_und_abc(output: Path) -> None:
    nwa(output)
    abc(output)
    _log(output, "nwa_und_abc", "NWA und ABC-Analyse abgeschlossen.")


def nwa(output: Path) -> None:
    _run("nwa.py", [], output, output)


def abc(output: Path) -> None:
    _run("abc.py", [], output, output)


def _log(output: Path, stage: str, message: str) -> None:
    with (output / "analysis_log.txt").open(
        "a", encoding="utf-8", newline=""
    ) as file:
        file.write(f"INFO;{stage};{message}\n")


def version(_: Path | None = None) -> str:
    return "backend-workflow-1.1"


def _mock_command(command: str, output: Path) -> None:
    from exinos_tool.adapter.mock import mock_backend
    from exinos_tool.adapter.mock.mock_backend import Protokoll

    function = {
        "parameteranfrage": mock_backend.parameteranfrage,
        "amesim_code_erzeugen": mock_backend.amesim_code_erzeugen,
    }[command]
    protocol = Protokoll(output, command)
    function(output, protocol)
    protocol.speichern()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            "Aufruf: python workflow.py "
            "(klassen_und_dsm|nwa|abc|nwa_und_abc|version)",
            file=sys.stderr,
        )
        return 2
    command = args[0]
    output = Path.cwd()
    try:
        if command == "klassen_und_dsm":
            klassen_und_dsm(output)
        elif command == "nwa_und_abc":
            nwa_und_abc(output)
        elif command == "nwa":
            nwa(output)
        elif command == "abc":
            abc(output)
        elif command in {"parameteranfrage", "amesim_code_erzeugen"}:
            _mock_command(command, output)
        elif command == "version":
            print(version(output))
        else:
            raise RuntimeError(f"Unbekannter Backend-Aufruf: {command}")
    except (OSError, RuntimeError) as error:
        print(f"FEHLER;{command};{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
