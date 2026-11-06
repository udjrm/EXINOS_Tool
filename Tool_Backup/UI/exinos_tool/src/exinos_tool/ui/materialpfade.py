"""Feste Materialpfad-Liste (PLATZHALTER bis bauteilpool.json v1.4).

Diese Liste gehoert spaeter in den Pool, Abschnitt "materialpfade".
Dann laedt das Frontend sie von dort und diese Datei entfaellt. Die
Kuerzel An, Ka, El, Se sind verbindlich, weil die NWA mit ihnen arbeitet.
"""

from __future__ import annotations

#: kuerzel -> Angaben. prozess ist "vereinzelung" oder "stapeln".
MATERIALPFADE: dict[str, dict[str, str]] = {
    "An": {"bezeichnung": "Anode", "prozess": "vereinzelung", "farbe": "#C62828"},
    "Ka": {"bezeichnung": "Kathode", "prozess": "vereinzelung", "farbe": "#1565C0"},
    "El": {"bezeichnung": "Elektrode", "prozess": "vereinzelung", "farbe": "#6A1B9A"},
    "Se": {"bezeichnung": "Separator", "prozess": "stapeln", "farbe": "#424242"},
}


def pfad_kuerzel() -> list[str]:
    return list(MATERIALPFADE)


def pfad_bezeichnung(kuerzel: str) -> str:
    eintrag = MATERIALPFADE.get(kuerzel)
    return eintrag["bezeichnung"] if eintrag else kuerzel


def pfad_farbe(kuerzel: str) -> str:
    eintrag = MATERIALPFADE.get(kuerzel)
    return eintrag["farbe"] if eintrag else "#777777"


def anzeige(kuerzel: str) -> str:
    """Text fuer Auswahlfelder, z. B. 'An – Anode'."""
    return f"{kuerzel} – {pfad_bezeichnung(kuerzel)}"