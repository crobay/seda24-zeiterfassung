#!/usr/bin/env python3
"""
Zeiterfassungs-Export fuer die Buchhaltung (Deckungsbeitrag je Objekt), DB nur lesend.

  export_zeiterfassung.py                    Vormonat: zeiterfassung_JJJJ-MM.csv + objekte_kunden.csv + qualitaet.csv
  export_zeiterfassung.py --monat 2026-10    bestimmter Monat
  export_zeiterfassung.py --alle --bis 2026-10-31
                                             alle Monate ab dem ersten Eintrag bis zum Stichtag

  export_zeiterfassung.py --exporttag       wie ohne Option, aber nur am Exporttag (sonst still beenden)

Cron: taeglich um 14:00 mit --exporttag -> Export des Vormonats am 1. Werktag des Folgemonats
(Mo-Fr ohne Feiertage BW, app/services/export_termine.py). Abruf von Drazens PC ueber /api/v1/export/zeiterfassung
(Endpunkt app/api/v1/endpoints/export.py, Windows-Skript frontend/public/downloads/seda24_export_abruf.ps1).

Eine Zeile je Einsatz; Semikolon, Dezimalkomma, UTF-8 (mit BOM fuer Excel), Datum JJJJ-MM-TT, keine Summen.
Keine Loehne/Stundensaetze/KM. Urlaub, Krank, unbezahlte Abwesenheit werden NICHT exportiert (nur gezaehlt).
Test-/Admin-Konten (is_test, T9999, TEST01, A0001) und Test-Objekte fehlen.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BACKEND, '.env'))
sys.path.insert(0, BACKEND)
from app.services.export_termine import exporttag, vormonat  # noqa: E402
OUT_DEFAULT = os.path.join(BACKEND, 'exports', 'zeiterfassung')
EXCL_PNR = ('T9999', 'TEST01', 'A0001')          # Test-/Admin-Konten
OBJ_URLAUB, OBJ_KRANK = 999, 19                  # Hilfsobjekte, kein Einsatzort
AUTO = {'Stempelung App', 'Auto-Booking Kat. A', 'Bestaetigung Kat. B'}
HDR = ['Datum', 'Pers.Nr', 'Name', 'Kunden-ID', 'Kunde', 'Objekt-ID', 'Objekt', 'Beginn', 'Ende', 'Pause_Min',
       'Netto_Std', 'Einsatzart', 'Buchungsweg', 'Eintrag-ID', 'Hinweis']


def num(x, d=2):
    return '' if x is None else f"{x:.{d}f}".replace('.', ',')


def work_date(ci, co):
    # Gehen an frueherem Tag als Kommen: Kommen-Datum in der DB verschoben, echtes Datum = Gehen-Datum
    if co is not None and co < ci and co.date() != ci.date():
        return co.date(), True
    return ci.date(), False


def absence(obj, st, notes):
    if obj == OBJ_URLAUB or st == 'Urlaub' or notes.startswith(('Urlaubstag', 'Unbezahlter Urlaub')):
        return 'Urlaub'
    if obj == OBJ_KRANK or st == 'Krank' or notes.startswith('Krank'):
        return 'Krank'
    if st == 'Abwesenheit':
        return 'Abwesenheit'
    return ''


def booking_path(manual, client_id, notes):
    if notes.startswith(('Auto-Booking Kategorie A', 'Automatische Buchung Kategorie A')):
        return 'Auto-Booking Kat. A'
    if notes.startswith(('Push-Bestaetigung Kategorie B', 'War anwesend (Kategorie B)')):
        return 'Bestaetigung Kat. B'
    if notes.startswith('Selbstbuchung genehmigt'):
        return 'Selbstbuchung genehmigt'
    if manual is False or client_id:
        return 'Stempelung App'
    if manual is None and not notes:
        return 'Altdaten (Import)'
    return 'Manuell (Admin)'


def write_csv(path, header, rows):
    """Atomar schreiben (tmp + rename), damit nie eine halbe Datei abgerufen wird."""
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.writer(f, delimiter=';')
        wr.writerow(header)
        wr.writerows(rows)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load(conn, bis):
    rows = conn.execute(text("""
        SELECT t.id, t.check_in, t.check_out, t.billed_hours, t.service_type, t.is_manual_entry, t.client_id,
               coalesce(t.notes, '') AS notes, e.id AS emp_id, e.personal_nr, e.first_name, e.last_name,
               t.object_id, o.name AS obj_name, o.customer_id, c.name AS cust_name, t.custom_object_name,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)), 0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS break_sec
        FROM time_entries t
        JOIN employees e ON e.id = t.employee_id
        LEFT JOIN objects o ON o.id = t.object_id
        LEFT JOIN customers c ON c.id = o.customer_id
        WHERE NOT coalesce(e.is_test, false) AND e.personal_nr NOT IN :excl AND NOT coalesce(o.is_test, false)
          AND least(t.check_in, coalesce(t.check_out, t.check_in))::date <= :bis
        ORDER BY t.check_in, e.personal_nr, t.id"""), {"excl": EXCL_PNR, "bis": bis}).fetchall()
    sched = conn.execute(text("""
        SELECT DISTINCT s.employee_id, s.date FROM schedules s JOIN employees e ON e.id = s.employee_id
        WHERE s.status IN ('normal', 'vertretung') AND s.date <= :bis AND coalesce(s.object_id, 0) NOT IN (:u, :k)
          AND NOT coalesce(e.is_test, false) AND e.personal_nr NOT IN :excl"""),
        {"bis": bis, "u": OBJ_URLAUB, "k": OBJ_KRANK, "excl": EXCL_PNR}).fetchall()
    return rows, {(s[0], s[1]) for s in sched}


def build(rows, sched_days, bis):
    by_month = defaultdict(list)
    q = defaultdict(lambda: defaultdict(int))
    ma_booked = defaultdict(set)
    booked_days = set()
    for r in rows:
        d, moved = work_date(r.check_in, r.check_out)
        if d > bis:
            continue
        m = d.strftime('%Y-%m')
        a = absence(r.object_id, r.service_type or '', r.notes)
        if a:
            q[m]['abw_' + a] += 1
            continue
        brutto_h = None
        if r.check_out:
            ci = datetime.combine(d, r.check_in.time()) if moved else r.check_in
            brutto_h = (r.check_out - ci).total_seconds() / 3600
            if brutto_h < 0:
                brutto_h = None
        netto = r.billed_hours if r.billed_hours is not None else (
            brutto_h - float(r.break_sec) / 3600 if brutto_h is not None else None)
        pause = max(0, round((brutto_h - netto) * 60)) if brutto_h is not None and netto is not None else None
        hint = []
        if moved:
            hint.append(f'Datum aus Gehen; Kommen-Datum in DB {r.check_in.date().isoformat()}')
        elif r.check_out is not None and r.check_out < r.check_in:
            hint.append('Gehen vor Kommen, Uhrzeiten unplausibel')
        if r.object_id is None:
            hint.append('Objekt nur als Freitext')
        if netto is not None and brutto_h is not None and netto > brutto_h + 0.1:
            hint.append(f'Netto groesser als Kommen-Gehen ({num(brutto_h)} h)')
        if netto is not None and netto < 0:
            hint.append('Netto in DB negativ (Datenfehler)')
            pause = None
        elif netto is not None and netto < 0.25:
            hint.append('Netto unter 15 Min')
        if r.check_out is None:
            hint.append('ohne Gehen')
        w = booking_path(r.is_manual_entry, r.client_id, r.notes)
        free = r.custom_object_name or ''
        by_month[m].append([d.isoformat(), r.personal_nr, f"{r.first_name} {r.last_name}", r.customer_id or '',
                            r.cust_name or free, r.object_id or '', r.obj_name or free,
                            r.check_in.strftime('%H:%M'), r.check_out.strftime('%H:%M') if r.check_out else '',
                            '' if pause is None else pause, num(netto), r.service_type or '', w, r.id,
                            '; '.join(hint)])
        q[m]['rows'] += 1
        q[m]['auto' if w in AUTO else 'manuell'] += 1
        q[m]['w_' + w] += 1
        ma_booked[m].add(r.emp_id)
        booked_days.add((r.emp_id, d))
        if (r.emp_id, d) not in sched_days:
            q[m]['ohne_schicht'] += 1
    ma_sched = defaultdict(set)
    for emp, d in sched_days:
        m = d.strftime('%Y-%m')
        ma_sched[m].add(emp)
        q[m]['plan_tage'] += 1
        if (emp, d) in booked_days:
            q[m]['plan_tage_gebucht'] += 1
    quality = []
    for m in sorted(set(q) | set(ma_sched)):
        x, n = q[m], q[m]['rows']
        quality.append([m, n, len(ma_sched[m]), len(ma_booked[m]), x['plan_tage'], x['plan_tage_gebucht'],
                        x['plan_tage'] - x['plan_tage_gebucht'], x['ohne_schicht'],
                        num(100 * x['auto'] / n, 0) if n else '', x['w_Stempelung App'], x['w_Auto-Booking Kat. A'],
                        x['w_Bestaetigung Kat. B'], x['w_Manuell (Admin)'], x['w_Selbstbuchung genehmigt'],
                        x['w_Altdaten (Import)'], x['abw_Urlaub'], x['abw_Krank'], x['abw_Abwesenheit']])
    return by_month, quality


QUALITY_HDR = ['Monat', 'Einsaetze', 'MA_mit_Schicht', 'MA_mit_Buchung', 'Schichttage', 'Schichttage_mit_Buchung',
               'Schichttage_ohne_Buchung', 'Einsaetze_ohne_Schicht', 'Anteil_automatisch_%', 'Stempelung_App',
               'Auto_Kat_A', 'Bestaetigung_Kat_B', 'Manuell_Admin', 'Selbstbuchung', 'Altdaten',
               'nicht_exportiert_Urlaub', 'nicht_exportiert_Krank', 'nicht_exportiert_Abwesenheit']


def objects_rows(conn):
    out = []
    for o in conn.execute(text("""
            SELECT o.id, o.name, o.address, o.is_active, o.customer_id, c.name, c.address, c.is_active
            FROM objects o LEFT JOIN customers c ON c.id = o.customer_id
            WHERE NOT o.is_test ORDER BY o.id""")):
        hint = {OBJ_URLAUB: 'Hilfsobjekt Urlaub, kein Einsatzort',
                OBJ_KRANK: 'Hilfsobjekt Krank, kein Einsatzort'}.get(o[0], '')
        out.append([o[0], o[1], o[2] or '', 'ja' if o[3] else 'nein', o[4] or '', o[5] or '', o[6] or '',
                    '' if o[4] is None else ('ja' if o[7] else 'nein'), hint])
    for c in conn.execute(text("""SELECT id, name, address, is_active FROM customers c
                                  WHERE NOT EXISTS (SELECT 1 FROM objects o WHERE o.customer_id = c.id)
                                  ORDER BY id""")):
        out.append(['', '', '', '', c[0], c[1], c[2] or '', 'ja' if c[3] else 'nein', 'Kunde ohne Objekt'])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--monat', help='JJJJ-MM (Standard: Vormonat)')
    ap.add_argument('--alle', action='store_true', help='alle Monate bis --bis')
    ap.add_argument('--bis', help='Stichtag JJJJ-MM-TT fuer --alle (Standard: Ende Vormonat)')
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--exporttag', action='store_true', help='nur am 1. Werktag des Monats exportieren (Cron)')
    a = ap.parse_args()
    if a.exporttag and date.today() != exporttag(vormonat()):
        return

    first_this_month = date.today().replace(day=1)
    if a.alle:
        bis = date.fromisoformat(a.bis) if a.bis else first_this_month - timedelta(days=1)
        months = None
    else:
        start = (datetime.strptime(a.monat, '%Y-%m').date() if a.monat
                 else (first_this_month - timedelta(days=1)).replace(day=1))
        bis = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        months = [start.strftime('%Y-%m')]

    engine = create_engine(os.getenv('DATABASE_URL'))
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        rows, sched_days = load(conn, bis)
        by_month, quality = build(rows, sched_days, bis)
        objs = objects_rows(conn)
        conn.rollback()

    os.makedirs(a.out, exist_ok=True)
    os.chmod(a.out, 0o700)
    written = []
    for m in (months if months is not None else sorted(by_month)):
        write_csv(os.path.join(a.out, f'zeiterfassung_{m}.csv'), HDR, by_month.get(m, []))
        written.append(f'{m}: {len(by_month.get(m, []))}')
    write_csv(os.path.join(a.out, 'objekte_kunden.csv'),
              ['Objekt-ID', 'Objekt', 'Objekt_Adresse', 'Objekt_aktiv', 'Kunden-ID', 'Kunde', 'Kunden_Adresse',
               'Kunde_aktiv', 'Hinweis'], objs)
    write_csv(os.path.join(a.out, 'qualitaet.csv'), QUALITY_HDR, quality)
    detail = ''
    if months:
        p = os.path.join(a.out, f'zeiterfassung_{months[0]}.csv')
        with open(p, 'rb') as f:
            detail = f" | {os.path.basename(p)} {os.path.getsize(p)} Bytes, SHA-256 {hashlib.sha256(f.read()).hexdigest()[:12]}"
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {'Exporttag ' if a.exporttag else ''}Export bis {bis}: "
          + ', '.join(written) + f" | Objekte {len(objs)}" + detail)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} FEHLER Export: {e}", file=sys.stderr)
        raise
