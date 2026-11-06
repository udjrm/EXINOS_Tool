"""build_dsm.py — DSM auf Klassenebene: direkte Regeln + Wirkketten

Aufruf : python build_dsm.py [--ohne-ketten]
Liest  : Exports/instances.csv, Exports/edges.csv, Exports/classes.csv,
         scoring_rules.csv,
         wirkketten.csv (optional)
Gibt   : dsm_matrix.csv           DSM mit klasse_id als Kopfzeile (maschinenlesbar)
         dsm_matrix_label.csv     dieselbe DSM mit Labels (zum Lesen)
         dsm_matrix_direkt.csv    DSM nur aus direkten Regeln (Vergleich)
         dsm_edges.csv            alle Eintraege mit Herkunft
         wirkketten_treffer.csv   Treffer je Wirkkette mit Pfad
         unmatched_pairs.csv      Typpaare ohne Regel / bewusst 0
         unused_rules.csv         nie ausgeloeste direkte Regeln
         eq51_check.csv           Klassen mit Verletzung von Gl. 5.1
         (alle Ausgaben nach Exports/<Zeitstempel>/)

Direkte Regeln : Gewicht je gerichtetem Typpaar und Domaene.
Wirkketten     : Einfluss ueber eine Kette von Klassen; ausgewertet auf dem
                 Klassengraphen (A1), nur physikalischer Einfluss (A2).
                 Mechanische Kanten in beide Richtungen, Signale nur in
                 Signalrichtung, jede Klasse hoechstens einmal je Pfad.
Kombination    : w_KL = max(w_direkt, w_kette)
Pfadsyntax     : 'a > b? > c|d'   '>' Schritt, '|' Alternative, '?' optional

Bezeichner     : Als Schluessel nach aussen dient klasse_id aus classes.csv
                 (stabil). Die laufende Nummer class_id steuert nur noch die
                 Zeilen- und Spaltenreihenfolge.

Zahlenformat   : Alle Groessen dieses Schrittes (DSM-Zellen, AS, PS, n) sind
                 ganzzahlig. zahlformat.py wird hier bewusst nicht benoetigt;
                 es kommt erst bei NW und B_ges zum Einsatz.
"""

import csv
import sys
import pathlib
import itertools
import shutil
from datetime import datetime
from collections import defaultdict, Counter

DEFAULT_WEIGHT = 0
DIAG = 'X'
KETTEN_DATEI = 'wirkketten.csv'
KETTE_DOM = 'kette'
BENUTZT = set()
EXPORT_DIR = pathlib.Path(__file__).resolve().parent / 'Exports'
RUN_DIR = EXPORT_DIR


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lies(name):
    with open(name, encoding='utf-8-sig', newline='') as f:
        return [{k: (v or '').strip() for k, v in z.items() if k}
                for z in csv.DictReader(f, delimiter=';')]


def export_pfad(name):
    return RUN_DIR / name


def archiviere_exports():
    global RUN_DIR
    EXPORT_DIR.mkdir(exist_ok=True)
    archiv = EXPORT_DIR / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    archiv.mkdir()
    dateien = [p for p in EXPORT_DIR.iterdir() if p.is_file()]
    for datei in dateien:
        shutil.move(str(datei), archiv / datei.name)
    RUN_DIR = archiv
    return archiv


def lade_regeln(pfad='scoring_rules.csv'):
    return {(r['from_type'], r['to_type'], r['domain']): (int(r['weight']), r['regel'])
            for r in lies(pfad)}


def gewicht(regeln, ta, tb, dom):
    for key in ((ta, tb, dom), (ta, tb, '*'), ('*', tb, dom), ('*', tb, '*'),
                (ta, '*', dom), (ta, '*', '*'), ('*', '*', dom), ('*', '*', '*')):
        if key in regeln:
            BENUTZT.add(key)
            w, reg = regeln[key]
            return w, reg, True
    return DEFAULT_WEIGHT, 'default-0', False


# ---------------------------------------------------------------------------
# Wirkketten
# ---------------------------------------------------------------------------

def parse_pfad(pfad):
    schritte = []
    for teil in pfad.split('>'):
        teil = teil.strip()
        if not teil:
            raise ValueError(f"leerer Schritt in '{pfad}'")
        opt = teil.endswith('?')
        if opt:
            teil = teil[:-1].strip()
        typen = frozenset(t.strip() for t in teil.split('|') if t.strip())
        if not typen:
            raise ValueError(f"Schritt ohne Typ in '{pfad}'")
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
    if not pathlib.Path(KETTEN_DATEI).exists():
        return []
    ketten = []
    for r in lies(KETTEN_DATEI):
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

def schreibe_csv(name, kopf, zeilen):
    RUN_DIR.mkdir(exist_ok=True)
    with open(export_pfad(name), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(kopf)
        w.writerows(zeilen)


def kennzahlen(mat, ids):
    AS = {a: sum(mat[a][b] for b in ids if b != a) for a in ids}
    PS = {b: sum(mat[a][b] for a in ids if a != b) for b in ids}
    felder = sum(1 for a in ids for b in ids if a != b and mat[a][b] > 0)
    return AS, PS, felder


def schreibe_matrix(name, mat, ids, kopf):
    """Schreibt die DSM. 'kopf' bestimmt die Beschriftung je Klasse -
       klasse_id fuer die maschinenlesbare, label fuer die lesbare Fassung."""
    AS, PS, _ = kennzahlen(mat, ids)
    zeilen = [[kopf[a]] + [DIAG if a == b else mat[a][b] for b in ids] + [AS[a]]
              for a in ids]
    zeilen.append(['PS'] + [PS[b] for b in ids] + [''])
    schreibe_csv(name, [''] + [kopf[c] for c in ids] + ['AS'], zeilen)


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    mit_ketten = '--ohne-ketten' not in sys.argv

    archiv = archiviere_exports()
    print(f"Ausgabeordner: {archiv.name}")

    regeln = lade_regeln()
    ketten = lade_ketten() if mit_ketten else []
    inst = {r['instanz']: r for r in lies(export_pfad('instances.csv'))}
    klassen = lies(export_pfad('classes.csv'))
    kanten = lies(export_pfad('edges.csv'))

    if klassen and 'klasse_id' not in klassen[0]:
        sys.exit("classes.csv ohne Spalte 'klasse_id' - bitte refine_wl.py "
                 "in der aktuellen Fassung erneut ausfuehren.")

    kls, label, kid, ktyp, mitglieder = {}, {}, {}, {}, defaultdict(list)
    for r in klassen:
        cid = r['class_id']
        label[cid] = r['label']
        kid[cid] = r['klasse_id']
        ktyp[cid] = r['typ']
        for i in r['instanzen'].split('|'):
            kls[i] = cid
            mitglieder[cid].append(i)
    ids = sorted(label)

    # --- direkte Regeln ----------------------------------------------------
    direkt, ungetroffen, bewusst_null = {}, defaultdict(int), defaultdict(int)
    inst_row, inst_col = defaultdict(dict), defaultdict(dict)
    nachf = defaultdict(set)                       # Klassengraph fuer Wirkketten

    for r in kanten:
        a, b, dom = r['from'], r['to'], r['domain']
        if a not in kls or b not in kls:
            continue
        gerichtet = r.get('gerichtet') == '1'
        ka0, kb0 = kls[a], kls[b]
        if ka0 != kb0:
            nachf[ka0].add(kb0)
            if not gerichtet:
                nachf[kb0].add(ka0)
        ta, tb = inst[a]['typ'], inst[b]['typ']
        richtungen = ((a, b, ta, tb),) if gerichtet else ((a, b, ta, tb), (b, a, tb, ta))
        for x, y, tx, ty in richtungen:
            w, reg, hit = gewicht(regeln, tx, ty, dom)
            if not hit:
                ungetroffen[(tx, ty, dom)] += 1
            elif w == 0:
                bewusst_null[(tx, ty, dom)] += 1
            if w == 0:
                continue
            ka, kb = kls[x], kls[y]
            if ka == kb:
                continue
            key = (ka, kb, dom)
            if key not in direkt or w > direkt[key][0]:
                direkt[key] = (w, reg)
            inst_row[x][kb] = max(inst_row[x].get(kb, 0), w)
            inst_col[y][ka] = max(inst_col[y].get(ka, 0), w)

    mat_d = defaultdict(lambda: defaultdict(int))
    for (ka, kb, _), (w, _) in direkt.items():
        mat_d[ka][kb] = max(mat_d[ka][kb], w)

    # --- Wirkketten --------------------------------------------------------
    kette_w = {}                                   # (ka,kb) -> (w, id, pfad)
    treffer, treffer_je = [], Counter()
    for k in ketten:
        paare = {}
        for seq in k['varianten']:
            for p, weg in finde_paare(seq, nachf, ktyp).items():
                paare.setdefault(p, weg)
        for (ka, kb), weg in sorted(paare.items()):
            treffer_je[k['id']] += 1
            alt = mat_d[ka][kb]
            hebt = k['gewicht'] > alt
            treffer.append([k['id'], kid[ka], label[ka], kid[kb], label[kb],
                            k['gewicht'], alt, 'ja' if hebt else 'nein',
                            ' > '.join(label[c] for c in weg)])
            if (ka, kb) not in kette_w or k['gewicht'] > kette_w[(ka, kb)][0]:
                kette_w[(ka, kb)] = (k['gewicht'], k['id'], weg)

    mat = defaultdict(lambda: defaultdict(int))
    for a in ids:
        for b in ids:
            mat[a][b] = mat_d[a][b]
    angehoben = 0
    for (ka, kb), (w, _, _) in kette_w.items():
        if w > mat[ka][kb]:
            mat[ka][kb] = w
            angehoben += 1

    # --- Ausgabe -----------------------------------------------------------
    schreibe_matrix('dsm_matrix.csv', mat, ids, kid)
    schreibe_matrix('dsm_matrix_label.csv', mat, ids, label)
    schreibe_matrix('dsm_matrix_direkt.csv', mat_d, ids, kid)

    dsm_kanten = [[kid[ka], label[ka], kid[kb], label[kb], w, dom, 'direkt', reg]
                  for (ka, kb, dom), (w, reg) in sorted(direkt.items())]
    regel_von = {k['id']: k['regel'] for k in ketten}
    for (ka, kb), (w, kettenid, _) in sorted(kette_w.items()):
        dsm_kanten.append([kid[ka], label[ka], kid[kb], label[kb], w, KETTE_DOM,
                           kettenid, regel_von[kettenid]])
    schreibe_csv('dsm_edges.csv',
                 ['from', 'from_label', 'to', 'to_label', 'weight', 'domain',
                  'herkunft', 'regel'], dsm_kanten)

    schreibe_csv('wirkketten_treffer.csv',
                 ['kette', 'from', 'from_label', 'to', 'to_label', 'gewicht_kette',
                  'gewicht_direkt', 'hebt_an', 'pfad'], treffer)

    nullen = []
    for d, st in ((ungetroffen, 'keine_regel'), (bewusst_null, 'regel_weight_0')):
        for (tx, ty, dom), n in sorted(d.items(), key=lambda x: -x[1]):
            nullen.append([tx, ty, dom, n, st])
    schreibe_csv('unmatched_pairs.csv',
                 ['from_type', 'to_type', 'domain', 'vorkommen', 'status'], nullen)

    typen = {inst[i]['typ'] for i in kls}

    def betrifft_modell(k):
        return (k[0] == '*' or k[0] in typen) and (k[1] == '*' or k[1] in typen)

    unbenutzt = [k for k in regeln if k not in BENUTZT]
    tot = sorted(k for k in unbenutzt if betrifft_modell(k))
    fremd = len(unbenutzt) - len(tot)
    schreibe_csv('unused_rules.csv',
                 ['from_type', 'to_type', 'domain', 'weight', 'regel', 'status'],
                 ([k[0], k[1], k[2], regeln[k][0], regeln[k][1],
                   'typen_vorhanden' if betrifft_modell(k) else 'andere_anlage']
                  for k in sorted(unbenutzt)))

    # Gl. 5.1 auf direkten Instanzzeilen (Wirkketten laufen auf dem Klassengraphen)
    verletzt = []
    for c in ids:
        mem = mitglieder[c]
        z = Counter(tuple(sorted(inst_row[m].items())) for m in mem)
        s = Counter(tuple(sorted(inst_col[m].items())) for m in mem)
        if len(z) > 1 or len(s) > 1:
            verletzt.append([kid[c], label[c], len(mem), len(z), len(s)])
    schreibe_csv('eq51_check.csv',
                 ['klasse_id', 'label', 'n', 'verschiedene_zeilen',
                  'verschiedene_spalten'], verletzt)

    # --- Konsole -----------------------------------------------------------
    n = len(ids)
    AS_d, PS_d, felder_d = kennzahlen(mat_d, ids)
    AS, PS, felder = kennzahlen(mat, ids)
    isoliert = [c for c in ids if AS[c] + PS[c] == 0]

    print(f"Modus        : {'direkt + Wirkketten' if mit_ketten else 'nur direkt (--ohne-ketten)'}")
    print(f"DSM          : {n}x{n}")
    print(f"               {'direkt':>8s} {'gesamt':>8s}")
    print(f"  Felder != 0: {felder_d:8d} {felder:8d}")
    print(f"  AS = PS    : {sum(AS_d.values()):8d} {sum(AS.values()):8d}"
          f"   (Kontrolle {sum(PS.values())})")
    print(f"  Nullanteil : {100 * (1 - felder_d / (n * (n - 1))):7.1f}% "
          f"{100 * (1 - felder / (n * (n - 1))):7.1f}%")

    if mit_ketten:
        if not ketten:
            print(f"\nWirkketten   : {KETTEN_DATEI} nicht gefunden -> nur direkt")
        else:
            print(f"\nWirkketten   : {len(ketten)} Regeln, {len(treffer)} Treffer, "
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
    for (tx, ty, dom) in sorted(ungetroffen):
        print(f"     {tx} -> {ty} [{dom}]")
    print(f"  isolierte Klassen          : {len(isoliert):3d}            (sollte 0 sein)")
    for c in isoliert:
        print(f"     {label[c]}")
    print(f"  Gl. 5.1 verletzt           : {len(verletzt):3d} Klassen    (sollte 0 sein)")
    for v in verletzt:
        print(f"     {v[1]:50s} n={v[2]}  Zeilen={v[3]}  Spalten={v[4]}")
    print(f"  nie ausgeloeste Regeln     : {len(tot):3d}            (jede begruenden)")
    print(f"  Regeln anderer Anlagen     : {fremd:3d}            (informativ)")
    print(f"  bewusst 0                  : {len(bewusst_null):3d} Typpaare")

    print("\nTop 15 Aktivsumme:")
    print(f"   {'Klasse':52s} {'AS dir':>6s} {'AS':>4s} {'PS':>4s}")
    for c in sorted(ids, key=lambda c: (-AS[c], -AS_d[c], c))[:15]:
        print(f"   {label[c]:52s} {AS_d[c]:6d} {AS[c]:4d} {PS[c]:4d}")