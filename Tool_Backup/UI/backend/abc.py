"""abc.py — ABC-Klassifikation der Bauteile, relativ und kumulativ

Aufruf : python abc.py          (Einstellungen: Konstanten unten)
Liest  : <Lauf>/nwa_klassen.csv          (aus nwa.py)
Gibt   : <Lauf>/analysis_result.csv      je Bauteil beide Einteilungen nebeneinander
         <Lauf>/abc_log.txt

Je Zielgroesse werden immer beide Verfahren gerechnet; jedes Bauteil erbt B_ges seiner Klasse.
  relativ   : A bei B_ges >= F_A * B_max, B bei >= F_B * B_max, sonst C
              (Festlegung dieser Arbeit; mengeninvariant, A1)
  kumulativ : absteigend sortiert (Tie-Break klasse_id, Bauteil);
              kumulierter Anteil <= GRENZE_A -> A, <= GRENZE_B -> B, sonst C (Husseini 2025)
Mehrere Zielgroessen: je Bauteil gilt die beste Klasse.
ABC_RELATIV waehlt nur, welches Verfahren zusaetzlich in Spalte 'abc' steht
(Grundlage der Parameterabfrage). Die Zielgroessen werden aus den Spalten
B_ges_<ziel> erkannt; neue Zielgroessen erfordern keine Aenderung hier.

Zahlen: Ausgabe mit Dezimalpunkt; beim Einlesen wird ein Komma als Punkt gelesen.
"""

import re
import csv
import sys
import pathlib
import os
from collections import defaultdict, Counter

# --- Einstellungen ----------------------------------------------------------
LAUFORDNER    = None                # None: juengster Ordner in Exports/ mit dsm_matrix.csv
ABC_RELATIV   = True                # Spalte 'abc': True relativ, False kumulativ
F_A           = 0.20                # relativ: Klasse A ab F_A * B_max
F_B           = 0.05                # relativ: Klasse B ab F_B * B_max
GRENZE_A      = 80.0                # kumulativ: Klasse A bis 80 % (Husseini 2025)
GRENZE_B      = 95.0                # kumulativ: Klasse B bis 95 %
SENSITIVITAET = [(0.15, 0.03), (0.20, 0.05), (0.25, 0.08)]   # weitere (F_A, F_B), nur Log; [] = aus
# -----------------------------------------------------------------------------

EXPORT_DIR = pathlib.Path(os.environ.get(
    'EXINOS_EXPORT_DIR',
    pathlib.Path(__file__).resolve().parent / 'Exports',
))
RANG, EPS = {'A': 0, 'B': 1, 'C': 2}, 1e-9
LOG = []


def log(t=''):
    print(t)
    LOG.append(t)


def zahl(t, feld):
    """Dezimalzahl; Komma wird als Punkt gelesen."""
    try:
        return float(str(t).strip().replace(',', '.'))
    except ValueError:
        sys.exit(f'{feld}: "{t}" ist keine Zahl')


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def verteilung(klassen):
    c = Counter(klassen)
    return '  '.join(f'{x} {c[x]:3d}' for x in 'ABC')


def beste(klassen):
    return min(klassen, key=RANG.get)


def zusammen(klassen):
    """Menge von Klassen als 'A' oder 'A/B', beste zuerst."""
    return '/'.join(sorted(set(klassen), key=RANG.get))


def finde_lauf():
    """Bewusst der juengste Ordner mit dsm_matrix.csv, nicht mit nwa_klassen.csv:
    nach einem neuen build_dsm.py-Lauf ohne nwa.py wuerde sonst still eine
    veraltete NWA eingeteilt."""
    if LAUFORDNER:
        p = pathlib.Path(LAUFORDNER)
        p = p if p.exists() else EXPORT_DIR / LAUFORDNER
    elif (EXPORT_DIR / 'dsm_matrix.csv').exists():
        p = EXPORT_DIR
    else:
        laeufe = sorted(d for d in EXPORT_DIR.glob('*') if (d / 'dsm_matrix.csv').exists())
        if not laeufe:
            sys.exit('Kein Laufordner mit dsm_matrix.csv in Exports/ - zuerst build_dsm.py')
        p = laeufe[-1]
    if not (p / 'nwa_klassen.csv').exists():
        sys.exit(f'nwa_klassen.csv fehlt in {p.name} - zuerst nwa.py ausfuehren')
    return p


def relativ(werte, fa, fb):
    bmax = max(werte.values(), default=0.0)

    def klasse(w):
        if bmax <= EPS:
            return 'C'
        return 'A' if w >= fa * bmax - EPS else 'B' if w >= fb * bmax - EPS else 'C'

    return {b: klasse(w) for b, w in werte.items()}, bmax


def kumulativ(werte, klasse_von):
    """-> {bauteil: (klasse, kumulierter Anteil in %, rang)}"""
    reihe = sorted(werte, key=lambda b: (-werte[b], klasse_von[b], natkey(b)))
    summe, lauf, out = sum(werte.values()), 0.0, {}
    for rang, b in enumerate(reihe, 1):
        lauf += werte[b]
        anteil = lauf / summe * 100 if summe > EPS else 100.0
        out[b] = ('A' if anteil <= GRENZE_A + EPS else 'B' if anteil <= GRENZE_B + EPS
                  else 'C', anteil, rang)
    return out


def main():
    if not 0 < F_B < F_A <= 1:
        sys.exit('Schwellen ungueltig: 0 < F_B < F_A <= 1 noetig')
    lauf = finde_lauf()
    with open(lauf / 'nwa_klassen.csv', encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f, delimiter=';')
        zeilen, kopf = list(r), r.fieldnames or []
    ziele = [s[len('B_ges_'):] for s in kopf if s.startswith('B_ges_')]
    if not ziele:
        sys.exit('nwa_klassen.csv ohne Spalte B_ges_<ziel> - nwa.py ausfuehren')

    for z in zeilen:
        for g in ziele:
            z[f'NW_{g}'] = zahl(z[f'NW_{g}'], f'{z["klasse_id"]}.NW_{g}')
            z[f'B_ges_{g}'] = zahl(z[f'B_ges_{g}'], f'{z["klasse_id"]}.B_ges_{g}')

    bauteile = [(m, z) for z in zeilen
                for m in sorted(filter(None, z['instanzen'].split('|')), key=natkey)]
    doppelt = [m for m, n in Counter(m for m, _ in bauteile).items() if n > 1]
    if doppelt:
        sys.exit('Bauteile in mehreren Klassen: ' + ', '.join(doppelt))
    klasse_von = {m: z['klasse_id'] for m, z in bauteile}
    bges = {g: {m: z[f'B_ges_{g}'] for m, z in bauteile} for g in ziele}

    log(f'Laufordner : {lauf.name}')
    log(f'Klassen    : {len(zeilen)},  Bauteile: {len(bauteile)},  Zielgroessen: {", ".join(ziele)}')
    log(f'Spalte abc : {"relativ" if ABC_RELATIV else "kumulativ"}')

    # --- Einteilung je Zielgroesse --------------------------------------------
    rel, kum = {}, {}
    for g in ziele:
        rel[g], bmax = relativ(bges[g], F_A, F_B)
        kum[g] = kumulativ(bges[g], klasse_von)
        log(f'\n{g}:  B_max = {bmax:.2f},  Summe B_ges = {sum(bges[g].values()):.2f}')
        log(f'  relativ   (A >= {F_A * bmax:.2f}, B >= {F_B * bmax:.2f}) : '
            + verteilung(rel[g].values()))
        log(f'  kumulativ ({GRENZE_A:.0f} / {GRENZE_B:.0f} %)          : '
            + verteilung(c for c, _, _ in kum[g].values()))
        je_klasse = defaultdict(set)
        for m in bges[g]:
            je_klasse[klasse_von[m]].add(kum[g][m][0])
        artefakte = sorted(k for k, s in je_klasse.items() if len(s) > 1)
        if artefakte:
            log(f'  Gleichstandsartefakte kumulativ: {", ".join(artefakte)}')
        log(f'  {"Klasse":40s} {"n":>2s} {"AS":>3s} {"B_ges":>7s}  rel  kum')
        for z in sorted(zeilen, key=lambda z: (-z[f'B_ges_{g}'], z['klasse_id']))[:10]:
            mem = [m for m in z['instanzen'].split('|') if m]
            log(f'  {z["klasse_id"]:40s} {len(mem):2d} {z["AS"]:>3s} {z[f"B_ges_{g}"]:7.2f}  '
                f'{zusammen(rel[g][m] for m in mem):4s} {zusammen(kum[g][m][0] for m in mem)}')

    # --- Gesamt: beste Klasse je Bauteil -------------------------------------
    ges_rel = {m: beste(rel[g][m] for g in ziele) for m, _ in bauteile}
    ges_kum = {m: beste(kum[g][m][0] for g in ziele) for m, _ in bauteile}
    abc = ges_rel if ABC_RELATIV else ges_kum
    je_ziel = rel if ABC_RELATIV else {g: {m: v[0] for m, v in kum[g].items()} for g in ziele}
    massgebend = {m: '+'.join(g for g in ziele if je_ziel[g][m] == abc[m]) for m, _ in bauteile}

    # --- analysis_result.csv --------------------------------------------------
    kopf = ['bauteil', 'klasse_id', 'typ', 'funktion', 'pfad', 'AS']
    for g in ziele:
        kopf += [f'NW_{g}', f'B_ges_{g}', f'rang_{g}', f'kum_{g}', f'abc_rel_{g}', f'abc_kum_{g}']
    kopf += ['abc_relativ', 'abc_kumulativ', 'abc', 'massgebend']
    reihe = sorted(bauteile, key=lambda mz: (RANG[abc[mz[0]]],
                                             min(kum[g][mz[0]][2] for g in ziele),
                                             natkey(mz[0])))
    aus = []
    for m, z in reihe:
        zeile = [m, z['klasse_id'], z['typ'], z['funktion'], z['pfad'], z['AS']]
        for g in ziele:
            c, anteil, rang = kum[g][m]
            zeile += [f'{z[f"NW_{g}"]:.4f}', f'{bges[g][m]:.2f}', rang, f'{anteil:.2f}',
                      rel[g][m], c]
        zeile += [ges_rel[m], ges_kum[m], abc[m], massgebend[m]]
        aus.append(zeile)
    with open(lauf / 'analysis_result.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(kopf)
        w.writerows(aus)

    # --- Konsole --------------------------------------------------------------
    log('\nGesamt (beste Klasse je Bauteil ueber die Zielgroessen)')
    log('  relativ   : ' + verteilung(ges_rel.values()))
    log('  kumulativ : ' + verteilung(ges_kum.values()))
    diff = sorted((m for m in ges_rel if ges_rel[m] != ges_kum[m]), key=natkey)
    log(f'  verschieden zwischen relativ und kumulativ: {len(diff)} Bauteile')
    for m in diff[:15]:
        log(f'     {m:32s} relativ {ges_rel[m]}   kumulativ {ges_kum[m]}')
    if len(diff) > 15:
        log(f'     ... {len(diff) - 15} weitere (analysis_result.csv)')

    if SENSITIVITAET:
        log('\nSensitivitaet relativ (gesamt, beste Klasse je Bauteil)')
        for fa, fb in SENSITIVITAET:
            r_ = {g: relativ(bges[g], fa, fb)[0] for g in ziele}
            log(f'  F_A = {fa:.2f}  F_B = {fb:.2f} : '
                + verteilung(beste(r_[g][m] for g in ziele) for m, _ in bauteile))

    log('\nAusgabe: analysis_result.csv, abc_log.txt')
    (lauf / 'abc_log.txt').write_text('\n'.join(LOG) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()