"""parse_export.py — Amesim-Python-Export -> instances.csv, edges.csv

Aufruf : python parse_export.py [pfad_zum_export]
Getestet: EXINOS (Lehmann), Coil2Stack_Kompakt (Husseini)

Schritte:
  1. Instanzen, Verbindungen, Materialparameter einlesen
  2. Domaene je Verbindung: Leitungsname > Porttabelle > Fallback
  3. Platzhalter entfernen (IGNORE_TYPES), Amesim-Typ -> Bauteiltyp (TYPE_ALIAS)
  4. Ersatzmodelle zusammenfassen: Bahn, Rahmen, Riementrieb, Walze
  5. Inline-Sensoren ueberbruecken (rotary, planar, rope)
  6. Signalketten GERICHTET kontrahieren
  7. Materialpfad propagieren (nur Beschriftung)
"""
import re
import csv
import sys
import pathlib
from collections import defaultdict, Counter, deque

MERGE_WEB = True
MERGE_FRAME = True
MERGE_BELT = True
MERGE_ROLLER = True
BYPASS_INLINE = True
CONTRACT_SIGNALS = True

FRAME_TYPE = 'plmrefwall'
FRAME_NAME = 'Rahmen'
BELT_TYPES = {'plmsheave01', 'plmsheave0', 'plmrope'}
BELT_TYPE = 'riementrieb'
ROLLER_TYPE = 'plmroller_conv'
ROLLER_INTERNAL = {'rotaryload2ports', '1part_rot_friction_new', 'zerotorquesource'}

# Amesim-Typ -> Bauteiltyp (Portnummern identisch zum Zieltyp geprueft)
TYPE_ALIAS = {
    'conv_mech_ao_passive_roller':     'plmroller_idlewithinertia',
    'conv_mech_ao_passive_roller_w2d': 'plmroller_conv',            # Taenzerrolle
    'ctrl_ao_speedctrlleddrive_enc':   'plmctrl_speedcntrlleddrive',
    'plmforcesensor_conv':             'plmwebforcesensor',
    'plmpilotedtranslation':           'plmrecpilotedprismatic',
}
IGNORE_TYPES = {'plmzer00'}                # Platzhalter ohne physikalische Funktion
LINE_DOMAIN_ALIAS = {'linear': 'planar'}  # translatorische 1D-Mechanik

# Sensoren IN einer mechanischen Kette (Bauteiltyp -> Domaene)
INLINE = {
    'rotaryspeedsensor2': 'rotary', 'anglesensor2': 'rotary',
    'plmdisplacementsensor': 'planar', 'plmvelocitysensor': 'planar',
    'plmforcesensor': 'planar',
    'plmwebforcesensor': 'rope', 'plmradiussensor_conv': 'rope',
}

# ---------------------------------------------------------------------------
RE_COMP = re.compile(r"AMEAddComponent\('([^']+)',\s*'([^']+)',\s*\(")
RE_DYN = re.compile(r"AMEAddDynamicComponent\('([^']+)',\s*'([^']+)',")
RE_SC = re.compile(r"AMECreateSupercomponent\(\(\),\s*'([^']+)',\s*'([^']+)',")
RE_LINE = re.compile(
    r"AMEConnectTwoPortsWithLine\('([^']+)',\s*(\d+),\s*'([^']+)',\s*(\d+),\s*'([a-zA-Z]+)")
RE_PORT = re.compile(
    r"AMEConnectTwoPorts\('([^']+)',\s*(\d+),\s*'([^']+)',\s*(\d+)\)")
RE_SCP = re.compile(
    r"AMEConnectSupercomponentPort\('([^']+)',\s*(\d+),\s*'([^']+)',\s*(\d+)\)")
RE_MAT = re.compile(
    r"AMESetParameterValue\('M0@(plmweb_conv(?:_\d+)?)',\s*'([^']*)'")
RE_MTOKEN = re.compile(r"\b(M_\w+)")

MATERIAL_PFAD = {'M_CU': 'Anode', 'M_AL': 'Kathode', 'M_Seperator': 'Separator'}
PFAD_KURZ = {'Anode': 'An', 'Kathode': 'Ka', 'Separator': 'Se'}

DOMAINS = ('rope', 'rotary', 'planar', 'control')
DOMAIN_PRIORITY = ['rope', 'planar', 'rotary', 'control']
MECH = {'rope', 'rotary', 'planar'}
EXPORT_DIR = pathlib.Path(__file__).resolve().parent / 'Exports'

# Portdomaenen je AMESIM-Typ
_SENS3P = {0: 'planar', 1: 'control', 2: 'planar'}
PORT_DOMAIN = {
    'plmweb_conv':                {0: 'rope', 1: 'rope'},
    'plmroller_idlewithinertia':  {0: 'rope', 1: 'rope'},
    'plmroller_conv':             {0: 'planar', 1: 'rope', 2: 'rope', 3: 'rotary'},
    'plmwinder_conv_SENSED':      {0: 'planar', 1: 'rope', 2: 'rotary',
                                   3: 'control', 4: 'control', 5: 'control'},
    'plmwebforcesensor':          {0: 'rope', 1: 'control', 2: 'rope'},
    'plmsheave0':                 {0: 'planar', 1: 'rope', 2: 'rope', 3: 'rotary'},
    'plmsheave01':                {0: 'planar', 1: 'rope', 2: 'rope', 3: 'rotary'},
    'plmrope':                    {0: 'rope', 1: 'rope'},
    'plmrefwall':                 {0: 'planar'},
    'plmsource':                  {0: 'control', 1: 'control', 2: 'control', 3: 'planar'},
    'plmrecpilotedprismatic':     {0: 'planar', 1: 'planar', 2: 'planar'},
    'screw_nut':                  {0: 'rotary', 1: 'planar'},
    'torquecon':                  {0: 'control', 1: 'rotary'},
    'rotaryspeedsensor2':         {0: 'rotary', 1: 'control', 2: 'rotary'},
    'anglesensor2':               {0: 'rotary', 1: 'control', 2: 'rotary'},
    'rotaryload2ports':           {0: 'rotary', 1: 'rotary'},
    'zerotorquesource':           {0: 'rotary'},
    '1part_rot_friction_new':     {0: 'rotary', 1: 'control'},
    'plmctrl_speedcntrlleddrive': {p: 'control' for p in range(6)},
    'ROT_MOTION':                 {0: 'control', 1: 'control', 2: 'planar',
                                   3: 'control', 4: 'control'},
    'plmforcesensor':             _SENS3P,
    # Coil2Stack
    'conv_mech_ao_passive_roller':     {0: 'rope', 1: 'rope'},
    'conv_mech_ao_passive_roller_w2d': {0: 'planar', 1: 'rope', 2: 'rope'},
    'ctrl_ao_speedctrlleddrive_enc':   {p: 'control' for p in range(6)},
    'plmforcesensor_conv':             {0: 'rope', 1: 'control', 2: 'rope'},
    'plmradiussensor_conv':            {0: 'rope', 1: 'control', 2: 'rope'},
    'plmpilotedtranslation':           {0: 'planar', 1: 'planar', 2: 'planar'},
    'dynamic_plmbody':                 {p: 'planar' for p in range(6)},
    'forcecon':                        {0: 'control', 1: 'planar'},
    'plmdisplacementsensor':           _SENS3P,
    'plmvelocitysensor':               _SENS3P,
    'plmzer00':                        {0: 'planar'},
}

# Signalrichtung je Port (Amesim-Portkonvention)
_OUT_IN = {0: 'out', 1: 'in'}
_JUN = {0: 'in', 1: 'out', 2: 'in'}
_SPLIT = {0: 'out', 1: 'out', 2: 'in'}
SIGNAL_PORT_DIR = {
    'gain': _OUT_IN, 'pid': _OUT_IN, 'fofx': _OUT_IN, 'dynamic_x_table': _OUT_IN,
    'differentiator': _OUT_IN, 'firstorderlag': _OUT_IN, 'vsine': _OUT_IN,
    'subtraction': _JUN, 'sum': _JUN, 'multiplication': _JUN, 'division': _JUN,
    'fofxy': _JUN, 'comparison': _JUN,
    'splitter2p': _SPLIT, 'splitter2p2': _SPLIT, 'control04': _SPLIT,
    'switchdyn': {0: 'out', 1: 'in', 2: 'in', 3: 'in'},
    'modulo_SENSED': {0: 'in', 1: 'in', 2: 'out'},
    'constant': {0: 'out'}, 'dynamic_constant_source': {0: 'out'},
    'random': {0: 'out'},
    'signalsink': {0: 'in'},
}
_CTRL = {0: 'out', 1: 'in', 2: 'in', 3: 'in', 4: 'in', 5: 'in'}
PHYS_SIGNAL_DIR = {
    'plmctrl_speedcntrlleddrive': _CTRL,
    'ctrl_ao_speedctrlleddrive_enc': _CTRL,
    'torquecon':              {0: 'in'},
    'forcecon':               {0: 'in'},
    'rotaryspeedsensor2':     {1: 'out'},
    'anglesensor2':           {1: 'out'},
    'plmwebforcesensor':      {1: 'out'},
    'plmforcesensor_conv':    {1: 'out'},
    'plmradiussensor_conv':   {1: 'out'},
    'plmdisplacementsensor':  {1: 'out'},
    'plmvelocitysensor':      {1: 'out'},
    'plmforcesensor':         {1: 'out'},
    'plmwinder_conv_SENSED':  {3: 'out', 4: 'out', 5: 'out'},
    'plmsource':              {0: 'in', 1: 'in', 2: 'in'},
    'ROT_MOTION':             {0: 'out', 1: 'out', 3: 'in', 4: 'in'},
    '1part_rot_friction_new': {1: 'in'},
}

SIGNAL_TYPES = {
    'constant', 'gain', 'subtraction', 'sum', 'splitter2p', 'splitter2p2',
    'splitter3p', 'pid', 'multiplication', 'division', 'fofx', 'fofxy',
    'differentiator', 'integrator', 'integric', 'switchdyn', 'signal_switch',
    'comparison', 'logical', 'logical_not', 'signalsink', 'modulo_SENSED',
    'firstorderlag', 'vsine', 'stop', 'control04', 'dynamic_x_table',
    'dynamic_mux2', 'dynamic_dmux2', 'dynamic_duplicator2', 'dynamic_extractor',
    'dynamic_transmitter', 'dynamic_receiver', 'dynamic_expressions2',
    'dynamic_constant_source', 'random', 'runstats', 'plmassembly',
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def lies(pfad):
    for enc in ('utf-8', 'iso-8859-1'):
        try:
            with open(pfad, encoding=enc) as f:
                return f.readlines(), enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f'Kein passendes Encoding fuer {pfad}')


def hierarchie(name):
    return name.rsplit('.', 1)[0] if '.' in name else ''


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def ist_phys(inst, n):
    d = inst.get(n)
    return bool(d) and not d['parent'] and d['typ'] not in SIGNAL_TYPES


def ist_sig(inst, n):
    d = inst.get(n)
    return bool(d) and not d['parent'] and d['typ'] in SIGNAL_TYPES


def signal_dir(typ, port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    if typ in SIGNAL_PORT_DIR:
        return SIGNAL_PORT_DIR[typ].get(port)
    return PHYS_SIGNAL_DIR.get(typ, {}).get(port)


def kante(a, b, inst, dom, quelle, gerichtet='0'):
    return {'from': a, 'from_port': '', 'from_typ': inst[a]['typ'],
            'to': b, 'to_port': '', 'to_typ': inst[b]['typ'],
            'domain': dom, 'domain_quelle': quelle, 'art': quelle,
            'gerichtet': gerichtet}


def umbenennen(edges, ziel):
    """Kantenenden umhaengen, Selbstschleifen entfernen.
       from_typ/to_typ bleiben Amesim-Typen (Portrichtung)."""
    out = []
    for e in edges:
        e = dict(e)
        e['from'] = ziel.get(e['from'], e['from'])
        e['to'] = ziel.get(e['to'], e['to'])
        if e['from'] != e['to']:
            out.append(e)
    return out


def zusammenfassen(inst, edges, gruppen, typ_von):
    ziel = {m: name for name, mem in gruppen.items() for m in mem}
    neu = {n: d for n, d in inst.items() if n not in ziel}
    for name, mem in gruppen.items():
        neu[name] = {'typ': typ_von(name), 'amesim_typ': 'merged', 'kind': 'merged',
                     'parent': '', 'pfad': '',
                     'members': '|'.join(sorted(mem, key=natkey))}
    return neu, umbenennen(edges, ziel)


# ---------------------------------------------------------------------------
# Domaenenlogik
# ---------------------------------------------------------------------------
def port_domain(typ, port, unmapped):
    if typ in SIGNAL_TYPES:
        return 'control'
    tab = PORT_DOMAIN.get(typ)
    if tab is None or port not in tab:
        unmapped[(typ, port)] += 1
        return None
    return tab[port]


def bestimme_domaene(ta, pa, tb, pb, unmapped):
    da = port_domain(ta, pa, unmapped)
    db = port_domain(tb, pb, unmapped)
    if da and db:
        if da == db:
            return da, 'port', da, db
        return min((da, db), key=DOMAIN_PRIORITY.index), 'port_konflikt', da, db
    if da or db:
        return (da or db), 'port_einseitig', da, db
    return 'control', 'fallback', da, db


# ---------------------------------------------------------------------------
# Schritt 1+2
# ---------------------------------------------------------------------------
def parse(zeilen):
    inst, roh, material = {}, [], {}
    for raw in zeilen:
        ln = raw.strip()
        m = RE_COMP.match(ln)
        if m:
            inst[m.group(2)] = {'typ': m.group(1), 'kind': 'static'}
            continue
        m = RE_DYN.match(ln)
        if m:
            inst[m.group(2)] = {'typ': m.group(1), 'kind': 'dynamic'}
            continue
        m = RE_SC.match(ln)
        if m:
            inst[m.group(2)] = {'typ': m.group(1), 'kind': 'supercomponent'}
            continue
        m = RE_LINE.match(ln)
        if m:
            a, pa, b, pb, dom = m.groups()
            dom = LINE_DOMAIN_ALIAS.get(dom.lower(), dom.lower())
            roh.append((a, int(pa), b, int(pb),
                        dom if dom in DOMAINS else None, 'line'))
            continue
        m = RE_PORT.match(ln)
        if m:
            a, pa, b, pb = m.groups()
            roh.append((a, int(pa), b, int(pb), None, 'port'))
            continue
        m = RE_SCP.match(ln)
        if m:
            sc, ps, child, pc = m.groups()
            roh.append((sc, int(ps), child, int(pc), None, 'scport'))
            continue
        m = RE_MAT.match(ln)
        if m:
            material[m.group(1)] = m.group(2)

    for n, d in inst.items():
        d['parent'] = hierarchie(n)
        d['pfad'] = ''
        d['members'] = ''
        d['amesim_typ'] = d['typ']

    edges, unmapped, konflikte = [], Counter(), []
    for a, pa, b, pb, ldom, art in roh:
        ta = inst.get(a, {}).get('typ', '?')
        tb = inst.get(b, {}).get('typ', '?')
        pdom, pquelle, da, db = bestimme_domaene(ta, pa, tb, pb, unmapped)
        if ldom:
            dom, quelle = ldom, 'line'
            for t, p, d in ((ta, pa, da), (tb, pb, db)):
                if d and d != ldom and t not in SIGNAL_TYPES:
                    konflikte.append((a, ta, pa, b, tb, pb, ldom, d,
                                      'tabelle_vs_leitung'))
        else:
            dom, quelle = pdom, pquelle
            if pquelle == 'port_konflikt':
                konflikte.append((a, ta, pa, b, tb, pb, '', f'{da}/{db}',
                                  'port_vs_port'))
        edges.append({'from': a, 'from_port': pa, 'from_typ': ta,
                      'to': b, 'to_port': pb, 'to_typ': tb,
                      'domain': dom, 'domain_quelle': quelle, 'art': art,
                      'gerichtet': '0'})
    return inst, edges, material, unmapped, konflikte


# ---------------------------------------------------------------------------
# Schritt 3: Platzhalter entfernen, Bauteiltypen zuordnen
# ---------------------------------------------------------------------------
def entferne_platzhalter(inst, edges):
    weg = {n for n, d in inst.items() if d['typ'] in IGNORE_TYPES and not d['parent']}
    inst = {n: d for n, d in inst.items() if n not in weg}
    edges = [e for e in edges if e['from'] not in weg and e['to'] not in weg]
    return inst, edges, sorted(weg, key=natkey)


def bauteiltypen(inst):
    zaehler = Counter()
    for d in inst.values():
        if d['typ'] in TYPE_ALIAS and not d['parent']:
            zaehler[(d['typ'], TYPE_ALIAS[d['typ']])] += 1
            d['typ'] = TYPE_ALIAS[d['typ']]
    return zaehler


# ---------------------------------------------------------------------------
# Schritt 4: Ersatzmodelle
# ---------------------------------------------------------------------------
def merge_web(inst, edges, material):
    segs = [n for n, d in inst.items() if d['typ'] == 'plmweb_conv' and not d['parent']]
    ohne = sorted((n for n in segs if n not in material), key=natkey)
    unbekannt = sorted({material[n] for n in segs
                        if n in material and not RE_MTOKEN.search(material[n])})

    def name_pfad(val):
        m = RE_MTOKEN.search(val)
        if m:
            p = MATERIAL_PFAD.get(m.group(1), m.group(1))
            return f'Bahn_{p}', PFAD_KURZ.get(p, '')
        i = unbekannt.index(val)
        return ('Bahn' if len(unbekannt) == 1 else f'Bahn_{i + 1}'), ''

    gruppen, pfad_von = defaultdict(list), {}
    for n in segs:
        if n in material:
            b, p = name_pfad(material[n])
            gruppen[b].append(n)
            pfad_von[b] = p
    if not gruppen:
        return inst, edges, {}, ohne
    inst, edges = zusammenfassen(inst, edges, gruppen, lambda _: 'plmweb_conv')
    for b in gruppen:
        inst[b]['pfad'] = pfad_von[b]
    return inst, edges, gruppen, ohne


def merge_frame(inst, edges):
    anker = [n for n, d in inst.items() if d['typ'] == FRAME_TYPE and not d['parent']]
    if not anker:
        return inst, edges, []
    inst, edges = zusammenfassen(inst, edges, {FRAME_NAME: anker}, lambda _: FRAME_TYPE)
    return inst, edges, sorted(anker, key=natkey)


def merge_belt(inst, edges):
    def ist_belt(n):
        return ist_phys(inst, n) and inst[n]['typ'] in BELT_TYPES
    nb = defaultdict(set)
    for e in edges:
        a, b = e['from'], e['to']
        if ist_belt(a) and ist_belt(b):
            nb[a].add(b)
            nb[b].add(a)
    gruppen, besucht = {}, set()
    for s in sorted((n for n in inst if ist_belt(n)
                     and inst[n]['typ'] == 'plmsheave01'), key=natkey):
        if s in besucht:
            continue
        grp, q = {s}, deque([s])
        while q:
            x = q.popleft()
            for y in nb[x]:
                if y not in grp:
                    grp.add(y)
                    q.append(y)
        besucht |= grp
        gruppen[f"Riementrieb_{s}"] = sorted(grp, key=natkey)
    rest = sorted((n for n in inst if ist_belt(n) and n not in besucht), key=natkey)
    if not gruppen:
        return inst, edges, {}, rest
    inst, edges = zusammenfassen(inst, edges, gruppen, lambda _: BELT_TYPE)
    return inst, edges, gruppen, rest


def merge_roller(inst, edges):
    def ist_intern(n):
        return ist_phys(inst, n) and inst[n]['typ'] in ROLLER_INTERNAL
    nb = defaultdict(set)
    for e in edges:
        nb[e['from']].add(e['to'])
        nb[e['to']].add(e['from'])
    ziel, protokoll = {}, {}
    for r in sorted((n for n in inst if ist_phys(inst, n)
                     and inst[n]['typ'] == ROLLER_TYPE), key=natkey):
        grp, q = set(), deque([r])
        while q:
            x = q.popleft()
            for y in nb[x]:
                if ist_intern(y) and y not in grp and y not in ziel:
                    grp.add(y)
                    q.append(y)
        for m in grp:
            ziel[m] = r
        if grp:
            protokoll[r] = sorted(grp, key=natkey)
    rest = sorted((n for n in inst if ist_intern(n) and n not in ziel), key=natkey)
    if not ziel:
        return inst, edges, {}, rest
    neu = {n: d for n, d in inst.items() if n not in ziel}
    for r, mem in protokoll.items():
        neu[r] = dict(neu[r])
        neu[r]['kind'] = 'merged'
        neu[r]['members'] = '|'.join([r] + mem)
    return neu, umbenennen(edges, ziel), protokoll, rest


# ---------------------------------------------------------------------------
# Schritt 5: Inline-Sensoren ueberbruecken (je Domaene)
# ---------------------------------------------------------------------------
def bypass_inline(inst, edges):
    nb = defaultdict(lambda: defaultdict(set))
    for e in edges:
        nb[e['domain']][e['from']].add(e['to'])
        nb[e['domain']][e['to']].add(e['from'])

    vorhanden = {frozenset((e['from'], e['to'])) for e in edges}
    neu, protokoll, besucht = [], [], set()
    for s in sorted((n for n in inst if ist_phys(inst, n) and inst[n]['typ'] in INLINE),
                    key=natkey):
        if s in besucht:
            continue
        dom = INLINE[inst[s]['typ']]

        def ist_inl(n):
            return ist_phys(inst, n) and INLINE.get(inst[n]['typ']) == dom

        kette, enden, q = {s}, set(), deque([s])
        while q:
            x = q.popleft()
            for y in nb[dom][x]:
                if ist_inl(y):
                    if y not in kette:
                        kette.add(y)
                        q.append(y)
                elif ist_phys(inst, y):
                    enden.add(y)
        besucht |= kette
        enden = sorted(enden, key=natkey)
        for i, a in enumerate(enden):
            for b in enden[i + 1:]:
                if frozenset((a, b)) in vorhanden:
                    continue
                vorhanden.add(frozenset((a, b)))
                neu.append(kante(a, b, inst, dom, 'inline_bypass'))
                protokoll.append((a, inst[a]['typ'], b, inst[b]['typ'], dom,
                                  '|'.join(sorted(kette, key=natkey))))
    return edges + neu, protokoll


# ---------------------------------------------------------------------------
# Schritt 6: Signalketten gerichtet kontrahieren
# ---------------------------------------------------------------------------
def contract_signals(inst, edges):
    succ, fehler = defaultdict(set), []
    for e in edges:
        if e['art'] in ('scport', 'inline_bypass'):
            continue
        a, b = e['from'], e['to']
        if not (ist_sig(inst, a) or ist_sig(inst, b)):
            continue
        if not all(ist_sig(inst, x) or ist_phys(inst, x) for x in (a, b)):
            continue
        da = signal_dir(e['from_typ'], e['from_port'])
        db = signal_dir(e['to_typ'], e['to_port'])
        if da == 'out' and db == 'in':
            succ[a].add(b)
        elif da == 'in' and db == 'out':
            succ[b].add(a)
        else:
            fehler.append((a, e['from_typ'], e['from_port'], da,
                           b, e['to_typ'], e['to_port'], db))

    direkt = {frozenset((e['from'], e['to'])) for e in edges
              if ist_phys(inst, e['from']) and ist_phys(inst, e['to'])}
    neu, protokoll, gesehen = [], [], set()
    for p in sorted((n for n in inst if ist_phys(inst, n)), key=natkey):
        start = [s for s in succ[p] if ist_sig(inst, s)]
        if not start:
            continue
        dist = {s: 1 for s in start}
        q = deque(start)
        while q:
            s = q.popleft()
            for t in succ[s]:
                if ist_sig(inst, t):
                    if t not in dist:
                        dist[t] = dist[s] + 1
                        q.append(t)
                elif ist_phys(inst, t) and t != p:
                    if frozenset((p, t)) in direkt or (p, t) in gesehen:
                        continue
                    gesehen.add((p, t))
                    neu.append(kante(p, t, inst, 'control',
                                     'signal_kontrahiert', gerichtet='1'))
                    protokoll.append((p, inst[p]['typ'], t, inst[t]['typ'], dist[s]))
    return edges + neu, protokoll, fehler


# ---------------------------------------------------------------------------
# Schritt 7: Materialpfad (nur Beschriftung)
# ---------------------------------------------------------------------------
def pfade_zuordnen(inst, edges):
    pf = {n: ({d['pfad']} if d['pfad'] else set()) for n, d in inst.items()}
    nb = defaultdict(set)
    for e in edges:
        if e['domain'] in MECH:
            nb[e['from']].add(e['to'])
            nb[e['to']].add(e['from'])
    for _ in range(20):
        neu = {}
        for n in inst:
            if pf[n] or not ist_phys(inst, n) or n == FRAME_NAME:
                continue
            kand = set()
            for m in nb[n]:
                if m != FRAME_NAME:
                    kand |= pf.get(m, set())
            if len(kand) == 1:
                neu[n] = kand
        if not neu:
            break
        pf.update(neu)
    for n, d in inst.items():
        d['pfad'] = '+'.join(sorted(pf[n]))


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------
def schreibe_csv(name, kopf, zeilen):
    EXPORT_DIR.mkdir(exist_ok=True)
    with open(EXPORT_DIR / name, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(kopf)
        w.writerows(zeilen)


def schreibe(inst, edges, bypass, protokoll, fehler, unmapped, konflikte):
    EXPORT_DIR.mkdir(exist_ok=True)
    schreibe_csv('instances.csv',
                 ['instanz', 'typ', 'amesim_typ', 'kind', 'parent', 'pfad', 'members'],
                 ([n, inst[n]['typ'], inst[n].get('amesim_typ', ''), inst[n]['kind'],
                   inst[n]['parent'], inst[n]['pfad'], inst[n]['members']]
                  for n in sorted(inst, key=natkey)))
    felder = ['from', 'from_port', 'from_typ', 'to', 'to_port', 'to_typ',
              'domain', 'domain_quelle', 'art', 'gerichtet']
    with open(EXPORT_DIR / 'edges.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=felder, delimiter=';')
        w.writeheader()
        w.writerows(edges)
    schreibe_csv('inline_bypass.csv',
                 ['a', 'a_typ', 'b', 'b_typ', 'domain', 'ueberbrueckt'], bypass)
    schreibe_csv('signal_paths.csv',
                 ['from', 'from_typ', 'to', 'to_typ', 'signalbloecke_dazwischen'],
                 sorted(protokoll, key=lambda r: (natkey(r[0]), r[4])))
    schreibe_csv('signal_dir_errors.csv',
                 ['a', 'a_typ', 'a_port', 'a_dir', 'b', 'b_typ', 'b_port', 'b_dir'], fehler)
    schreibe_csv('ports_unmapped.csv', ['typ', 'port', 'vorkommen'],
                 ([t, p, n] for (t, p), n in unmapped.most_common()))
    schreibe_csv('domain_conflicts.csv',
                 ['from', 'from_typ', 'from_port', 'to', 'to_typ', 'to_port',
                  'leitung', 'tabelle', 'art'], konflikte)


def bericht(inst_roh, inst, edges, merge, alias, ignoriert, bypass, protokoll,
            fehler, unmapped, konflikte):
    kinds = Counter(d['kind'] for d in inst_roh.values())
    print(f"Instanzen (roh) : {len(inst_roh)}  "
          f"(static {kinds['static']}, dynamic {kinds['dynamic']}, "
          f"supercomponent {kinds['supercomponent']})")
    if ignoriert:
        print(f"Platzhalter entfernt: {len(ignoriert)} ({'|'.join(ignoriert)})")
    if alias:
        print("\nAmesim-Typ -> Bauteiltyp:")
        for (a, b), n in sorted(alias.items()):
            print(f"  {a:34s} -> {b:28s} {n}x")

    print("\nErsatzmodelle zusammengefasst:")
    for b, mem in sorted(merge['web'].items()):
        print(f"  {b:28s}: {len(mem):2d} Segmente")
    if merge['web_ohne']:
        print(f"  WARNUNG Segmente ohne Material: {merge['web_ohne'][:5]}")
    if merge['frame']:
        print(f"  {FRAME_NAME:28s}: {len(merge['frame']):2d} Anker")
    print(f"  Riementriebe                : {len(merge['belt']):2d}")
    for b, mem in sorted(merge['belt'].items(), key=lambda x: natkey(x[0])):
        print(f"     {b:32s} {len(mem)} Elemente: {'|'.join(mem)}")
    if merge['belt_rest']:
        print(f"  WARNUNG Riemenelemente ohne Scheibe: {merge['belt_rest']}")
    print(f"  Walzen mit Innenleben       : {len(merge['roller']):2d}")
    for r, mem in merge['roller'].items():
        print(f"     {r:32s} + {'|'.join(mem)}")
    if merge['roller_rest']:
        print(f"  WARNUNG Lager-/Reibelemente ohne Walze: {merge['roller_rest']}")

    print(f"\nKanten          : {len(edges)}")
    for art, n in Counter(e['art'] for e in edges).most_common():
        print(f"  {art:18s}: {n:4d}")

    tv = sum(1 for k in konflikte if k[-1] == 'tabelle_vs_leitung')
    print("\nPruefwerte")
    print(f"  Tabelle widerspricht Leitungsname : {tv:3d}   (sollte 0 sein)")
    print(f"  Signalkanten ohne Richtung        : {len(fehler):3d}   (sollte 0 sein)")
    print(f"  Ports ohne Tabelleneintrag        : {len(unmapped):3d}   (sollte 0 sein)")
    for (t, p), n in unmapped.most_common(10):
        print(f"     {t} Port {p}: {n}x")
    for f_ in fehler[:10]:
        print(f"     {f_[1]}[{f_[2]}]={f_[3]}  <->  {f_[5]}[{f_[6]}]={f_[7]}")
    bp = Counter(r[4] for r in bypass)
    print(f"  Inline-Bypass                     : {len(bypass):3d}   "
          f"(rotary {bp['rotary']}, planar {bp['planar']}, rope {bp['rope']})")

    if bypass:
        print("\nInline-Bypass:")
        for a, _, b, _, dom, k in bypass:
            print(f"  {a:28s} <-> {b:28s} [{dom}] ueber {k}")
    if protokoll:
        print(f"\nKontrahierte Signalpfade (gerichtet): {len(protokoll)}")
        for r in sorted(protokoll, key=lambda r: natkey(r[0])):
            print(f"  {r[0]:32s} -> {r[2]:34s} ({r[4]} Bloecke)")

    phys = [n for n in inst if ist_phys(inst, n)]
    print(f"\nPhysische Knoten: {len(phys)}, davon ohne Pfad: "
          f"{sum(1 for n in phys if not inst[n]['pfad'])}")


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    pfad = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'AMESIM_CODE_EXINOS.txt')
    if not pfad.exists():
        sys.exit(f'Datei nicht gefunden: {pfad.resolve()}')
    zeilen, enc = lies(pfad)
    print(f"Gelesen: {pfad.name} ({len(zeilen)} Zeilen, {enc})\n")

    inst, edges, material, unmapped, konflikte = parse(zeilen)
    inst_roh = {n: dict(d) for n, d in inst.items()}
    inst, edges, ignoriert = entferne_platzhalter(inst, edges)
    alias = bauteiltypen(inst)

    merge = {'web': {}, 'web_ohne': [], 'frame': [], 'belt': {}, 'belt_rest': [],
             'roller': {}, 'roller_rest': []}
    if MERGE_WEB:
        inst, edges, merge['web'], merge['web_ohne'] = merge_web(inst, edges, material)
    if MERGE_FRAME:
        inst, edges, merge['frame'] = merge_frame(inst, edges)
    if MERGE_BELT:
        inst, edges, merge['belt'], merge['belt_rest'] = merge_belt(inst, edges)
    if MERGE_ROLLER:
        inst, edges, merge['roller'], merge['roller_rest'] = merge_roller(inst, edges)

    bypass = []
    if BYPASS_INLINE:
        edges, bypass = bypass_inline(inst, edges)
    protokoll, fehler = [], []
    if CONTRACT_SIGNALS:
        edges, protokoll, fehler = contract_signals(inst, edges)

    pfade_zuordnen(inst, edges)
    schreibe(inst, edges, bypass, protokoll, fehler, unmapped, konflikte)
    bericht(inst_roh, inst, edges, merge, alias, ignoriert, bypass, protokoll,
            fehler, unmapped, konflikte)