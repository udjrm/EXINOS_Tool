"""build_dsm.py — DSM auf Klassenebene: direkte Regeln + Wirkketten

Aufruf : python build_dsm.py          (Einstellungen: Konstanten unten)
Liest  : Exports/instances.csv, Exports/edges.csv, Exports/classes.csv
         (aus lese_anlage.py und refine_wl.py), scoring_rules.csv,
         wirkketten.csv (optional)
Gibt   : Exports/<Zeitstempel>/
           dsm_matrix.csv   DSM; Kopf = klasse_id, letzte Spalte AS, letzte Zeile PS
                            (Eingang fuer nwa.py)
           dsm_edges.csv    jeder Eintrag mit Herkunft: direkte Regel oder
                            Wirkkette mit Pfad
         Die Eingabedateien werden in denselben Ordner verschoben.
         Pruefwerte (Paare ohne Regel, isolierte Klassen, Gl. 5.1, nie
         ausgeloeste Regeln, Wirkketten ohne Treffer) nur in der Konsole.

Direkte Regeln : Gewicht je gerichtetem Typpaar und Domaene; spezifische Regel
                 vor Platzhalter '*'.
Wirkketten     : Einfluss ueber eine Kette von Klassen, ausgewertet auf dem
                 Klassengraphen (A1). Mechanische Kanten in beide Richtungen,
                 Signale nur in Signalrichtung, jede Klasse hoechstens einmal
                 je Pfad.
Kombination    : w_KL = max(w_direkt, w_kette)
Pfadsyntax     : 'a > b? > c|d'   '>' Schritt, '|' Alternative, '?' optional
Bezeichner     : klasse_id aus classes.csv (stabil); class_id legt nur die
                 Reihenfolge fest.
"""

import csv
import sys
import shutil
import pathlib
import itertools
import os
from datetime import datetime
from collections import defaultdict, Counter

# --- Einstellungen ----------------------------------------------------------
MIT_KETTEN = True                   # False: nur direkte Regeln (Methodenvergleich)
CONFIG_DIR = pathlib.Path(os.environ.get(
    'EXINOS_CONFIG_DIR', pathlib.Path(__file__).resolve().parent
))
REGELN     = str(CONFIG_DIR / 'scoring_rules.csv')
KETTEN     = str(CONFIG_DIR / 'wirkketten.csv')
# -----------------------------------------------------------------------------

EXPORT_DIR = pathlib.Path(os.environ.get(
    'EXINOS_EXPORT_DIR',
    pathlib.Path(__file__).resolve().parent / 'Exports',
))
DIAG = 'X'
BENUTZT = set()


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lies(pfad):
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        return [{k: (v or '').strip() for k, v in z.items() if k}
                for z in csv.DictReader(f, delimiter=';')]


def archiviere():
    """Verschiebt alle Dateien aus Exports/ in einen neuen Laufordner."""
    EXPORT_DIR.mkdir(exist_ok=True)
    if os.environ.get('EXINOS_FLAT_RUN') == '1':
        return EXPORT_DIR
    lauf = EXPORT_DIR / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    lauf.mkdir()
    for p in [p for p in EXPORT_DIR.iterdir() if p.is_file()]:
        shutil.move(str(p), lauf / p.name)
    return lauf


def lade_regeln():
    return {(r['from_type'], r['to_type'], r['domain']): (int(r['weight']), r['regel'])
            for r in lies(REGELN)}


def gewicht(regeln, ta, tb, dom):
    for key in ((ta, tb, dom), (ta, tb, '*'), ('*', tb, dom), ('*', tb, '*'),
                (ta, '*', dom), (ta, '*', '*'), ('*', '*', dom), ('*', '*', '*')):
        if key in regeln:
            BENUTZT.add(key)
            w, reg = regeln[key]
            return w, reg, True
    return 0, 'default-0', False


# ---------------------------------------------------------------------------
# Wirkketten
# ---------------------------------------------------------------------------

def parse_pfad(pfad):
    schritte = []
    for teil in pfad.split('>'):
        teil = teil.strip()
        opt = teil.endswith('?')
        typen = frozenset(t.strip() for t in teil.rstrip('?').split('|') if t.strip())
        if not typen:
            raise ValueError(f"leerer Schritt in '{pfad}'")
        schritte.append((typen, opt))
    return schritte


def varianten(schritte):
    """Alle Typfolgen mit und ohne optionale Schritte (mind. 2 Schritte)."""
    opt_idx = [i for i, (_, o) in enumerate(schritte) if o]
    out = []
    for wahl in itertools.product((True, False), repeat=len(opt_idx)):
        mit = dict(zip(opt_idx, wahl))
        seq = tuple(t for i, (t, o) in enumerate(schritte) if not o or mit[i])
        if len(seq) >= 2 and seq not in out:
            out.append(seq)
    return out


def lade_ketten():
    if not pathlib.Path(KETTEN).exists():
        return []
    ketten = []
    for r in lies(KETTEN):
        schritte = parse_pfad(r['pfad'])
        ketten.append({'id': r['id'], 'pfad': r['pfad'], 'gewicht': int(r['gewicht']),
                       'regel': r['regel'], 'schritte': schritte,
                       'varianten': varianten(schritte)})
    return ketten


def finde_paare(seq, nachf, ktyp):
    """Alle Klassenpaare (Start, Ende), die die Typfolge seq auf dem
       Klassengraphen erfuellen; je Paar der erste gefundene Pfad."""
    paare = {}

    def dfs(i, weg):
        k = weg[-1]
        if i == len(seq) - 1:
            if weg[0] != k:
                paare.setdefault((weg[0], k), list(weg))
            return
        for m in sorted(nachf[k]):
            if m not in weg and ktyp[m] in seq[i + 1]:
                weg.append(m)
                dfs(i + 1, weg)
                weg.pop()

    for k in sorted(ktyp):
        if ktyp[k] in seq[0]:
            dfs(0, [k])
    return paare


def kette_betrifft_modell(kette, typen):
    return all(o or (t & typen) for t, o in kette['schritte'])


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def schreibe_csv(pfad, kopf, zeilen):
    with open(pfad, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(kopf)
        w.writerows(zeilen)


def kennzahlen(mat, ids):
    AS = {a: sum(mat[a][b] for b in ids if b != a) for a in ids}
    PS = {b: sum(mat[a][b] for a in ids if a != b) for b in ids}
    felder = sum(1 for a in ids for b in ids if a != b and mat[a][b] > 0)
    return AS, PS, felder


def schreibe_matrix(pfad, mat, ids, kopf):
    AS, PS, _ = kennzahlen(mat, ids)
    zeilen = [[kopf[a]] + [DIAG if a == b else mat[a][b] for b in ids] + [AS[a]]
              for a in ids]
    zeilen.append(['PS'] + [PS[b] for b in ids] + [''])
    schreibe_csv(pfad, [''] + [kopf[c] for c in ids] + ['AS'], zeilen)


# ---------------------------------------------------------------------------

def main():
    lauf = archiviere()
    print(f"Ausgabeordner: {lauf.name}")

    regeln = lade_regeln()
    ketten = lade_ketten() if MIT_KETTEN else []
    inst = {r['instanz']: r for r in lies(lauf / 'instances.csv')}
    klassen = lies(lauf / 'classes.csv')
    kanten = lies(lauf / 'edges.csv')
    if klassen and 'klasse_id' not in klassen[0]:
        sys.exit("classes.csv ohne Spalte 'klasse_id' - refine_wl.py erneut ausfuehren")

    kls, label, kid, ktyp, mitglieder = {}, {}, {}, {}, defaultdict(list)
    for r in klassen:
        cid = r['class_id']
        label[cid], kid[cid], ktyp[cid] = r['label'], r['klasse_id'], r['typ']
        for i in r['instanzen'].split('|'):
            kls[i] = cid
            mitglieder[cid].append(i)
    ids = sorted(label)

    # --- direkte Regeln ------------------------------------------------------
    direkt, ungetroffen, bewusst_null = {}, defaultdict(int), defaultdict(int)
    inst_row, inst_col = defaultdict(dict), defaultdict(dict)
    nachf = defaultdict(set)                       # Klassengraph fuer Wirkketten

    for r in kanten:
        a, b, dom = r['from'], r['to'], r['domain']
        if a not in kls or b not in kls:
            continue
        gerichtet = r.get('gerichtet') == '1'
        if kls[a] != kls[b]:
            nachf[kls[a]].add(kls[b])
            if not gerichtet:
                nachf[kls[b]].add(kls[a])
        ta, tb = inst[a]['typ'], inst[b]['typ']
        richtungen = ((a, b, ta, tb),) if gerichtet else ((a, b, ta, tb), (b, a, tb, ta))
        for x, y, tx, ty in richtungen:
            w, reg, hit = gewicht(regeln, tx, ty, dom)
            if not hit:
                ungetroffen[(tx, ty, dom)] += 1
            elif w == 0:
                bewusst_null[(tx, ty, dom)] += 1
            ka, kb = kls[x], kls[y]
            if w == 0 or ka == kb:
                continue
            if (ka, kb, dom) not in direkt or w > direkt[(ka, kb, dom)][0]:
                direkt[(ka, kb, dom)] = (w, reg)
            inst_row[x][kb] = max(inst_row[x].get(kb, 0), w)
            inst_col[y][ka] = max(inst_col[y].get(ka, 0), w)

    mat_d = defaultdict(lambda: defaultdict(int))
    for (ka, kb, _), (w, _) in direkt.items():
        mat_d[ka][kb] = max(mat_d[ka][kb], w)

    # --- Wirkketten ----------------------------------------------------------
    kette_w, treffer_je = {}, Counter()            # (ka, kb) -> (w, id, pfad)
    for k in ketten:
        paare = {}
        for seq in k['varianten']:
            for p, weg in finde_paare(seq, nachf, ktyp).items():
                paare.setdefault(p, weg)
        treffer_je[k['id']] = len(paare)
        for p, weg in sorted(paare.items()):
            if p not in kette_w or k['gewicht'] > kette_w[p][0]:
                kette_w[p] = (k['gewicht'], k['id'], weg)

    mat = defaultdict(lambda: defaultdict(int))
    for a in ids:
        for b in ids:
            mat[a][b] = mat_d[a][b]
    angehoben = 0
    for (ka, kb), (w, _, _) in kette_w.items():
        if w > mat[ka][kb]:
            mat[ka][kb] = w
            angehoben += 1

    # --- Ausgabe -------------------------------------------------------------
    schreibe_matrix(lauf / 'dsm_matrix.csv', mat, ids, kid)

    regel_von = {k['id']: k['regel'] for k in ketten}
    zeilen = [[kid[a], label[a], kid[b], label[b], w, dom, 'direkt', reg, '']
              for (a, b, dom), (w, reg) in sorted(direkt.items())]
    zeilen += [[kid[a], label[a], kid[b], label[b], w, 'kette', kn, regel_von[kn],
                ' > '.join(kid[c] for c in weg)]
               for (a, b), (w, kn, weg) in sorted(kette_w.items())]
    schreibe_csv(lauf / 'dsm_edges.csv',
                 ['from', 'from_label', 'to', 'to_label', 'weight', 'domain',
                  'herkunft', 'regel', 'pfad'], zeilen)

    # --- Pruefwerte ----------------------------------------------------------
    typen = {inst[i]['typ'] for i in kls}

    def betrifft_modell(k):
        return (k[0] == '*' or k[0] in typen) and (k[1] == '*' or k[1] in typen)

    unbenutzt = [k for k in regeln if k not in BENUTZT]
    tot = sorted(k for k in unbenutzt if betrifft_modell(k))
    fremd = len(unbenutzt) - len(tot)

    verletzt = []                                  # Gl. 5.1 auf direkten Instanzzeilen
    for c in ids:
        mem = mitglieder[c]
        z = {tuple(sorted(inst_row[m].items())) for m in mem}
        s = {tuple(sorted(inst_col[m].items())) for m in mem}
        if len(z) > 1 or len(s) > 1:
            verletzt.append((label[c], len(mem), len(z), len(s)))

    # --- Konsole -------------------------------------------------------------
    n = len(ids)
    AS_d, _, felder_d = kennzahlen(mat_d, ids)
    AS, PS, felder = kennzahlen(mat, ids)
    isoliert = [c for c in ids if AS[c] + PS[c] == 0]

    print(f"Modus        : {'direkt + Wirkketten' if MIT_KETTEN else 'nur direkt'}")
    print(f"DSM          : {n}x{n}")
    print(f"               {'direkt':>8s} {'gesamt':>8s}")
    print(f"  Felder != 0: {felder_d:8d} {felder:8d}")
    print(f"  AS = PS    : {sum(AS_d.values()):8d} {sum(AS.values()):8d}"
          f"   (Kontrolle {sum(PS.values())})")
    print(f"  Nullanteil : {100 * (1 - felder_d / (n * (n - 1))):7.1f}% "
          f"{100 * (1 - felder / (n * (n - 1))):7.1f}%")

    if MIT_KETTEN:
        if not ketten:
            print(f"\nWirkketten   : {KETTEN} nicht gefunden -> nur direkt")
        else:
            print(f"\nWirkketten   : {len(ketten)} Regeln, {sum(treffer_je.values())} Treffer, "
                  f"{angehoben} Felder angehoben")
            for k in ketten:
                if treffer_je[k['id']]:
                    print(f"  {k['id']:5s} {treffer_je[k['id']]:3d} Paare   {k['regel']}")
            ohne = [k for k in ketten if not treffer_je[k['id']]]
            relevant = [k for k in ohne if kette_betrifft_modell(k, typen)]
            if ohne:
                print(f"  ohne Treffer: {len(ohne)} "
                      f"(davon Typen im Modell vorhanden: {len(relevant)})")
                for k in relevant:
                    print(f"     {k['id']:5s} {k['pfad']}")

    print("\nPruefwerte")
    print(f"  ohne Regel                 : {len(ungetroffen):3d} Typpaare   (sollte 0 sein)")
    for tx, ty, dom in sorted(ungetroffen):
        print(f"     {tx} -> {ty} [{dom}]")
    print(f"  isolierte Klassen          : {len(isoliert):3d}            (sollte 0 sein)")
    for c in isoliert:
        print(f"     {label[c]}")
    print(f"  Gl. 5.1 verletzt           : {len(verletzt):3d} Klassen    (sollte 0 sein)")
    for lab, nm, nz, ns in verletzt:
        print(f"     {lab:50s} n={nm}  Zeilen={nz}  Spalten={ns}")
    print(f"  nie ausgeloeste Regeln     : {len(tot):3d}            (jede begruenden)")
    for k in tot:
        print(f"     {k[0]} -> {k[1]} [{k[2]}]  w={regeln[k][0]}  {regeln[k][1]}")
    print(f"  Regeln anderer Anlagen     : {fremd:3d}            (informativ)")
    print(f"  bewusst 0                  : {len(bewusst_null):3d} Typpaare")

    print("\nTop 15 Aktivsumme:")
    print(f"   {'Klasse':52s} {'AS dir':>6s} {'AS':>4s} {'PS':>4s}")
    for c in sorted(ids, key=lambda c: (-AS[c], -AS_d[c], c))[:15]:
        print(f"   {label[c]:52s} {AS_d[c]:6d} {AS[c]:4d} {PS[c]:4d}")


if __name__ == '__main__':
    main()