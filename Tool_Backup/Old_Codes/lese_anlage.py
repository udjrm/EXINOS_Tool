"""lese_anlage.py — Anlagenbeschreibung der UI -> Graph fuer Klassenbildung und DSM

Aufruf : python lese_anlage.py <ordner> [--rahmen]
         <ordner> enthaelt components.csv und connections.csv (Lastenheft Abschn. 6.3)
         --rahmen : zusaetzlicher Knoten 'Rahmen', der alle gestellfesten Bauteile lagert

Eingang: components.csv, connections.csv, bauteilpool.json
Ausgang: Exports/instances.csv, Exports/edges.csv, Exports/pruefung.txt

Schritte:
  1. Einlesen, Bauteilpool laden
  2. Pruefung nach Lastenheft Abschnitt 5 (bei Fehlern Abbruch ohne Ausgabe)
  3. Graph bilden
     - Materialbahn = Knoten; jedes Bauteil im Bahnlauf erhaelt eine Kante zur Bahn
       (Rollen koppeln nicht untereinander, sondern ueber die Bahn)
     - welle / lage / pneumatik: ungerichtet, gespeichert in Wirkrichtung von -> nach
     - signal: gerichtet (Sender -> Empfaenger)
     - optional: Rahmen -> jedes gestellfeste Bauteil
"""
import re
import csv
import sys
import json
import pathlib
from collections import defaultdict, Counter

POOL_DATEI = 'bauteilpool.json'
EXPORT_DIR = pathlib.Path(__file__).resolve().parent / 'Exports'
BAHN_TYP = 'materialbahn'
RAHMEN_ID = 'Rahmen'
RAHMEN_TYP = 'rahmen'
ID_MUSTER = re.compile(r'^[A-Za-z0-9_]+$')
KOMP_SPALTEN = ['id', 'typ', 'bezeichnung', 'materialpfad', 'baugruppe',
                'gestellfest', 'bemerkung']
VERB_SPALTEN = ['id', 'von', 'von_port', 'nach', 'nach_port', 'art', 'bahn']


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------
def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def lies_csv(pfad, spalten):
    if not pfad.exists():
        sys.exit(f'Datei nicht gefunden: {pfad}')
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f, delimiter=';')
        fehlend = [s for s in spalten if s not in (r.fieldnames or [])]
        if fehlend:
            sys.exit(f'{pfad.name}: Spalten fehlen: {", ".join(fehlend)}')
        return [{k: (v or '').strip() for k, v in z.items() if k} for z in r]


def finde_pool():
    for p in (pathlib.Path.cwd() / POOL_DATEI,
              pathlib.Path(__file__).resolve().with_name(POOL_DATEI)):
        if p.exists():
            return p
    sys.exit(f'{POOL_DATEI} nicht gefunden (Arbeitsordner oder Skriptordner)')


def lade_pool(pfad):
    with open(pfad, encoding='utf-8') as f:
        roh = json.load(f)
    typen = {}
    for t in roh['typen']:
        t = dict(t)
        t['ports'] = {p['name']: p for p in t.get('ports', [])}
        typen[t['typ']] = t
    return roh.get('version', ''), roh['verbindungsarten'], typen


# ---------------------------------------------------------------------------
# Pruefung (Lastenheft Abschnitt 5)
# ---------------------------------------------------------------------------
def pruefe(komps, verbs, arten, typen, mit_rahmen):
    fehler, warn, hinweis = [], [], []

    # P-1: eindeutige, gueltige ids
    for liste, was in ((komps, 'Bauteil'), (verbs, 'Verbindung')):
        for i, n in Counter(z['id'] for z in liste).items():
            if n > 1:
                fehler.append(('P-1', i, f'{was}-id mehrfach vergeben ({n}x)'))
        for z in liste:
            if not ID_MUSTER.match(z['id']):
                fehler.append(('P-1', z['id'] or '(leer)', f'{was}-id ungueltig'))
    k_von = {}
    for z in komps:
        k_von.setdefault(z['id'], z)
    if mit_rahmen and RAHMEN_ID in k_von:
        fehler.append(('P-1', RAHMEN_ID, 'id ist fuer den impliziten Rahmen reserviert'))

    # P-2: Typen im Pool
    for z in komps:
        if z['typ'] not in typen:
            fehler.append(('P-2', z['id'], f"Typ '{z['typ']}' nicht im Bauteilpool"))

    # P-2 / P-3 / P-5: Verbindungen
    belegung = Counter()
    bahn_kanten = defaultdict(list)
    verbunden = set()
    for v in verbs:
        vid = v['id']
        if v['art'] not in arten:
            fehler.append(('P-3', vid, f"Verbindungsart '{v['art']}' unbekannt"))
            continue
        ok = True
        for seite, soll in (('von', 'aus'), ('nach', 'ein')):
            kid, port = v[seite], v[f'{seite}_port']
            k = k_von.get(kid)
            if k is None:
                fehler.append(('P-2', vid, f"Bauteil '{kid}' existiert nicht"))
                ok = False
                continue
            t = typen.get(k['typ'])
            if t is None:
                ok = False
                continue
            p = t['ports'].get(port)
            if p is None:
                fehler.append(('P-2', vid, f"Port '{port}' gehoert nicht zu Typ '{k['typ']}'"))
                ok = False
                continue
            if p['art'] != v['art']:
                fehler.append(('P-3', vid, f"Port {kid}.{port} hat Art '{p['art']}', "
                                           f"Verbindung '{v['art']}'"))
                ok = False
            if p['richtung'] != soll:
                fehler.append(('P-3', vid, f"Port {kid}.{port} ist '{p['richtung']}', "
                                           f"erwartet '{soll}'"))
                ok = False
            belegung[(kid, port)] += 1
            verbunden.add(kid)

        if v['art'] == 'bahn':
            b = v['bahn']
            if not b:
                fehler.append(('P-5', vid, 'Bahnverbindung ohne Zuordnung zu einer Materialbahn'))
            elif k_von.get(b, {}).get('typ') != BAHN_TYP:
                fehler.append(('P-5', vid, f"'{b}' ist keine Materialbahn"))
            elif ok:
                bahn_kanten[b].append((v['von'], v['nach']))
        elif v['bahn']:
            warn.append(('P-5', vid, 'Spalte bahn bei Nicht-Bahnverbindung gesetzt (ignoriert)'))

    # P-3: maximale Verbindungen je Port
    for (kid, port), n in sorted(belegung.items()):
        mx = typen[k_von[kid]['typ']]['ports'][port].get('max')
        if mx is not None and n > mx:
            fehler.append(('P-3', kid, f'Port {port}: {n} Verbindungen, zulaessig {mx}'))

    # P-4: jede Bahn eine lueckenlose Kette
    for b in sorted((z['id'] for z in komps if z['typ'] == BAHN_TYP), key=natkey):
        kanten = bahn_kanten.get(b, [])
        if not kanten:
            fehler.append(('P-4', b, 'Materialbahn ohne Bahnverlauf'))
            continue
        aus = Counter(a for a, _ in kanten)
        ein = Counter(c for _, c in kanten)
        knoten = set(aus) | set(ein)
        verzweigt = sorted((n for n in knoten if aus[n] > 1 or ein[n] > 1), key=natkey)
        for n in verzweigt:
            fehler.append(('P-4', b, f'Verzweigung an {n}'))
        start = sorted((n for n in knoten if ein[n] == 0), key=natkey)
        ende = sorted((n for n in knoten if aus[n] == 0), key=natkey)
        if len(start) != 1 or len(ende) != 1:
            fehler.append(('P-4', b, f'genau ein Anfang und ein Ende noetig '
                                     f'(Anfang: {start}, Ende: {ende})'))
            continue
        if verzweigt:
            continue
        nachf = dict(kanten)
        weg, n = [start[0]], start[0]
        while n in nachf and len(weg) <= len(knoten):
            n = nachf[n]
            weg.append(n)
        if len(weg) != len(knoten):
            fehler.append(('P-4', b, 'Bahnverlauf nicht zusammenhaengend oder zyklisch'))

    # P-6 / P-7 / P-8
    for z in komps:
        t = typen.get(z['typ'])
        if t is None or z['typ'] in (BAHN_TYP, RAHMEN_TYP):
            continue
        if z['id'] not in verbunden:
            warn.append(('P-6', z['id'], 'Bauteil ohne Verbindung'))
        for pn, p in t['ports'].items():
            if p.get('pflicht') and belegung[(z['id'], pn)] == 0:
                warn.append(('P-7', z['id'], f'Pflicht-Port {pn} nicht verbunden'))
        if z['typ'] == 'antrieb':
            sig = [pn for pn, p in t['ports'].items() if p['art'] == 'signal']
            if not any(belegung[(z['id'], pn)] for pn in sig):
                hinweis.append(('P-8', z['id'], 'Antrieb ohne Signaleingang'))

    return fehler, warn, hinweis, bahn_kanten


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def baue_graph(komps, verbs, arten, mit_rahmen):
    inst = [{'instanz': z['id'], 'typ': z['typ'], 'bezeichnung': z['bezeichnung'],
             'pfad': z['materialpfad'], 'baugruppe': z['baugruppe'],
             'gestellfest': z['gestellfest']} for z in komps]
    kanten, gesehen = [], set()

    def neu(a, b, dom, gerichtet, quelle):
        if a == b:
            return
        key = (a, b, dom) if gerichtet else (frozenset((a, b)), dom)
        if key in gesehen:
            return
        gesehen.add(key)
        kanten.append({'from': a, 'to': b, 'domain': dom,
                       'gerichtet': '1' if gerichtet else '0', 'quelle': quelle})

    for v in verbs:
        art = arten[v['art']]
        if v['art'] == 'bahn':
            for k in (v['von'], v['nach']):
                neu(k, v['bahn'], art['domaene'], False, v['id'])
        else:
            neu(v['von'], v['nach'], art['domaene'], bool(art['gerichtet']), v['id'])

    if mit_rahmen:
        inst.append({'instanz': RAHMEN_ID, 'typ': RAHMEN_TYP,
                     'bezeichnung': 'Maschinenrahmen (implizit)', 'pfad': '',
                     'baugruppe': '', 'gestellfest': ''})
        for z in komps:
            if z['gestellfest'].lower() == 'ja':
                neu(RAHMEN_ID, z['id'], 'planar', False, 'rahmen')
    return inst, kanten


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------
def schreibe_csv(name, kopf, zeilen):
    EXPORT_DIR.mkdir(exist_ok=True)
    with open(EXPORT_DIR / name, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=kopf, delimiter=';')
        w.writeheader()
        w.writerows(zeilen)


def schreibe_pruefung(fehler, warn, hinweis):
    EXPORT_DIR.mkdir(exist_ok=True)
    with open(EXPORT_DIR / 'pruefung.txt', 'w', encoding='utf-8') as f:
        for titel, liste in (('FEHLER', fehler), ('WARNUNG', warn), ('HINWEIS', hinweis)):
            for code, obj, text in liste:
                f.write(f'{titel};{code};{obj};{text}\n')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    mit_rahmen = '--rahmen' in sys.argv
    if not args:
        sys.exit('Aufruf: python lese_anlage.py <ordner> [--rahmen]')
    ordner = pathlib.Path(args[0])

    version, arten, typen = lade_pool(finde_pool())
    komps = lies_csv(ordner / 'components.csv', KOMP_SPALTEN)
    verbs = lies_csv(ordner / 'connections.csv', VERB_SPALTEN)
    print(f"Gelesen: {ordner.name}  ({len(komps)} Bauteile, {len(verbs)} Verbindungen), "
          f"Bauteilpool v{version}")
    print(f"Rahmen : {'ja (--rahmen)' if mit_rahmen else 'nein'}\n")

    fehler, warn, hinweis, bahn_kanten = pruefe(komps, verbs, arten, typen, mit_rahmen)
    schreibe_pruefung(fehler, warn, hinweis)

    print("Bauteile je Typ:")
    for t, n in Counter(z['typ'] for z in komps).most_common():
        print(f"  {typen.get(t, {}).get('kurz', t):18s} {n:3d}")

    print("\nMaterialbahnen:")
    for b, k in sorted(bahn_kanten.items(), key=lambda x: natkey(x[0])):
        teile = {x for kante in k for x in kante}
        print(f"  {b:18s} {len(teile):3d} Bauteile im Lauf, {len(k):3d} Bahnsegmente")

    print("\nPruefung (Lastenheft Abschn. 5)")
    print(f"  Fehler    : {len(fehler):3d}   (sollte 0 sein)")
    print(f"  Warnungen : {len(warn):3d}")
    print(f"  Hinweise  : {len(hinweis):3d}")
    for titel, liste in (('FEHLER', fehler), ('WARNUNG', warn), ('HINWEIS', hinweis)):
        for code, obj, text in liste:
            print(f"    {titel:8s} {code}  {obj}: {text}")

    if fehler:
        sys.exit("\nAbbruch: Fehler beheben, keine Ausgabe geschrieben (Details: pruefung.txt)")

    inst, kanten = baue_graph(komps, verbs, arten, mit_rahmen)
    schreibe_csv('instances.csv',
                 ['instanz', 'typ', 'bezeichnung', 'pfad', 'baugruppe', 'gestellfest'], inst)
    schreibe_csv('edges.csv', ['from', 'to', 'domain', 'gerichtet', 'quelle'], kanten)

    print(f"\nGraph: {len(inst)} Knoten, {len(kanten)} Kanten")
    for d, n in Counter(k['domain'] for k in kanten).most_common():
        print(f"  {d:10s} {n:3d}")