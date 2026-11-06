"""refine_wl.py — Aequivalenzklassen via Weisfeiler-Leman-Farbverfeinerung

Aufruf : python refine_wl.py [max_iter]      (Standard: 50 = bis zum Fixpunkt)
Liest  : Exports/instances.csv, Exports/edges.csv (aus lese_anlage.py),
         bauteilpool.json (Kurznamen)
Gibt   : Exports/classes.csv

Signatur je Knoten:
  eigene Farbe + je Domaene die MENGE der Nachbarfarben;
  gerichtete Kanten getrennt als <domaene>_out / <domaene>_in.

Eigenschaften:
  - Fixpunkt -> Bauteile einer Klasse haben identische Nachbarklassen (Gl. 5.1)
  - Menge    -> struktureller Zwilling aendert keine Klasse (A1)
  - nur Typen und Verbindungen gehen ein, keine Bewertungsgroesse (A2)

Bezeichner je Klasse:
  klasse_id  stabil: <typ>__<alphabetisch erstes Mitglied>.
             Die laufende Nummer K01..Kn ist positionsabhaengig und taugt
             nicht als Schluessel: kommt eine Klasse hinzu oder faellt eine
             weg, verschieben sich alle folgenden Nummern. Bereits
             abgegebene NWA-Bewertungen fielen dann still auf andere
             Klassen. klasse_id aendert sich nur, wenn sich die Klasse
             selbst aendert - insbesondere NICHT, wenn eine Funktions-
             benennung angepasst wird.
  label      lesbar und eindeutig: Kurzname + Funktion + Materialpfad + n
             + Vertreter in eckigen Klammern.
  class_id   K01..Kn, bleibt als Anzeige- und Sortierreihenfolge erhalten.

Funktionsbenennung (nur Beschriftung, nicht klassenbildend):
  Eine Spindel treibt eine Linearachse an - ob diese senkrecht (Hubachse)
  oder waagerecht verfaehrt, geht aus dem Graphen nicht hervor. Deshalb
  heisst die Funktion neutral 'Linearachse'. Messgeber uebernehmen die
  Funktion des gemessenen Bauteils, statt sie aus dem Nachbartyp zu raten.
"""

import re
import csv
import sys
import json
import hashlib
import pathlib
from collections import defaultdict, Counter

SIGNATUR = 'menge'              # 'menge' (A1-vertraeglich) oder 'multimenge'
POOL_DATEI = 'bauteilpool.json'
EXPORT_DIR = pathlib.Path(__file__).resolve().parent / 'Exports'

# Abtrieb einer Antriebskette -> Funktion
FUNKTION_ZIEL = {'abwickler': 'Abwickler', 'handhabungssystem': 'Handhabung',
                 'falteinheit': 'Falteinheit', 'spindel': 'Linearachse'}

# Typen, deren Funktion ein Messgeber uebernehmen kann
GEMESSEN_TYPEN = ('linearfuehrung', 'lineareinheit', 'schwenkarm',
                  'handhabungssystem', 'stapeltisch')


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def farbe_von(sig):
    """Deterministischer Hash -> reproduzierbare Klassen ueber Laeufe hinweg."""
    return hashlib.sha1(repr(sig).encode('utf-8')).hexdigest()[:12]


def lade_kurznamen():
    for p in (pathlib.Path.cwd() / POOL_DATEI,
              pathlib.Path(__file__).resolve().with_name(POOL_DATEI)):
        if p.exists():
            with open(p, encoding='utf-8') as f:
                return {t['typ']: t.get('kurz', t['typ']) for t in json.load(f)['typen']}
    return {}


def lade():
    with open(EXPORT_DIR / 'instances.csv', encoding='utf-8') as f:
        inst = {r['instanz']: r for r in csv.DictReader(f, delimiter=';')}
    adj = defaultdict(lambda: defaultdict(list))
    kanten = []
    with open(EXPORT_DIR / 'edges.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter=';'):
            a, b, d = r['from'], r['to'], r['domain']
            g = r.get('gerichtet') == '1'
            kanten.append((a, b, d, g))
            if g:
                adj[a][f'{d}_out'].append(b)
                adj[b][f'{d}_in'].append(a)
            else:
                adj[a][d].append(b)
                adj[b][d].append(a)
    return inst, adj, kanten


# ---------------------------------------------------------------------------
# Farbverfeinerung
# ---------------------------------------------------------------------------

def _partition(farbe):
    p = defaultdict(set)
    for n, c in farbe.items():
        p[c].add(n)
    return frozenset(frozenset(s) for s in p.values())


def wl(inst, adj, scope, domains, max_iter):
    farbe = {n: inst[n]['typ'] for n in scope}
    tiefe = {n: 0 for n in scope}
    fixpunkt = False
    print(f"  Iteration 0: {len(_partition(farbe))} Klassen")
    for k in range(1, max_iter + 1):
        neu = {}
        for n in scope:
            sig = [farbe[n]]
            for d in domains:
                nb = [farbe[m] for m in adj[n].get(d, []) if m in scope]
                if SIGNATUR == 'menge':
                    nb = set(nb)
                sig.append((d, tuple(sorted(nb))))
            neu[n] = farbe_von(tuple(sig))
        alt_p, neu_p = _partition(farbe), _partition(neu)
        if alt_p == neu_p:
            fixpunkt = True
            print(f"  Fixpunkt erreicht (Iteration {k} aendert nichts)")
            break
        for n in scope:
            a = next(s for s in alt_p if n in s)
            b = next(s for s in neu_p if n in s)
            if a != b:
                tiefe[n] = k
        farbe = neu
        print(f"  Iteration {k}: {len(neu_p)} Klassen")
    if not fixpunkt:
        print(f"  WARNUNG: Fixpunkt nach {max_iter} Iterationen nicht erreicht "
              f"-> Gl. 5.1 nicht garantiert")
    return farbe, tiefe, fixpunkt


# ---------------------------------------------------------------------------
# Funktion je Bauteil (nur Beschriftung)
# ---------------------------------------------------------------------------

def bestimme_rollen(inst, kanten):
    """Ermittelt eine Funktionsbezeichnung je Bauteil.

    Zwei Durchgaenge: zuerst die Fuehrungen und Achsen, dann alles, was
    seine Funktion von ihnen erbt. Ohne diese Reihenfolge haette ein
    Wegaufnehmer die Funktion seines Nachbarn noch nicht kennen koennen.
    """
    typ = lambda n: inst[n]['typ']
    nb, planar_nb = defaultdict(set), defaultdict(set)
    welle_ab, sig_aus = defaultdict(set), defaultdict(set)
    for a, b, d, g in kanten:
        nb[a].add(b)
        nb[b].add(a)
        if d == 'planar':                   # Lagerung, Fuehrung, Lagemessung
            planar_nb[a].add(b)
            planar_nb[b].add(a)
        if d == 'rotary':
            welle_ab[a].add(b)              # gespeichert in Wirkrichtung
        if g:
            sig_aus[a].add(b)

    def abtrieb(n, tiefe=0):
        for m in sorted(welle_ab[n], key=natkey):
            if typ(m) in FUNKTION_ZIEL:
                return FUNKTION_ZIEL[typ(m)]
            if typ(m) == 'riementrieb' and tiefe < 3:
                r = abtrieb(m, tiefe + 1)
                if r:
                    return r
        return ''

    rolle = {}

    # Durchgang 1: Fuehrungen - sie geben die Funktion an die Messgeber weiter
    for n in inst:
        if typ(n) != 'linearfuehrung':
            continue
        nbt = {typ(m) for m in nb[n]}
        if 'spindel' in nbt:
            rolle[n] = 'Linearachse'
        elif nbt & {'druckluftzylinder', 'taenzerwalze'}:
            rolle[n] = 'Taenzer'

    # Durchgang 2: Antriebsstraenge, Messgeber, Messwalzen
    for n in inst:
        t = typ(n)
        nbt = {typ(m) for m in nb[n]}
        if t in ('antrieb', 'riementrieb'):
            rolle[n] = abtrieb(n)
        elif t == 'wegaufnehmer':
            # Der Wegaufnehmer uebernimmt die Funktion des gemessenen
            # Bauteils. Massgeblich sind nur planare Nachbarn, nicht die
            # Signalempfaenger - sonst erbte er die Funktion des Antriebs,
            # den er beliefert.
            for m in sorted((m for m in planar_nb[n] if typ(m) in GEMESSEN_TYPEN),
                            key=natkey):
                if rolle.get(m):
                    rolle[n] = rolle[m]
                    break
                if typ(m) in FUNKTION_ZIEL:
                    rolle[n] = FUNKTION_ZIEL[typ(m)]
                    break
        elif t == 'messwalze':
            if any(typ(m) in ('antrieb', 'regelventil') for m in sig_aus[n]):
                rolle[n] = 'Regelkreis'
    return rolle


def klassen_wert(mem, werte):
    w = {werte.get(m, '') for m in mem}
    return w.pop() if len(w) == 1 else ''


def klassen_pfad(mem, inst):
    pf = set()
    for m in mem:
        pf |= {c for c in inst[m].get('pfad', '').split('+') if c}
    return '+'.join(sorted(pf))


def klassen_baugruppe(mem, inst):
    """Gemeinsame Baugruppe oder '' bei uneinheitlicher Belegung.

    In EXINOS umfasst eine Klasse Bauteile aus Abwicklung_An UND
    Abwicklung_Ka. Dann waere jede Einzelauswahl willkuerlich, deshalb
    bleibt das Feld in diesem Fall leer. Es dient nur der Information.
    """
    bg = {(inst[m].get('baugruppe') or '').strip() for m in mem}
    bg.discard('')
    return bg.pop() if len(bg) == 1 else ''


# ---------------------------------------------------------------------------
# Stabile Bezeichner
# ---------------------------------------------------------------------------

def pruefe_eindeutig(zeilen, spalte, name):
    """Bricht ab, wenn ein Bezeichner mehrfach vorkommt.

    Beide Bezeichner sind per Konstruktion eindeutig, solange die
    Bauteil-ids es sind (P-1 stellt das sicher). Die Pruefung faengt den
    Fall ab, dass die Bildungsvorschrift spaeter geaendert wird - still
    durchlaufen darf das nicht, weil sonst NWA-Bewertungen kollidieren.
    """
    doppelt = [w for w, n in Counter(z[spalte] for z in zeilen).items() if n > 1]
    if doppelt:
        sys.exit(f"\nAbbruch: {name} nicht eindeutig: {', '.join(sorted(doppelt))}")


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    max_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    print(f"max_iter = {max_iter},  Signatur = {SIGNATUR}")

    kurz = lade_kurznamen()
    inst, adj, kanten = lade()
    scope = set(inst)
    domains = sorted({d for n in adj for d in adj[n]})
    print(f"Betrachtet: {len(scope)} Bauteile,  Domaenen: {', '.join(domains)}\n")

    farbe, tiefe, fixpunkt = wl(inst, adj, scope, domains, max_iter)
    rolle = bestimme_rollen(inst, kanten)

    gruppen = defaultdict(list)
    for n in scope:
        gruppen[farbe[n]].append(n)
    for mem in gruppen.values():
        mem.sort(key=natkey)

    reihenfolge = sorted(gruppen.values(),
                         key=lambda mem: (-len(mem), inst[mem[0]]['typ'], natkey(mem[0])))

    namen, zeilen = Counter(), []
    for i, mem in enumerate(reihenfolge, 1):
        cid = f'K{i:02d}'
        typ = inst[mem[0]]['typ']
        funk = klassen_wert(mem, rolle)
        pfad = klassen_pfad(mem, inst)
        bgrp = klassen_baugruppe(mem, inst)

        # Vertreter: erstes Mitglied in natuerlicher Sortierung.
        # natkey ist deterministisch und nicht von der Spracheinstellung
        # des Rechners abhaengig - anders als locale-basierte Sortierung.
        vertreter = mem[0]
        klasse_id = f'{typ}__{vertreter}'

        name = '_'.join(filter(None, [kurz.get(typ, typ), funk, pfad]))
        namen[name] += 1
        label = f'{cid}_{name}_n{len(mem)}_[{vertreter}]'

        zeilen.append({
            'class_id': cid,
            'klasse_id': klasse_id,
            'label': label,
            'typ': typ,
            'funktion': funk,
            'baugruppe': bgrp,
            'pfad': pfad,
            'vertreter': vertreter,
            'n': len(mem),
            'wl_tiefe': max(tiefe[m] for m in mem),
            'instanzen': '|'.join(mem),
        })

    pruefe_eindeutig(zeilen, 'klasse_id', 'klasse_id')
    pruefe_eindeutig(zeilen, 'label', 'label')

    kopf = ['class_id', 'klasse_id', 'label', 'typ', 'funktion', 'baugruppe',
            'pfad', 'vertreter', 'n', 'wl_tiefe', 'instanzen']
    EXPORT_DIR.mkdir(exist_ok=True)
    with open(EXPORT_DIR / 'classes.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=kopf, delimiter=';')
        w.writeheader()
        w.writerows(zeilen)

    print(f"\n-> {len(gruppen)} Klassen  (Fixpunkt: {'ja' if fixpunkt else 'NEIN'})")

    print("\nKlassen je Typ:")
    for typ, anz in Counter(inst[m[0]]['typ'] for m in gruppen.values()).most_common():
        ges = sum(len(m) for m in gruppen.values() if inst[m[0]]['typ'] == typ)
        print(f"  {kurz.get(typ, typ):18s} {anz:2d} Klassen / {ges:2d} Bauteile")

    print("\nBezeichner")
    print(f"  klasse_id eindeutig        : ja  ({len(zeilen)} Klassen)")
    print(f"  label eindeutig            : ja")
    doppelt = [k for k, v in namen.items() if v > 1]
    print(f"  gleiche Funktionsbenennung : {len(doppelt):3d}   "
          f"(informativ, durch Vertreter aufgeloest)")
    for k in doppelt:
        print(f"     {k}: {namen[k]}x")

    print("\nKlassen:")
    for z in zeilen:
        print(f"   {z['klasse_id']:34s} {z['label']}")