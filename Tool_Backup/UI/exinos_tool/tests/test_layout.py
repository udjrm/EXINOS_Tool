"""Auto-Layout F-3 mit den Festlegungen L1-L6 und F1-F3."""

from __future__ import annotations

import pytest

from exinos_tool.core.layout import (
    HERKUNFT_ANKER_SEITLICH,
    HERKUNFT_ANKER_SPUR,
    HERKUNFT_REST,
    HERKUNFT_SPUR,
    berechne_layout,
    _median_tiefe,
)


@pytest.fixture
def layouts(pool, anlagen):
    return {name: berechne_layout(a, pool) for name, a in anlagen.items()}


def test_kein_restblock(layouts, anlage_name):
    """Kernaussage: Jedes Bauteil wird platziert."""
    ergebnis = layouts[anlage_name]
    assert ergebnis.restblock == [], ergebnis.meldungen


def test_alle_bauteile_platziert(layouts, anlagen, anlage_name):
    assert len(layouts[anlage_name].platzierungen) == len(
        anlagen[anlage_name].bauteile
    )


def test_tiefe_null_nur_fuer_bahn_und_ankerspur(pool, layouts, anlagen, anlage_name):
    """Tiefe 0 ist Bahnbauteilen und anker_spur vorbehalten (F2)."""
    anlage = anlagen[anlage_name]
    for platzierung in layouts[anlage_name].platzierungen.values():
        if platzierung.tiefe != 0:
            continue
        typ = pool.typ(anlage.bauteile[platzierung.bauteil_id].typ)
        assert typ.hat_bahnports or platzierung.herkunft == HERKUNFT_ANKER_SPUR, (
            platzierung
        )


def test_spurknoten_zaehlen(pool, layouts, anlagen, anlage_name):
    """Auf der Spur steht genau, was bahn-Kanten hat."""
    anlage = anlagen[anlage_name]
    aus_kanten = {
        v.von for v in anlage.verbindungen.values() if v.art == "bahn"
    } | {v.nach for v in anlage.verbindungen.values() if v.art == "bahn"}
    auf_spur = {
        p.bauteil_id
        for p in layouts[anlage_name].platzierungen.values()
        if p.herkunft == HERKUNFT_SPUR
    }
    assert auf_spur == aus_kanten


def test_f1_ablegetisch_bleibt_auf_tiefe_null(layouts):
    """F1: anker_spur kreuzt die Bahnspur nicht."""
    platzierungen = layouts["Coil2Stack"].platzierungen
    tisch = platzierungen["Ablegetisch"]
    assert tisch.herkunft == HERKUNFT_ANKER_SPUR
    assert tisch.tiefe == 0
    # Die Baugruppe Ablage haengt vollstaendig darunter.
    for name in (
        "Fuehrung_AT_h",
        "Spindel_AT_h",
        "Antrieb_AT_h",
        "Spindel_AT_v",
        "Antrieb_AT_v",
    ):
        assert platzierungen[name].tiefe < 0, name


def test_zweigvorzeichen_bleibt_erhalten(layouts):
    """L4-Vorlaeufer: Antrieb_VG1 darf nicht in der Bahnspur landen."""
    platzierungen = layouts["Coil2Stack"].platzierungen
    assert platzierungen["Handhabung"].tiefe == 0
    assert platzierungen["Lineareinheit_VG1"].tiefe == 1
    assert platzierungen["Antrieb_VG1"].tiefe == 2
    assert platzierungen["Vakuumgreifer_1"].tiefe == 2
    # Die Hubachse liegt unterhalb.
    assert platzierungen["Fuehrung_Hub"].tiefe == -1
    assert platzierungen["Antrieb_Hub"].tiefe == -4


def test_f2_median_wird_vom_nullpunkt_weg_gerundet():
    assert _median_tiefe([-1, -3]) == -2
    assert _median_tiefe([0, -1]) == -1
    assert _median_tiefe([-1, -4]) == -3
    assert _median_tiefe([-3, 1, 1]) == 1


def test_f2_regler_dr_neben_stellantrieb(layouts):
    platzierungen = layouts["Coil2Stack"].platzierungen
    assert platzierungen["Stellantrieb_DR"].tiefe == -1
    regler = platzierungen["Regler_DR"]
    assert regler.herkunft == HERKUNFT_ANKER_SEITLICH
    assert regler.tiefe == -1


def test_f3_wechselseitige_anker(layouts):
    """Drehgeber und Regler bedingen sich gegenseitig (Z-Falter)."""
    platzierungen = layouts["ZFalter"].platzierungen
    assert platzierungen["Drehgeber_Taenzer"].tiefe == -1
    assert platzierungen["Regler_Abw"].tiefe == -1
    assert platzierungen["Taktgeber"].tiefe == 1


def test_klemmrollen_liegen_ueber_dem_tisch(layouts):
    platzierungen = layouts["ZFalter"].platzierungen
    assert platzierungen["Stapeltisch"].tiefe == 0
    assert platzierungen["Klemmrolle"].tiefe == 1
    assert platzierungen["Kontaktrolle"].tiefe == 1


def test_determinismus(pool, anlagen, anlage_name):
    """Abnahme 1: Dieselbe Eingabe ergibt dieselbe Anordnung."""
    erst = berechne_layout(anlagen[anlage_name], pool)
    zweit = berechne_layout(anlagen[anlage_name], pool)
    assert {k: (p.x, p.y) for k, p in erst.platzierungen.items()} == {
        k: (p.x, p.y) for k, p in zweit.platzierungen.items()
    }


def test_statistik_ausgeben(layouts, anlage_name, capsys):
    """Kein Pruefkriterium, nur zur Kontrolle der Verteilung."""
    with capsys.disabled():
        print(f"\n{anlage_name}: {layouts[anlage_name].statistik()}")