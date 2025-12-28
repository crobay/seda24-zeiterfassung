from sqlalchemy import text
"""
SEDA24 - PDF Generator für Zeitnachweise und Kilometerabrechnungen
"""
import os
import subprocess
from datetime import datetime, date
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import TimeEntry, Employee, Object, User


class PDFGenerator:
    """Generiert professionelle PDFs für Zeitnachweise und Kilometer"""
    
    def __init__(self, db: Session):
        self.db = db
        self.output_dir = "/tmp/seda24_pdfs"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_zeitnachweis(self, employee_id: int, year: int, month: int) -> str:
        """
        Generiert Zeitnachweis-PDF für einen Mitarbeiter
        
        Returns:
            Pfad zur generierten PDF-Datei
        """
        # Mitarbeiter laden
        employee = self.db.query(Employee).filter(Employee.id == employee_id).first()
        if not employee:
            raise ValueError(f"Mitarbeiter {employee_id} nicht gefunden")
        
        # Zeitbuchungen laden
        entries = self._get_time_entries(employee_id, year, month)
        
        # Statistiken berechnen
        stats = self._calculate_stats(entries, employee)
        
        # HTML generieren
        html_content = self._generate_zeitnachweis_html(employee, entries, stats, year, month)
        
        # PDF erstellen
        filename = f"Zeitnachweis_{employee.first_name}_{employee.last_name}_{month:02d}_{year}.pdf"
        pdf_path = os.path.join(self.output_dir, filename)
        
        self._html_to_pdf(html_content, pdf_path)
        
        return pdf_path
    
    def generate_kilometer(self, employee_id: int, year: int, month: int) -> str:
        """
        Generiert Kilometer-Abrechnung für einen Mitarbeiter
        
        Returns:
            Pfad zur generierten PDF-Datei
        """
        # Mitarbeiter laden
        employee = self.db.query(Employee).filter(Employee.id == employee_id).first()
        if not employee:
            raise ValueError(f"Mitarbeiter {employee_id} nicht gefunden")
        
        # Kilometer-Daten laden
        km_entries = self._get_kilometer_entries(employee_id, year, month)
        
        # Statistiken berechnen
        total_km = sum(e['km'] for e in km_entries if e['abrechnbar'])
        total_betrag = float(total_km) * 0.30
        
        # HTML generieren
        html_content = self._generate_kilometer_html(employee, km_entries, total_km, total_betrag, year, month)
        
        # PDF erstellen
        filename = f"Kilometer_{employee.first_name}_{employee.last_name}_{month:02d}_{year}.pdf"
        pdf_path = os.path.join(self.output_dir, filename)
        
        self._html_to_pdf(html_content, pdf_path)
        
        return pdf_path
    
    def _get_time_entries(self, employee_id: int, year: int, month: int) -> List[Dict]:
        """Lädt Zeitbuchungen für einen Monat"""
        from calendar import monthrange
        
        # Ersten und letzten Tag des Monats
        start_date = datetime(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = datetime(year, month, last_day, 23, 59, 59)
        
        # Query
        entries = self.db.query(TimeEntry, Object.name).join(
            Object, TimeEntry.object_id == Object.id
        ).filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.check_in >= start_date,
            TimeEntry.check_in <= end_date
        ).order_by(TimeEntry.check_in).all()
        
        # Aufbereiten
        result = []
        for entry, object_name in entries:
            if entry.check_out:
                delta = entry.check_out - entry.check_in
                hours = delta.total_seconds() / 3600
            else:
                hours = 0
            
            # Typ erkennen
            entry_type = 'normal'
            if entry.object_id == 999:
                entry_type = 'urlaub'
            elif 'krank' in object_name.lower():
                entry_type = 'krank'
            
            result.append({
                'date': entry.check_in.date(),
                'object_name': object_name,
                'check_in': entry.check_in,
                'check_out': entry.check_out,
                'hours': round(hours, 2),
                'hourly_rate': entry.hourly_rate or 15.0,
                'amount': round(hours * (entry.hourly_rate or 15.0), 2),
                'type': entry_type
            })
        
        return result
    
    def _calculate_stats(self, entries: List[Dict], employee: Employee) -> Dict:
        """Berechnet Statistiken für Header"""
        total_hours = 0
        work_amount = 0
        urlaubstage = 0
        urlaub_amount = 0
        kranktage = 0
        arbeitstage = 0
        
        for e in entries:
            if e['type'] == 'urlaub':
                urlaubstage += 1
                urlaub_amount += e['amount']
            elif e['type'] == 'krank':
                kranktage += 1
                work_amount += e['amount']  # Krankengeld auch zählen
            else:
                total_hours += e['hours']
                work_amount += e['amount']
                arbeitstage += 1
        
        return {
            'total_hours': round(total_hours, 2),
            'work_amount': round(work_amount, 2),
            'urlaubstage': urlaubstage,
            'urlaub_amount': round(urlaub_amount, 2),
            'kranktage': kranktage,
            'arbeitstage': arbeitstage,
            'gesamt_brutto': round(work_amount + urlaub_amount, 2)
        }
    
    def _get_kilometer_entries(self, employee_id: int, year: int, month: int) -> List[Dict]:
        """Lädt Kilometer-Einträge aus km_daily_entries"""
        from calendar import monthrange
        
        # Ersten und letzten Tag
        start_date = datetime(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = datetime(year, month, last_day)
        
        # Aus km_daily_entries laden (mit Object-Join für Namen)
        from sqlalchemy import text
        query = text("""
            SELECT 
                kde.date,
                o.name as object_name,
                kde.distance_km,
                kde.is_longest_trip,
                kde.amount
            FROM km_daily_entries kde
            JOIN objects o ON o.id = kde.object_id
            WHERE kde.employee_id = :emp_id
              AND kde.date >= :start_date
              AND kde.date <= :end_date
            ORDER BY kde.date, kde.distance_km DESC
        """)
        
        result_proxy = self.db.execute(
            query,
            {
                'emp_id': employee_id,
                'start_date': start_date.date(),
                'end_date': end_date.date()
            }
        )
        
        result = []
        for row in result_proxy:
            result.append({
                'date': row.date,
                'object_name': row.object_name,
                'km': float(row.distance_km),
                'abrechnbar': row.is_longest_trip,  # HIER IST DER FIX!
                'betrag': float(row.amount)
            })
        
        return result
        # Temporär: Dummy-Werte
        result = self.db.execute(
            text("SELECT distance_km FROM km_distances WHERE employee_id = :emp AND object_id = :obj"),
            {"emp": employee_id, "obj": object_id}
        ).fetchone()
        
        return result[0] if result else 5.5
    
    def _generate_zeitnachweis_html(self, employee: Employee, entries: List[Dict], 
                                   stats: Dict, year: int, month: int) -> str:
        """Generiert HTML für Zeitnachweis"""
        
        # Monatsnamen
        month_names = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                      'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
        
        # Tabellen-Zeilen
        table_rows = ""
        for e in entries:
            weekday = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][e['date'].weekday()]
            
            if e['type'] == 'urlaub':
                row_class = "urlaub-row"
                badge = '<span class="badge badge-urlaub">🏖️ Urlaub</span>'
                zeit = "-"
                stunden = "-"
                lohn_h = "-"
            elif e['type'] == 'krank':
                row_class = "krank-row"
                badge = '<span class="badge badge-krank">🤒 Krankheit</span>'
                zeit = "-"
                stunden = "-"
                lohn_h = "-"
            else:
                row_class = ""
                badge = e['object_name']
                zeit = f"{e['check_in'].strftime('%H:%M')} - {e['check_out'].strftime('%H:%M')}"
                stunden = f"{e['hours']}"
                lohn_h = f"{e['hourly_rate']:.2f} €"
            
            table_rows += f"""
                    <tr class="{row_class}">
                        <td><strong>{weekday}, {e['date'].strftime('%d.%m.')}</strong></td>
                        <td>{badge}</td>
                        <td class="center-align">{zeit}</td>
                        <td class="right-align">{stunden}</td>
                        <td class="right-align">{lohn_h}</td>
                        <td class="right-align"><strong>{e['amount']:.2f} €</strong></td>
                    </tr>
            """
        
        # Komplettes HTML (aus unserer Vorlage)
        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: white; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; }}
        
        /* HEADER */
        .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8f 100%); color: white; padding: 40px; position: relative; }}
        .logo-area {{ font-size: 32px; font-weight: bold; letter-spacing: 2px; }}
        .header h1 {{ font-size: 28px; font-weight: 300; margin: 10px 0 5px 0; }}
        .header p {{ opacity: 0.9; font-size: 16px; }}
        
        /* INFO GRID */
        .info-grid {{ display: flex; flex-wrap: wrap; gap: 20px; padding: 40px; background: #f8f9fa; }}
        .info-card {{ background: white; padding: 25px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                     border-left: 5px solid #1e3a5f; width: calc(50% - 10px); flex: 0 0 calc(50% - 10px); }}
        .info-card-icon {{ font-size: 24px; margin-bottom: 10px; }}
        .info-card-label {{ font-size: 13px; color: #666; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
        .info-card-value {{ font-size: 24px; font-weight: bold; color: #1e3a5f; }}
        .info-card-sub {{ font-size: 14px; color: #888; margin-top: 5px; }}
        
        /* HIGHLIGHT */
        .highlight-box {{ margin: 0 40px 30px 40px; padding: 25px; background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                         color: white; border-radius: 15px; display: flex; justify-content: space-between; align-items: center; }}
        .highlight-item {{ text-align: center; flex: 1; }}
        .highlight-item .label {{ font-size: 13px; opacity: 0.9; margin-bottom: 8px; }}
        .highlight-item .value {{ font-size: 28px; font-weight: bold; }}
        .divider {{ width: 2px; height: 60px; background: rgba(255,255,255,0.3); }}
        
        /* TABLE */
        .table-container {{ padding: 0 40px 40px 40px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8f 100%); color: white; padding: 18px 15px;
              text-align: left; font-weight: 600; font-size: 13px; text-transform: uppercase; }}
        td {{ padding: 16px 15px; border-bottom: 1px solid #e9ecef; font-size: 14px; }}
        .urlaub-row {{ background: linear-gradient(90deg, #fff9e6 0%, #ffffff 100%); }}
        .urlaub-row td {{ font-style: italic; color: #d97706; }}
        .krank-row {{ background: linear-gradient(90deg, #fee2e2 0%, #ffffff 100%); }}
        .krank-row td {{ font-style: italic; color: #dc2626; }}
        .total-row {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8f 100%); color: white; font-weight: bold; }}
        .total-row td {{ padding: 20px 15px; }}
        .right-align {{ text-align: right; }}
        .center-align {{ text-align: center; }}
        .badge {{ display: inline-block; padding: 5px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
        .badge-urlaub {{ background: #fef3c7; color: #92400e; }}
        .badge-krank {{ background: #fee2e2; color: #991b1b; }}
        
        /* FOOTER */
        .footer {{ padding: 40px; background: #f8f9fa; border-top: 3px solid #1e3a5f; }}
        .thank-you {{ text-align: center; font-size: 18px; color: #1e3a5f; font-weight: 600; margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-area">SEDA24</div>
            <h1>Zeitnachweis & Lohnabrechnung</h1>
            <p>Professionelle Zeiterfassung für Ihr Team</p>
        </div>
        
        <div class="info-grid">
            <div class="info-card">
                <div class="info-card-icon">👤</div>
                <div class="info-card-label">Mitarbeiter</div>
                <div class="info-card-value">{employee.first_name} {employee.last_name}</div>
                <div class="info-card-sub">Personal-Nr: {employee.personal_nr}</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">📅</div>
                <div class="info-card-label">Abrechnungszeitraum</div>
                <div class="info-card-value">{month_names[month]} {year}</div>
                <div class="info-card-sub">01.{month:02d}. - {entries[-1]['date'].day if entries else '31'}.{month:02d}.{year}</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">⏰</div>
                <div class="info-card-label">Geleistete Arbeitsstunden</div>
                <div class="info-card-value">{stats['total_hours']} h</div>
                <div class="info-card-sub">{stats['arbeitstage']} Arbeitstage</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">💰</div>
                <div class="info-card-label">Bruttolohn (Arbeit)</div>
                <div class="info-card-value">{stats['work_amount']:.2f} €</div>
                <div class="info-card-sub">@ {employee.hourly_rate or 15.0:.2f} €/h Standard</div>
            </div>
        </div>
        
        <div class="highlight-box">
            <div class="highlight-item">
                <div class="label">🏖️ Urlaubstage</div>
                <div class="value">{stats['urlaubstage']} Tage</div>
            </div>
            <div class="divider"></div>
            <div class="highlight-item">
                <div class="label">💵 Urlaubsgeld</div>
                <div class="value">{stats['urlaub_amount']:.2f} €</div>
            </div>
            <div class="divider"></div>
            <div class="highlight-item">
                <div class="label">🤒 Krankheitstage</div>
                <div class="value">{stats['kranktage']} Tag{'e' if stats['kranktage'] != 1 else ''}</div>
            </div>
            <div class="divider"></div>
            <div class="highlight-item">
                <div class="label">💰 GESAMT BRUTTO</div>
                <div class="value">{stats['gesamt_brutto']:.2f} €</div>
            </div>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Datum</th>
                        <th>Kunde/Objekt</th>
                        <th class="center-align">Arbeitszeit</th>
                        <th class="right-align">Stunden</th>
                        <th class="right-align">Lohn/h</th>
                        <th class="right-align">Betrag</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                    <tr class="total-row">
                        <td colspan="3"><strong>GESAMT {month_names[month].upper()} {year}</strong></td>
                        <td class="right-align"><strong>{stats['total_hours']} h</strong></td>
                        <td class="right-align">-</td>
                        <td class="right-align"><strong>{stats['gesamt_brutto']:.2f} €</strong></td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <div class="thank-you">✨ Vielen Dank für Ihren wertvollen Einsatz! ✨</div>
            <div style="background: #f0f9ff; border-left: 4px solid #0284c7; padding: 20px; border-radius: 10px;">
                <h3 style="color: #0c4a6e; margin-bottom: 15px; font-size: 16px;">📋 PRÜFUNG & EINSPRUCH</h3>
                <p style="color: #334155; margin-bottom: 10px;">Bitte prüfen Sie diese Abrechnung sorgfältig innerhalb von <strong>7 Tagen</strong>.</p>
                <p style="color: #334155; margin-bottom: 10px;"><strong>Bei Unstimmigkeiten:</strong><br>📧 E-Mail an: <strong>buchhaltung@seda24.de</strong></p>
                <p style="color: #64748b; font-size: 13px; margin-bottom: 10px;">Ohne Rückmeldung innerhalb von 7 Tagen gilt die Abrechnung als geprüft und akzeptiert.</p>
                <p style="color: #64748b; font-size: 13px; font-style: italic; margin-top: 15px; padding-top: 15px; border-top: 1px solid #cbd5e1;">Diese Abrechnung wurde digital erstellt und ist ohne Unterschrift gültig.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def _generate_kilometer_html(self, employee: Employee, entries: List[Dict],
                                 total_km: float, total_betrag: float, year: int, month: int) -> str:
        """Generiert HTML für Kilometer-Abrechnung"""
        
        month_names = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                      'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
        
        # Tabellen-Zeilen
        table_rows = ""
        for e in entries:
            weekday = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][e['date'].weekday()]
            
            if e['abrechnbar']:
                row_class = "charge-row"
                badge = '<span class="badge badge-abrechnbar">✓ Abgerechnet</span>'
            else:
                row_class = "no-charge-row"
                badge = '<span class="badge badge-nicht">○ Nicht weiteste</span>'
            
            table_rows += f"""
                    <tr class="{row_class}">
                        <td><strong>{weekday}, {e['date'].strftime('%d.%m.')}</strong></td>
                        <td>{e['object_name']}</td>
                        <td class="center-align">{badge}</td>
                        <td class="right-align">{e['km']:.1f} km</td>
                        <td class="right-align"><strong>{e['betrag']:.2f} €</strong></td>
                    </tr>
            """
        
        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: white; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        
        .header {{ background: linear-gradient(135deg, #d97706 0%, #b45309 100%); color: white; padding: 40px; }}
        .logo-area {{ font-size: 32px; font-weight: bold; letter-spacing: 2px; }}
        .header h1 {{ font-size: 28px; font-weight: 300; margin: 10px 0 5px 0; }}
        .header p {{ opacity: 0.9; font-size: 16px; }}
        
        .info-grid {{ display: flex; flex-wrap: wrap; gap: 20px; padding: 40px; background: #f8f9fa; }}
        .info-card {{ background: white; padding: 25px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                     border-left: 5px solid #d97706; width: calc(50% - 10px); flex: 0 0 calc(50% - 10px); }}
        .info-card-icon {{ font-size: 24px; margin-bottom: 10px; }}
        .info-card-label {{ font-size: 13px; color: #666; text-transform: uppercase; margin-bottom: 8px; }}
        .info-card-value {{ font-size: 24px; font-weight: bold; color: #d97706; }}
        .info-card-sub {{ font-size: 14px; color: #888; margin-top: 5px; }}
        
        .highlight-box {{ margin: 0 40px 30px 40px; padding: 30px; background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
                         color: white; border-radius: 15px; text-align: center; }}
        .highlight-box .label {{ font-size: 16px; opacity: 0.9; margin-bottom: 15px; }}
        .highlight-box .value {{ font-size: 48px; font-weight: bold; }}
        
        .info-box {{ margin: 0 40px 30px 40px; padding: 20px; background: #fef3c7; border-left: 5px solid #d97706; border-radius: 10px; }}
        .info-box p {{ margin: 8px 0; color: #78350f; font-size: 14px; }}
        
        .table-container {{ padding: 0 40px 40px 40px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: linear-gradient(135deg, #d97706 0%, #b45309 100%); color: white; padding: 18px 15px;
              text-align: left; font-size: 13px; text-transform: uppercase; }}
        td {{ padding: 16px 15px; border-bottom: 1px solid #e9ecef; font-size: 14px; }}
        .no-charge-row {{ opacity: 0.5; }}
        .charge-row {{ background: linear-gradient(90deg, #ecfdf5 0%, #ffffff 100%); }}
        .charge-row td {{ font-weight: 600; color: #059669; }}
        .total-row {{ background: linear-gradient(135deg, #d97706 0%, #b45309 100%); color: white; font-weight: bold; }}
        .total-row td {{ padding: 20px 15px; }}
        .right-align {{ text-align: right; }}
        .center-align {{ text-align: center; }}
        .badge {{ display: inline-block; padding: 5px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
        .badge-abrechnbar {{ background: #d1fae5; color: #065f46; }}
        .badge-nicht {{ background: #f3f4f6; color: #6b7280; }}
        
        .footer {{ padding: 40px; background: #f8f9fa; border-top: 3px solid #d97706; }}
        .thank-you {{ text-align: center; font-size: 18px; color: #d97706; font-weight: 600; margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-area">SEDA24</div>
            <h1>Kilometerabrechnung</h1>
            <p>Fahrtkosten-Erstattung für Dienstfahrten</p>
        </div>
        
        <div class="info-grid">
            <div class="info-card">
                <div class="info-card-icon">👤</div>
                <div class="info-card-label">Mitarbeiter</div>
                <div class="info-card-value">{employee.first_name} {employee.last_name}</div>
                <div class="info-card-sub">Personal-Nr: {employee.personal_nr}</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">📅</div>
                <div class="info-card-label">Abrechnungszeitraum</div>
                <div class="info-card-value">{month_names[month]} {year}</div>
                <div class="info-card-sub">01.{month:02d}. - {entries[-1]['date'].day if entries else '31'}.{month:02d}.{year}</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">🗺️</div>
                <div class="info-card-label">Gefahrene Kilometer</div>
                <div class="info-card-value">{total_km:.1f} km</div>
                <div class="info-card-sub">nur abrechnbar</div>
            </div>
            <div class="info-card">
                <div class="info-card-icon">💰</div>
                <div class="info-card-label">Erstattungsbetrag</div>
                <div class="info-card-value">{total_betrag:.2f} €</div>
                <div class="info-card-sub">@ 0,30 €/km</div>
            </div>
        </div>
        
        <div class="highlight-box">
            <div class="label">💵 GESAMT FAHRTKOSTEN-ERSTATTUNG</div>
            <div class="value">{total_betrag:.2f} €</div>
        </div>
        
        <div class="info-box">
            <p><strong>ℹ️ Berechnungsgrundlage:</strong></p>
            <p>✅ Pro Tag wird nur die weiteste Fahrt abgerechnet (0,30 €/km)</p>
            <p>✅ Alle anderen Fahrten des Tages werden dokumentiert, aber nicht abgerechnet</p>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Datum</th>
                        <th>Kunde/Objekt</th>
                        <th class="center-align">Status</th>
                        <th class="right-align">Entfernung</th>
                        <th class="right-align">Erstattung</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                    <tr class="total-row">
                        <td colspan="3"><strong>GESAMT {month_names[month].upper()} {year}</strong></td>
                        <td class="right-align"><strong>{total_km:.1f} km</strong></td>
                        <td class="right-align"><strong>{total_betrag:.2f} €</strong></td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <div class="thank-you">🚗 Gute und sichere Fahrt! 🚗</div>
            <div style="background: #fffbeb; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 10px;">
                <h3 style="color: #92400e; margin-bottom: 15px; font-size: 16px;">📋 PRÜFUNG & EINSPRUCH</h3>
                <p style="color: #334155; margin-bottom: 10px;">Bitte prüfen Sie diese Abrechnung sorgfältig innerhalb von <strong>7 Tagen</strong>.</p>
                <p style="color: #334155; margin-bottom: 10px;"><strong>Bei Unstimmigkeiten:</strong><br>📧 E-Mail an: <strong>buchhaltung@seda24.de</strong></p>
                <p style="color: #64748b; font-size: 13px;">Ohne Rückmeldung innerhalb von 7 Tagen gilt die Abrechnung als geprüft und akzeptiert.</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def _html_to_pdf(self, html_content: str, output_path: str):
        """Konvertiert HTML zu PDF mit wkhtmltopdf"""
        import tempfile
        
        # HTML in Temp-Datei schreiben
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            html_file = f.name
        
        try:
            # wkhtmltopdf aufrufen
            cmd = [
                'wkhtmltopdf',
                '--enable-local-file-access',
                '--page-size', 'A4',
                '--margin-top', '10mm',
                '--margin-bottom', '10mm',
                '--margin-left', '10mm',
                '--margin-right', '10mm',
                html_file,
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            
        finally:
            # Temp-Datei löschen
            os.unlink(html_file)
