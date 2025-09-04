from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from datetime import datetime
from io import BytesIO

def generate_monthly_timesheet_pdf(employee, entries, year, month):
    """Generiert PDF genau wie Drazens Muster"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm)
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1e40af'),
        alignment=TA_CENTER
    )
    
    elements = []
    
    # Header
    elements.append(Paragraph("Zeitnachweis - SEDA24", title_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # Mitarbeiter Info
    month_names = {
        1: "Januar", 2: "Februar", 3: "März", 4: "April",
        5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
        9: "September", 10: "Oktober", 11: "November", 12: "Dezember"
    }
    
    info_data = [
        ['Mitarbeiter:', f"{employee.first_name} {employee.last_name}"],
        ['Monat:', f"{month_names[month]} {year}"],
    ]
    
    info_table = Table(info_data, colWidths=[4*cm, 10*cm])
    info_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica-Bold', 12),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Berechne Gesamt
    total_hours = 0
    total_lohn = 0
    
    # Tabellen-Daten vorbereiten
    table_data = [
        ['Datum', 'Kunde', 'Arbeitszeit', 'Stunden', 'Lohn/h', 'Lohn Gesamt']
    ]
    
    for entry in entries:
        if entry.check_out:
            # Stunden berechnen
            diff = entry.check_out - entry.check_in
            hours = round(diff.total_seconds() / 3600, 2)
            total_hours += hours
            
            # Lohn berechnen
            lohn = hours * employee.hourly_rate
            total_lohn += lohn
            
            # Datum formatieren (Di, 01.07.2025)
            weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
            weekday = weekdays[entry.check_in.weekday()]
            date_str = f"{weekday}, {entry.check_in.strftime('%d.%m.%Y')}"
            
            # Arbeitszeit (15:00 bis 20:00)
            time_str = f"{entry.check_in.strftime('%H:%M')} bis {entry.check_out.strftime('%H:%M')}"
            
            # Kunde/Objekt
            kunde = entry.object.name if entry.object else "Unbekannt"
            
            table_data.append([
                date_str,
                kunde,
                time_str,
                f"{hours:.2f}",
                f"{employee.hourly_rate:.2f} €",
                f"{lohn:.2f} €"
            ])
    
    # Übertrag-Zeile am Anfang (falls gewünscht)
    table_data.insert(1, [
        f"{weekdays[0]}, 01.{month:02d}.{year}",
        "Übertrag",
        "-",
        "-",
        "-",
        "- €"
    ])
    
    # Tabelle erstellen
    table = Table(table_data, colWidths=[3.5*cm, 4*cm, 4*cm, 2*cm, 2*cm, 3*cm])
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        
        # Body
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (3, 1), (5, -1), 'RIGHT'),
        
        # Alternierende Zeilen
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # Zusammenfassung
    summary_data = [
        ['Geleistete Stunden:', f"{total_hours:.2f}"],
        ['Bruttolohn:', f"{total_lohn:.2f} €"],
        ['Urlaubsbetrag:', "0,00 €"],
        ['Übertrag:', "0,00 €"],
    ]
    
    summary_table = Table(summary_data, colWidths=[5*cm, 4*cm])
    summary_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 11),
        ('FONT', (1, 0), (1, -1), 'Helvetica-Bold', 11),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TEXTCOLOR', (0, 0), (-1, 1), colors.HexColor('#1e40af')),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 2*cm))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.grey
    )
    elements.append(Paragraph("Herzlichen Dank für Ihren Einsatz!", footer_style))
    
    # PDF generieren
    doc.build(elements)
    buffer.seek(0)
    
    return buffer
