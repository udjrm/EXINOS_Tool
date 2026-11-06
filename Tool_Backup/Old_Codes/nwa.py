"""nwa.py — Nutzwertanalyse auf Klassenebene

Aufruf : python nwa.py          (Einstellungen: Konstanten unten)
Liest  : <Lauf>/classes.csv, <Lauf>/dsm_matrix.csv       (aus build_dsm.py)
         nwa_kriterien.csv, nwa_regeln.csv, nwa_bewertung.csv (optional)
Gibt   : <Lauf>/nwa_klassen.csv  B, NW, B_ges je Klasse und Zielgroesse
         <Lauf>/nwa_log.txt

Rechnung (Husseini 2025, Gl. 5-1, hier auf Klassenebene):
  G_i     = RPZ_i / Summe RPZ der Zielgroesse   (oder Spalte 'gewicht')
  NW_K    = Summe_i B_K,i * G_i                 nur aktive Kriterien
  B_ges,K = AS_K * NW_K                         AS aus dsm_matrix.csv; n geht nicht ein (A1)

Zielgroesse aktiv : die Anlage enthaelt einen ihrer 'zielpfade'
Kriterium aktiv   : Zielgroesse aktiv, Spalte aktiv != nein, Traegertyp in der Anlage
Vorschlag         : spezifischste Regel aus nwa_regeln.csv (typ 4, funktion 2, pfad 1 Punkt);
                    bei mehreren Pfaden einer Klasse das Maximum je Kriterium
Bewertung         : nwa_bewertung.csv, Schluessel klasse_id, leere Zelle = Vorschlag;
                    Abweichung ohne Begruendung -> Warnung

nwa_klassen.csv ist zugleich die Vorlage fuer nwa_bewertung.csv: Datei kopieren,
Werte in den Kriteriumsspalten aendern, Grund in 'begruendung' eintragen. Die
Spalten NW, B_ges, nutzerwerte und instanzen werden beim Einlesen ignoriert.
In den Kriteriumsspalten steht der angewandte Wert (Vorschlag oder Nutzerwert);
wie viele davon vom Vorschlag abweichen, zeigt 'nutzerwerte' und das Log.

Zahlen: Ausgabe mit Dezimalpunkt; beim Einlesen wird ein Komma als Punkt gelesen.
"""

import re
import csv
import sys
import pathlib
from collections import defaultdict, Counter

# --- Einstellungen ----------------------------------------------------------
LAUFORDNER  = None                  # None: juengster Ordner in Exports/ mit dsm_matrix.csv
ZIELE       = None                  # None: automatisch ueber Materialpfade, sonst z. B. ['stapeln']
RENORMIEREN = False                 # True: aktive Gewichte je Zielgroesse auf Summe 1
KRITERIEN   = 'nwa_kriterien.csv'
REGELN      = 'nwa_regeln.csv'
BEWERTUNG   = 'nwa_bewertung.csv'
# -----------------------------------------------------------------------------

EXPORT_DIR = pathlib.Path(__file__).resolve().parent / 'Exports'
SKALA, EPS = (0, 1, 3), 1e-9
INFO = ['klasse_id', 'label', 'typ', 'funktion', 'pfad', 'n', 'AS']
LOG, WARN = [], []


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def log(t=''):
    print(t)
    LOG.append(t)


def warn(t):
    WARN.append(t)
    log(f'  WARNUNG  {t}')


def zahl(t, feld):
    """Dezimalzahl; Komma wird als Punkt gelesen."""
    try:
        return float(str(t).strip().replace(',', '.'))
    except ValueError:
        sys.exit(f'{feld}: "{t}" ist keine Zahl')


def ganz(t, feld):
    try:
        return int(str(t).strip())
    except ValueError:
        sys.exit(f'{feld}: "{t}" ist keine ganze Zahl')


def skala(t, feld):
    w = ganz(t, feld)
    if w not in SKALA:
        sys.exit(f'{feld}: Wert {w} nicht in der Skala 0/1/3')
    return w


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def teilpfade(t):
    """'An+Ka' -> ['An', 'Ka']; gleiche Trennung wie in refine_wl.py."""
    return [p.strip() for p in (t or '').split('+') if p.strip()]


def menge(t):
    """'*' oder leer -> None (beliebig), sonst Menge der Alternativen 'a|b'."""
    t = (t or '').strip()
    return None if t in ('', '*') else frozenset(x.strip() for x in t.split('|') if x.strip())


def passt(m, w):
    return m is None or w in m


def lies_csv(pfad, pflicht=()):
    """Semikolon-CSV; Zeilen mit '#' am Anfang sind Kommentare."""
    pfad = pathlib.Path(pfad)
    if not pfad.exists():
        sys.exit(f'Datei nicht gefunden: {pfad}')
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        zeilen = [z for z in f if z.strip() and not z.lstrip().startswith('#')]
    r = csv.DictReader(zeilen, delimiter=';')
    kopf = [(k or '').strip() for k in r.fieldnames or []]
    fehlt = [s for s in pflicht if s not in kopf]
    if fehlt:
        sys.exit(f'{pfad.name}: Spalten fehlen: {", ".join(fehlt)}')
    return kopf, [{(k or '').strip(): (v or '').strip() for k, v in z.items() if k} for z in r]


def finde_lauf():
    if LAUFORDNER:
        p = pathlib.Path(LAUFORDNER)
        return p if p.exists() else EXPORT_DIR / LAUFORDNER
    laeufe = sorted(d for d in EXPORT_DIR.glob('*') if (d / 'dsm_matrix.csv').exists())
    if not laeufe:
        sys.exit('Kein Laufordner mit dsm_matrix.csv in Exports/ - zuerst build_dsm.py')
    return laeufe[-1]


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lade_as(pfad):
    """Aktivsumme je klasse_id aus der letzten Spalte von dsm_matrix.csv."""
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        r = csv.reader(f, delimiter=';')
        if next(r, [''])[-1].strip() != 'AS':
            sys.exit('dsm_matrix.csv: letzte Spalte AS fehlt')
        return {z[0].strip(): ganz(z[-1], f'AS {z[0]}') for z in r
                if z and z[0].strip() not in ('', 'PS')}


def lade_kriterien():
    """Kriterien je Zielgroesse mit Gewicht G (aus 'gewicht' oder RPZ-Anteil)."""
    _, zeilen = lies_csv(KRITERIEN, ('zielgroesse', 'kriterium_id', 'rpz', 'gewicht',
                                     'traeger_typen', 'zielpfade'))
    doppelt = [k for k, n in Counter(z['kriterium_id'] for z in zeilen).items() if n > 1]
    if doppelt:
        sys.exit(f'{KRITERIEN}: kriterium_id mehrfach: {", ".join(doppelt)}')
    je_ziel = defaultdict(list)
    for z in zeilen:
        kid = z['kriterium_id']
        je_ziel[z['zielgroesse']].append({
            'id': kid,
            'rpz': zahl(z['rpz'], f'{kid}.rpz') if z['rpz'] else None,
            'gewicht': zahl(z['gewicht'], f'{kid}.gewicht') if z['gewicht'] else None,
            'traeger': menge(z['traeger_typen']), 'zielpfade': menge(z['zielpfade']),
            'schalter': (z.get('aktiv') or 'ja').lower() not in ('nein', '0', 'false')})
    for ziel, ks in je_ziel.items():
        if all(k['gewicht'] is not None for k in ks):
            for k in ks:
                k['G'], k['quelle'] = k['gewicht'], 'gewicht'
        elif any(k['gewicht'] is not None for k in ks):
            sys.exit(f'{ziel}: gewicht bei allen Kriterien oder bei keinem setzen')
        elif all(k['rpz'] for k in ks):
            summe = sum(k['rpz'] for k in ks)
            for k in ks:
                k['G'], k['quelle'] = k['rpz'] / summe, 'rpz'
        else:
            sys.exit(f'{ziel}: weder gewicht noch rpz vollstaendig angegeben')
    return je_ziel


def lade_regeln(krit_ids):
    kopf, zeilen = lies_csv(REGELN, ('typ', 'pfad', 'funktion'))
    for k in krit_ids:
        if k not in kopf:
            warn(f'{REGELN}: keine Spalte {k} - Vorschlag dort 0')
    regeln, gesehen = [], set()
    for z in zeilen:
        s = '/'.join(z[x] or '*' for x in ('typ', 'pfad', 'funktion'))
        if s in gesehen:
            sys.exit(f'{REGELN}: Regel {s} mehrfach')
        gesehen.add(s)
        t, p, f = menge(z['typ']), menge(z['pfad']), menge(z['funktion'])
        regeln.append({
            's': s, 'typ': t, 'pfad': p, 'funk': f, 'herkunft': z.get('herkunft') or '-',
            'punkte': 4 * (t is not None) + 2 * (f is not None) + (p is not None),
            'werte': {k: skala(z[k], f'Regel {s}/{k}') if z.get(k) else 0 for k in krit_ids}})
    return regeln


def lade_bewertung(krit_ids):
    """Bestaetigte Werte je klasse_id. Spalten ausserhalb der Kriterien und
    'begruendung' werden ignoriert, damit nwa_klassen.csv direkt als
    Bewertung kopiert werden kann."""
    if not pathlib.Path(BEWERTUNG).exists():
        return {}
    _, zeilen = lies_csv(BEWERTUNG, ('klasse_id',))
    doppelt = [k for k, n in Counter(z['klasse_id'] for z in zeilen).items() if k and n > 1]
    if doppelt:
        sys.exit(f'{BEWERTUNG}: klasse_id mehrfach: {", ".join(doppelt)}')
    return {z['klasse_id']: {'werte': {k: skala(z[k], f'{BEWERTUNG} {z["klasse_id"]}/{k}')
                                       for k in krit_ids if z.get(k)},
                             'begruendung': z.get('begruendung', '')}
            for z in zeilen if z['klasse_id']}


# ---------------------------------------------------------------------------
# Zielgroessen, Kriterien, Vorschlag
# ---------------------------------------------------------------------------

def aktive_kriterien(je_ziel, klassen):
    """Aktive Zielgroessen und je Zielgroesse die aktiven Kriterien mit Geff."""
    pfade = {p for k in klassen for p in teilpfade(k['pfad'])}
    typen = {k['typ'] for k in klassen}
    if ZIELE:
        fremd = [z for z in ZIELE if z not in je_ziel]
        if fremd:
            sys.exit(f'Zielgroesse nicht in {KRITERIEN}: {", ".join(fremd)}')
        ziele = list(ZIELE)
    else:
        ziele = [z for z, ks in je_ziel.items()
                 if any(k['zielpfade'] is None or k['zielpfade'] & pfade for k in ks)]
    if not ziele:
        sys.exit('Keine Zielgroesse aktiv (Pfade der Anlage: '
                 + (', '.join(sorted(pfade)) or 'keine') + ')')

    aktive = {}
    log('\nZielgroessen und Kriterien')
    for z, ks in je_ziel.items():
        log(f'  {z:14s} {"aktiv" if z in ziele else "inaktiv (kein passender Materialpfad)"}')
        if z not in ziele:
            continue
        aktive[z] = []
        for k in ks:
            if not k['schalter']:
                grund = 'aktiv = nein'
            elif k['traeger'] and not k['traeger'] & typen:
                grund = 'kein Traeger (' + '|'.join(sorted(k['traeger'])) + ')'
            else:
                grund = ''
                aktive[z].append(k)
            log(f'    {k["id"]:10s} G = {k["G"]:.4f} ({k["quelle"]:7s}) '
                f'{"nein" if grund else "ja  "}  {grund}')
        summe = sum(k['G'] for k in aktive[z])
        if summe <= EPS:
            sys.exit(f'{z}: kein aktives Kriterium')
        for k in aktive[z]:
            k['Geff'] = k['G'] / summe if RENORMIEREN else k['G']
        log(f'    Summe aktiv {summe:.4f}'
            + (' -> renormiert auf 1' if RENORMIEREN else ' (nicht renormiert)'))
    return aktive


def vorschlag(k, regeln, krit_ids):
    """Je Pfad die spezifischste Regel, ueber die Pfade das Maximum je Kriterium."""
    werte, genutzt = dict.fromkeys(krit_ids, 0), []
    for p in teilpfade(k['pfad']) or ['']:
        treffer = [r for r in regeln if passt(r['typ'], k['typ']) and passt(r['pfad'], p)
                   and passt(r['funk'], k['funktion'])]
        if not treffer:
            warn(f'{k["id"]}: keine Regel (Typ {k["typ"]}, Pfad {p or "-"}, '
                 f'Funktion {k["funktion"] or "-"}) -> B = 0')
            continue
        best = max(r['punkte'] for r in treffer)
        top = [r for r in treffer if r['punkte'] == best]
        if len(top) > 1:
            sys.exit(f'{k["id"]}: mehrere gleich spezifische Regeln: '
                     + ', '.join(r['s'] for r in top))
        if top[0] not in genutzt:
            genutzt.append(top[0])
        for kid in krit_ids:
            werte[kid] = max(werte[kid], top[0]['werte'][kid])
    return werte, genutzt


# ---------------------------------------------------------------------------

def main():
    lauf = finde_lauf()
    _, zeilen = lies_csv(lauf / 'classes.csv',
                         ('klasse_id', 'label', 'typ', 'funktion', 'pfad', 'instanzen'))
    klassen = [dict(z, id=z['klasse_id'],
                    mitglieder=sorted(filter(None, z['instanzen'].split('|')), key=natkey))
               for z in zeilen]
    as_von = lade_as(lauf / 'dsm_matrix.csv')
    fehlt = [k['id'] for k in klassen if k['id'] not in as_von]
    if fehlt:
        sys.exit('In dsm_matrix.csv fehlen: ' + ', '.join(fehlt))
    log(f'Laufordner : {lauf.name}')
    log(f'Klassen    : {len(klassen)},  Bauteile: {sum(len(k["mitglieder"]) for k in klassen)},'
        f'  Summe AS: {sum(as_von[k["id"]] for k in klassen)}')

    je_ziel = lade_kriterien()
    krit_ids = [k['id'] for ks in je_ziel.values() for k in ks]
    regeln = lade_regeln(krit_ids)
    aktive = aktive_kriterien(je_ziel, klassen)
    ziele = list(aktive)
    aktiv_ids = [k['id'] for z in ziele for k in aktive[z]]

    bew = lade_bewertung(krit_ids)
    log('\nBewertung  : ' + (f'{BEWERTUNG} ({len(bew)} Klassen)' if bew
                             else 'keine -> Vorschlag gilt unveraendert'))
    fremd = set(bew) - {k['id'] for k in klassen}
    if fremd:
        warn(f'{len(fremd)} klasse_id in {BEWERTUNG} gehoeren nicht zu dieser Anlage (ignoriert)')

    aus, herkunft, abw_ges = [], Counter(), 0
    for k in klassen:
        v, genutzt = vorschlag(k, regeln, krit_ids)
        herkunft.update(r['herkunft'] for r in genutzt)
        e = bew.get(k['id'], {'werte': {}, 'begruendung': ''})
        b = {kid: e['werte'].get(kid, v[kid]) for kid in aktiv_ids}
        abw = [kid for kid in aktiv_ids if b[kid] != v[kid]]
        if abw and not e['begruendung']:
            warn(f'{k["id"]}: Abweichung vom Vorschlag ohne Begruendung ({", ".join(abw)})')
        abw_ges += len(abw)

        k['nw'] = {z: sum(b[kr['id']] * kr['Geff'] for kr in aktive[z]) for z in ziele}
        aus.append([k['id'], k['label'], k['typ'], k['funktion'], k['pfad'],
                    len(k['mitglieder']), as_von[k['id']],
                    ' | '.join(r['s'] for r in genutzt) or '-',
                    '+'.join(sorted({r['herkunft'] for r in genutzt})) or '-']
                   + [b[kid] for kid in aktiv_ids] + [e['begruendung']]
                   + [f'{x:.6f}' for z in ziele
                      for x in (k['nw'][z], as_von[k['id']] * k['nw'][z])]
                   + [len(abw), '|'.join(k['mitglieder'])])
    log(f'  vom Vorschlag abweichend: {abw_ges} Werte')
    log('  Herkunft der Regeln: ' + ', '.join(f'{h} {n}' for h, n in herkunft.most_common()))

    kopf = (INFO + ['regel', 'herkunft'] + aktiv_ids + ['begruendung']
            + [f'{x}_{z}' for z in ziele for x in ('NW', 'B_ges')]
            + ['nutzerwerte', 'instanzen'])
    with open(lauf / 'nwa_klassen.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(kopf)
        w.writerows(aus)

    log('\nErgebnis je Zielgroesse')
    for z in ziele:
        bges = {k['id']: as_von[k['id']] * k['nw'][z] for k in klassen}
        log(f'  {z}: B_max = {max(bges.values()):.2f},  '
            f'Klassen mit B_ges = 0: {sum(1 for w in bges.values() if w <= EPS)}')
        log(f'    {"Klasse":40s} {"n":>2s} {"AS":>3s} {"NW":>7s} {"B_ges":>7s}')
        for k in sorted(klassen, key=lambda k: (-bges[k['id']], k['id']))[:10]:
            log(f'    {k["id"]:40s} {len(k["mitglieder"]):2d} {as_von[k["id"]]:3d} '
                f'{k["nw"][z]:7.4f} {bges[k["id"]]:7.2f}')

    log(f'\n{len(WARN)} Warnungen.  Ausgabe: nwa_klassen.csv, nwa_log.txt')
    log('Bewertung aendern: nwa_klassen.csv als nwa_bewertung.csv kopieren, Werte und')
    log('begruendung anpassen, nwa.py erneut ausfuehren.  Danach: python abc.py')
    (lauf / 'nwa_log.txt').write_text('\n'.join(LOG) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()