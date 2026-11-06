"""Zahlenformat der Schnittstelle.

Festlegung aus Lastenheft 1.2, Punkt 6:
Dezimaltrennzeichen ist das Komma. Beim Lesen werden Punkt und Komma
akzeptiert, beim Schreiben wird das Komma verwendet. Keine
Tausendertrennzeichen.
"""

from __future__ import annotations


class ZahlFehler(ValueError):
    """Ein Feld konnte nicht als Zahl gelesen werden."""


def zahl_lesen(text: str | float | int | None) -> float | None:
    """Liest eine Zahl, die Punkt oder Komma als Trennzeichen verwenden darf.

    Leere Felder und None ergeben None. Das unterscheidet einen nicht
    gesetzten Wert von einer echten Null.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)

    roh = text.strip()
    if not roh:
        return None
    if "," in roh and "." in roh:
        raise ZahlFehler(
            f"Zahl {roh!r} enthaelt Punkt und Komma. "
            "Tausendertrennzeichen sind nicht zulaessig."
        )
    try:
        return float(roh.replace(",", "."))
    except ValueError as fehler:
        raise ZahlFehler(f"Feld {roh!r} ist keine Zahl.") from fehler


def ganzzahl_lesen(text: str | int | None) -> int | None:
    """Liest eine Ganzzahl. Ein gebrochener Wert ist ein Fehler."""
    wert = zahl_lesen(text)
    if wert is None:
        return None
    if wert != int(wert):
        raise ZahlFehler(f"Wert {text!r} ist keine Ganzzahl.")
    return int(wert)


def zahl_schreiben(wert: float | int | None, nachkommastellen: int | None = None) -> str:
    """Schreibt eine Zahl mit Komma als Dezimaltrennzeichen.

    Ohne Angabe von nachkommastellen wird die kuerzeste Darstellung
    gewaehlt, die den Wert exakt wiedergibt (repr-Verhalten von float).
    """
    if wert is None:
        return ""
    if nachkommastellen is None:
        text = repr(float(wert))
        if text.endswith(".0"):
            text = text[:-2]
    else:
        text = f"{float(wert):.{nachkommastellen}f}"
    return text.replace(".", ",")


def wahrheitswert_lesen(text: str | bool | None) -> bool | None:
    """Liest ja/nein, true/false, 1/0. Leer ergibt None (nicht festgelegt)."""
    if text is None:
        return None
    if isinstance(text, bool):
        return text
    roh = text.strip().casefold()
    if not roh:
        return None
    if roh in {"ja", "j", "true", "wahr", "1"}:
        return True
    if roh in {"nein", "n", "false", "falsch", "0"}:
        return False
    raise ZahlFehler(f"Feld {text!r} ist kein Wahrheitswert.")


def wahrheitswert_schreiben(wert: bool | None) -> str:
    """Schreibt ja/nein. None ergibt ein leeres Feld."""
    if wert is None:
        return ""
    return "ja" if wert else "nein"