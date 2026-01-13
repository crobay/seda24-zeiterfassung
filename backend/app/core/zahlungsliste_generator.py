import os
from sqlalchemy.orm import Session
from sqlalchemy import text
import pdfkit

class ZahlungslisteGenerator:
    def __init__(self, db: Session):
        self.db = db
        self.output_dir = "/tmp/seda24_pdfs"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate(self, year: int, month: int):
        """Generiert Zahlungsliste für alle MA"""
        
        # Daten holen
        query = text(f"""
            SELECT 
              e.first_name || ' ' || e.last_name as name,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 15 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 ELSE 0 END), 0)::numeric, 2) as std15,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 15 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 * 15 ELSE 0 END), 0)::numeric, 2) as bet15,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 17 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 ELSE 0 END), 0)::numeric, 2) as std17,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 17 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 * 17 ELSE 0 END), 0)::numeric, 2) as bet17,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 20 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 ELSE 0 END), 0)::numeric, 2) as std20,
              ROUND(COALESCE(SUM(CASE WHEN te.hourly_rate = 20 THEN EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 * 20 ELSE 0 END), 0)::numeric, 2) as bet20,
              ROUND(COALESCE((SELECT SUM(amount) FROM km_daily_entries kde WHERE kde.employee_id = e.id AND EXTRACT(YEAR FROM kde.date) = {year} AND EXTRACT(MONTH FROM kde.date) = {month} AND kde.is_billable = true), 0)::numeric, 2) as km,
              ROUND((COALESCE(SUM(EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600 * te.hourly_rate), 0) + COALESCE((SELECT SUM(amount) FROM km_daily_entries kde WHERE kde.employee_id = e.id AND EXTRACT(YEAR FROM kde.date) = {year} AND EXTRACT(MONTH FROM kde.date) = {month} AND kde.is_billable = true), 0))::numeric, 2) as gesamt
            FROM employees e
            LEFT JOIN time_entries te ON te.employee_id = e.id 
              AND EXTRACT(YEAR FROM te.check_in) = {year} 
              AND EXTRACT(MONTH FROM te.check_in) = {month}
            WHERE e.is_active = true
            GROUP BY e.id, e.first_name, e.last_name
            HAVING COALESCE(SUM(EXTRACT(EPOCH FROM (te.check_out - te.check_in))/3600), 0) > 0
            ORDER BY e.last_name, e.first_name
        """)
        
        result = self.db.execute(query)
        rows = result.fetchall()
        
        # HTML erstellen
        html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ text-align: center; color: #333; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 10px; }}
th {{ background-color: #4CAF50; color: white; padding: 8px; text-align: left; }}
td {{ padding: 6px; border-bottom: 1px solid #ddd; }}
tr:hover {{ background-color: #f5f5f5; }}
.right {{ text-align: right; }}
.total {{ font-weight: bold; background-color: #e8f5e9; }}
</style>
</head>
<body>
<h1>Zahlungsliste {month:02d}/{year}</h1>
<table>
<tr>
<th>Mitarbeiter</th>
<th class="right">Std. 15€</th>
<th class="right">Betrag 15€</th>
<th class="right">Std. 17€</th>
<th class="right">Betrag 17€</th>
<th class="right">Std. 20€</th>
<th class="right">Betrag 20€</th>
<th class="right">KM-Geld</th>
<th class="right">Gesamt</th>
</tr>
'''
        
        total_bet15 = 0
        total_bet17 = 0
        total_bet20 = 0
        total_km = 0
        total_gesamt = 0
        
        for row in rows:
            name, std15, bet15, std17, bet17, std20, bet20, km, gesamt = row
            html += f'''<tr>
<td>{name}</td>
<td class="right">{std15}</td>
<td class="right">{bet15:.2f} €</td>
<td class="right">{std17}</td>
<td class="right">{bet17:.2f} €</td>
<td class="right">{std20}</td>
<td class="right">{bet20:.2f} €</td>
<td class="right">{km:.2f} €</td>
<td class="right"><strong>{gesamt:.2f} €</strong></td>
</tr>
'''
            total_bet15 += float(bet15)
            total_bet17 += float(bet17)
            total_bet20 += float(bet20)
            total_km += float(km)
            total_gesamt += float(gesamt)
        
        html += f'''<tr class="total">
<td><strong>GESAMT</strong></td>
<td class="right"></td>
<td class="right"><strong>{total_bet15:.2f} €</strong></td>
<td class="right"></td>
<td class="right"><strong>{total_bet17:.2f} €</strong></td>
<td class="right"></td>
<td class="right"><strong>{total_bet20:.2f} €</strong></td>
<td class="right"><strong>{total_km:.2f} €</strong></td>
<td class="right"><strong>{total_gesamt:.2f} €</strong></td>
</tr>
</table>
</body>
</html>'''
        
        # PDF erstellen
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            html_path = f.name
        
        pdf_path = os.path.join(self.output_dir, f"Zahlungsliste_{month:02d}_{year}.pdf")
        pdfkit.from_file(html_path, pdf_path)
        os.unlink(html_path)
        
        return pdf_path
