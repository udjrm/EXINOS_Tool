# -*- coding: utf-8 -*-
"""
zahlformat.py
Einheitliches Dezimalformat fuer alle CSV-Schnittstellen.

Festlegung (Lastenheft 1.2, Punkt 6)
------------------------------------
Lesen    : Punkt UND Komma werden akzeptiert.
Schreiben: immer Komma, feste Nachkommastellen, keine
           Tausendertrennzeichen, keine Exponentialschreibweise.

Betroffen sind nur Dezimalwerte: gewicht, NW, B_ges, spaeter die
Parameterwerte. Ganzzahlige Groessen (AS, PS, n, DSM-Zellen) werden
mit schreibe_ganz() ausgegeben und sind von der Umstellung nicht
beruehrt - die DSM-Berechnung bleibt also unveraendert.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional


NACHKOMMA_STANDARD = 4


class ZahlFormatFehler(ValueError):
    """Ein Feld liess sich nicht als Zahl lesen."""
    pass


# ----------------------------------------------------------------------
# Lesen
# ----------------------------------------------------------------------

def lies_zahl(text, feldname: str = "", standard: Optional[float] = None) -> float:
    """
    Liest einen Dezimalwert aus einer CSV-Zelle.

    Akzeptiert "0,4884" und "0.4884" gleichermassen, ebenso fuehrende
    und nachlaufende Leerzeichen. Leere Zellen liefern 'standard',
    sofern gesetzt - sonst eine Ausnahme mit Feldnamen im Text.

    Bewusst NICHT akzeptiert werden Tausendertrennzeichen: "1.234,56"
    waere mehrdeutig und deutet auf eine Datei aus einer anderen
    Quelle hin.
    """
    if text is None:
        if standard is not None:
            return standard
        raise ZahlFormatFehler("Feld {} ist leer".format(feldname or "?"))

    roh = str(text).strip()
    if roh == "":
        if standard is not None:
            return standard
        raise ZahlFormatFehler("Feld {} ist leer".format(feldname or "?"))

    if roh.count(",") > 1 or (("," in roh) and ("." in roh)):
        raise ZahlFormatFehler(
            "Feld {}: '{}' sieht nach Tausendertrennzeichen aus - "
            "bitte nur ein Dezimaltrennzeichen verwenden".format(
                feldname or "?", roh))

    try:
        return float(roh.replace(",", "."))
    except ValueError:
        raise ZahlFormatFehler(
            "Feld {}: '{}' ist keine Zahl".format(feldname or "?", roh))


def lies_ganz(text, feldname: str = "", standard: Optional[int] = None) -> int:
    """Liest eine ganze Zahl. Nachkommastellen sind hier ein Fehler."""
    if text is None or str(text).strip() == "":
        if standard is not None:
            return standard
        raise ZahlFormatFehler("Feld {} ist leer".format(feldname or "?"))

    roh = str(text).strip()
    try:
        return int(roh)
    except ValueError:
        raise ZahlFormatFehler(
            "Feld {}: '{}' ist keine ganze Zahl".format(feldname or "?", roh))


# ----------------------------------------------------------------------
# Schreiben
# ----------------------------------------------------------------------

def schreibe_zahl(wert, nachkomma: int = NACHKOMMA_STANDARD) -> str:
    """
    Formatiert einen Dezimalwert fuer die Ausgabe.

    Immer Komma, immer feste Stellenzahl - auch bei glatten Werten.
    Das haelt Spaltenbreiten konstant und macht Golden-File-Tests
    zuverlaessig, weil 3 und 3,0000 sonst unterschiedliche Zeilen
    erzeugen.

    Gerundet wird kaufmaennisch (ROUND_HALF_UP), nicht nach dem
    Python-Standard ROUND_HALF_EVEN: 0,12345 ergibt 0,1235, nicht
    0,1234. Das entspricht der Erwartung in technischen Tabellen.
    """
    if wert is None:
        return ""
    try:
        d = Decimal(str(wert))
    except InvalidOperation:
        raise ZahlFormatFehler("'{}' laesst sich nicht formatieren".format(wert))

    quant = Decimal(1).scaleb(-nachkomma)
    gerundet = d.quantize(quant, rounding=ROUND_HALF_UP)
    return format(gerundet, "f").replace(".", ",")


def schreibe_ganz(wert) -> str:
    """Formatiert eine ganze Zahl. Kein Trennzeichen, kein Komma."""
    if wert is None:
        return ""
    return str(int(wert))


# ----------------------------------------------------------------------
# Selbsttest
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # Lesen
    assert lies_zahl("0,4884") == 0.4884
    assert lies_zahl("0.4884") == 0.4884
    assert lies_zahl("  3  ") == 3.0
    assert lies_zahl("", standard=0.0) == 0.0
    assert lies_ganz("92") == 92

    for schlecht in ("1.234,56", "abc", "3,1,4"):
        try:
            lies_zahl(schlecht, "test")
            raise AssertionError("haette scheitern muessen: " + schlecht)
        except ZahlFormatFehler:
            pass

    # Schreiben
    assert schreibe_zahl(0.4884) == "0,4884"
    assert schreibe_zahl(3) == "3,0000"
    assert schreibe_zahl(0.12345) == "0,1235"      # kaufmaennisch
    assert schreibe_ganz(92) == "92"
    assert schreibe_zahl(None) == ""

    # Durchlauf: Gewichte Vereinzelung aus Tab. 5-2
    gewichte = ["0,4884", "0,2326", "0,1628", "0,1163"]
    summe = sum(lies_zahl(g, "gewicht") for g in gewichte)
    print("Summe Vereinzelung:", schreibe_zahl(summe))   # 1,0001

    print("Alle Tests bestanden.")