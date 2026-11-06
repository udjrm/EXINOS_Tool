"""Pool v1.3: Struktur, Kennzahlen und Layoutrollen."""

from __future__ import annotations

import pytest

from exinos_tool.core.pool import (
    LAYOUT_ANKER_SEITLICH,
    LAYOUT_ANKER_SPUR,
    LAYOUT_SPUR,
    LAYOUT_STRUKTUR,
    PoolFehler,
    Pool,
)


def test_kennzahlen(pool):
    assert pool.version == "1.3"
    assert len(pool.typen) == 28
    assert len(pool.platzierbare_typen()) == 26
    assert pool.anzahl_portdefinitionen() == 71


def test_keine_migrationswarnungen(pool):
    """Nach L1/L2 muss der Pool ohne Warnungen laden."""
    assert pool.warnungen == []


def test_portzahl_je_kategorie(pool):
    erwartet = {
        "Bahnfuehrung": 16,
        "Wickeln und Handhaben": 21,
        "Antriebstechnik": 19,
        "Pneumatik und Vakuum": 6,
        "Sensorik und Steuerung": 9,
    }
    gezaehlt = {}
    for typ in pool.platzierbare_typen():
        gezaehlt[typ.kategorie] = gezaehlt.get(typ.kategorie, 0) + len(typ.ports)
    assert gezaehlt == erwartet


def test_pseudotypen_nicht_platzierbar(pool):
    assert not pool.typ("materialbahn").platzierbar
    assert not pool.typ("rahmen").platzierbar


def test_max_null_bei_lage_aus_leistung(pool):
    """Jeder lage-Ausgang mit rolle leistung ist unbegrenzt (v1.3)."""
    betroffen = [
        (t.typ, p.name)
        for t in pool.platzierbare_typen()
        for p in t.ports.values()
        if p.art == "lage" and p.richtung == "aus" and p.rolle == "leistung"
    ]
    assert len(betroffen) == 8
    for typ_name, port_name in betroffen:
        assert pool.port(typ_name, port_name).unbegrenzt, (typ_name, port_name)


def test_messungsports_bleiben_einfach(pool):
    messung = [
        p
        for t in pool.platzierbare_typen()
        for p in t.ports.values()
        if p.rolle == "messung" and p.richtung == "aus"
    ]
    assert len(messung) == 3
    assert all(p.max == 1 for p in messung)


@pytest.mark.parametrize(
    "art, rolle, erwartet",
    [
        ("bahn", None, LAYOUT_SPUR),
        ("welle", None, LAYOUT_STRUKTUR),
        ("pneumatik", None, LAYOUT_STRUKTUR),
        ("vakuum", None, LAYOUT_STRUKTUR),
        ("material", None, LAYOUT_ANKER_SPUR),
        ("signal", None, LAYOUT_ANKER_SEITLICH),
        ("lage", "leistung", LAYOUT_STRUKTUR),
        ("lage", "messung", LAYOUT_ANKER_SEITLICH),
        ("lage", None, LAYOUT_STRUKTUR),  # Default leistung
    ],
)
def test_layoutrollen(pool, art, rolle, erwartet):
    assert pool.layout_rolle(art, rolle) == erwartet


def test_bahnports_nach_ports_nicht_kategorie(pool):
    """klemmrolle steht in Bahnfuehrung ohne bahn-Ports,
    bahnkantensensor in Sensorik mit bahn-Ports."""
    assert not pool.typ("klemmrolle").hat_bahnports
    assert pool.typ("bahnkantensensor").hat_bahnports


def test_unbekannte_art_wird_abgelehnt():
    roh = {
        "version": "x",
        "verbindungsarten": {"bahn": {"rolle_layout": "spur"}},
        "typen": [
            {"typ": "t", "ports": [{"name": "p", "art": "gibtsnicht", "richtung": "ein"}]}
        ],
    }
    with pytest.raises(PoolFehler):
        Pool.aus_rohdaten(roh)