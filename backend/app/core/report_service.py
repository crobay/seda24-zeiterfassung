from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
import pandas as pd
from typing import Optional, Dict, List
from app.models.models import TimeEntry, Employee, Object, Customer, User

class ReportService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_today_hours(self, employee_id: int) -> Dict:
        """Heutige Arbeitszeit eines Mitarbeiters"""
        today = date.today()
        
        entries = self.db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee_id,
            func.date(TimeEntry.check_in) == today
        ).all()
        
        total_minutes = 0
        details = []
        
        for entry in entries:
            if entry.check_out:
                duration = (entry.check_out - entry.check_in).total_seconds() / 60
                total_minutes += duration
                
                details.append({
                    "object": entry.object.name if entry.object else "Unbekannt",
                    "check_in": entry.check_in.strftime("%H:%M"),
                    "check_out": entry.check_out.strftime("%H:%M"),
                    "duration_minutes": round(duration),
                    "duration_formatted": f"{int(duration//60)}:{int(duration%60):02d}"
                })
        
        # Aktuelle offene Stempelung
        active_entry = self.db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.check_out == None
        ).first()
        
        if active_entry:
            current_duration = (datetime.now() - active_entry.check_in).total_seconds() / 60
            total_minutes += current_duration
            details.append({
                "object": active_entry.object.name if active_entry.object else "Unbekannt",
                "check_in": active_entry.check_in.strftime("%H:%M"),
                "check_out": "LÄUFT",
                "duration_minutes": round(current_duration),
                "duration_formatted": f"{int(current_duration//60)}:{int(current_duration%60):02d}"
            })
        
        return {
            "date": today.strftime("%d.%m.%Y"),
            "total_minutes": round(total_minutes),
            "total_hours": round(total_minutes / 60, 2),
            "total_formatted": f"{int(total_minutes//60)}:{int(total_minutes%60):02d}",
            "entries": details,
            "is_working": active_entry is not None
        }
    
    def get_week_hours(self, employee_id: int, week_number: Optional[int] = None, year: Optional[int] = None) -> Dict:
        """Wochenstunden eines Mitarbeiters"""
        if not week_number:
            week_number = datetime.now().isocalendar()[1]
        if not year:
            year = datetime.now().year
        
        # Montag und Sonntag der Woche berechnen
        jan1 = date(year, 1, 1)
        week_start = jan1 + timedelta(days=(week_number-1)*7 - jan1.weekday())
        week_end = week_start + timedelta(days=6)
        
        entries = self.db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee_id,
            func.date(TimeEntry.check_in) >= week_start,
            func.date(TimeEntry.check_in) <= week_end,
            TimeEntry.check_out != None
        ).all()
        
        # Nach Tag gruppieren
        daily_hours = {}
        for day in range(7):
            current_date = week_start + timedelta(days=day)
            daily_hours[current_date.strftime("%A")] = {
                "date": current_date.strftime("%d.%m"),
                "hours": 0,
                "formatted": "0:00"
            }
        
        total_minutes = 0
        for entry in entries:
            day_name = entry.check_in.strftime("%A")
            duration = (entry.check_out - entry.check_in).total_seconds() / 60
            
            if day_name in daily_hours:
                daily_hours[day_name]["hours"] += duration / 60
                daily_hours[day_name]["formatted"] = f"{int(duration//60)}:{int(duration%60):02d}"
                total_minutes += duration
        
        # Deutsche Wochentage
        german_days = {
            "Monday": "Montag",
            "Tuesday": "Dienstag", 
            "Wednesday": "Mittwoch",
            "Thursday": "Donnerstag",
            "Friday": "Freitag",
            "Saturday": "Samstag",
            "Sunday": "Sonntag"
        }
        
        daily_hours_german = {}
        for eng, ger in german_days.items():
            if eng in daily_hours:
                daily_hours_german[ger] = daily_hours[eng]
        
        return {
            "week_number": week_number,
            "year": year,
            "week_start": week_start.strftime("%d.%m.%Y"),
            "week_end": week_end.strftime("%d.%m.%Y"),
            "daily_hours": daily_hours_german,
            "total_minutes": round(total_minutes),
            "total_hours": round(total_minutes / 60, 2),
            "total_formatted": f"{int(total_minutes//60)}:{int(total_minutes%60):02d}"
        }
    
    def get_month_hours(self, employee_id: int, month: Optional[int] = None, year: Optional[int] = None) -> Dict:
        """Monatsstunden mit Überstunden-Berechnung"""
        if not month:
            month = datetime.now().month
        if not year:
            year = datetime.now().year
        
        # Erster und letzter Tag des Monats
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        entries = self.db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee_id,
            func.date(TimeEntry.check_in) >= month_start,
            func.date(TimeEntry.check_in) <= month_end,
            TimeEntry.check_out != None
        ).all()
        
        total_minutes = 0
        work_days = set()
        
        for entry in entries:
            duration = (entry.check_out - entry.check_in).total_seconds() / 60
            total_minutes += duration
            work_days.add(entry.check_in.date())
        
        # Mitarbeiter-Info für Soll-Berechnung
        employee = self.db.query(Employee).filter(Employee.id == employee_id).first()
        
        # Standard: 8 Stunden pro Arbeitstag (kann später aus DB kommen)
        sollstunden = len(work_days) * 8
        ueberstunden = (total_minutes / 60) - sollstunden
        
        return {
            "month": month,
            "year": year,
            "month_name": month_start.strftime("%B %Y"),
            "work_days": len(work_days),
            "total_minutes": round(total_minutes),
            "total_hours": round(total_minutes / 60, 2),
            "total_formatted": f"{int(total_minutes//60)}:{int(total_minutes%60):02d}",
            "soll_hours": sollstunden,
            "ueberstunden": round(ueberstunden, 2),
            "hourly_rate": employee.hourly_rate if employee else 12.50,
            "estimated_salary": round((total_minutes / 60) * (employee.hourly_rate if employee else 12.50), 2)
        }
    
    def get_all_employees_daily(self, target_date: Optional[date] = None) -> Dict:
        """Admin: Tagesübersicht aller Mitarbeiter"""
        if not target_date:
            target_date = date.today()
        
        employees = self.db.query(Employee).all()
        result = []
        
        for emp in employees:
            entries = self.db.query(TimeEntry).filter(
                TimeEntry.employee_id == emp.id,
                func.date(TimeEntry.check_in) == target_date
            ).all()
            
            total_minutes = 0
            objects_worked = []
            
            for entry in entries:
                if entry.check_out:
                    duration = (entry.check_out - entry.check_in).total_seconds() / 60
                    total_minutes += duration
                    if entry.object and entry.object.name not in objects_worked:
                        objects_worked.append(entry.object.name)
            
            result.append({
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "personal_nr": emp.personal_nr,
                "total_hours": round(total_minutes / 60, 2),
                "total_formatted": f"{int(total_minutes//60)}:{int(total_minutes%60):02d}",
                "objects": ", ".join(objects_worked) if objects_worked else "Keine",
                "status": "Anwesend" if total_minutes > 0 else "Abwesend"
            })
        
        return {
            "date": target_date.strftime("%d.%m.%Y"),
            "employees": result,
            "total_employees": len(employees),
            "present": len([e for e in result if e["status"] == "Anwesend"])
        }
    
def export_to_csv(self, month: int, year: int) -> bytes:
        """CSV-Export für einen Monat - SIMPLE"""
        try:
            month_start = date(year, month, 1)
            if month == 12:
                month_end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(year, month + 1, 1) - timedelta(days=1)
            
            # Header
            csv_content = "Datum;Mitarbeiter;Objekt;Einstempelung;Ausstempelung;Stunden\n"
            
            # Alle Einträge des Monats
            entries = self.db.query(TimeEntry).filter(
                func.date(TimeEntry.check_in) >= month_start,
                func.date(TimeEntry.check_in) <= month_end,
                TimeEntry.check_out != None
            ).all()
            
            if not entries:
                csv_content += "Keine Daten vorhanden\n"
                return csv_content.encode("utf-8-sig")
            
            for entry in entries:
                # Dauer berechnen
                duration_hours = 0
                if entry.check_out:
                    duration_hours = round((entry.check_out - entry.check_in).total_seconds() / 3600, 2)
                
                # CSV-Zeile
                line = f"{entry.check_in.strftime('%d.%m.%Y')};"
                line += f"MA-{entry.employee_id};"
                line += f"Objekt-{entry.object_id};"
                line += f"{entry.check_in.strftime('%H:%M')};"
                line += f"{entry.check_out.strftime('%H:%M')};"
                line += f"{duration_hours}\n"
                csv_content += line
            
            return csv_content.encode("utf-8-sig")
        except Exception as e:
            error_msg = f"Fehler beim CSV-Export: {str(e)}"
            return error_msg.encode("utf-8-sig")
