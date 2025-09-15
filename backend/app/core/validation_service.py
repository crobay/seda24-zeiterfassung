from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import TimeEntry, Schedule, Warning, Employee, Object
from app.schemas.warning_schema import WarningCreate
from app.core.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

class ValidationService:
    
    @staticmethod
    def check_schedule_compliance(db: Session, employee_id: int, object_id: int):
        """Prüft ob Mitarbeiter am richtigen Objekt ist"""
        today = datetime.now().weekday()
        print(f"DEBUG: Checking schedule for employee {employee_id} at object {object_id} on weekday {today}")
        
        # Dienstplan für heute holen
        schedule = db.query(Schedule).filter(
            Schedule.employee_id == employee_id,
            Schedule.weekday == today,
            Schedule.is_active == True
        ).first()
        
        if schedule:
            print(f"DEBUG: Found schedule - employee should be at object {schedule.object_id}")
        else:
            print(f"DEBUG: No schedule found for today")
        
        if schedule and schedule.object_id != object_id:
            print(f"DEBUG: Wrong object! Creating warning...")
            # Warnung erstellen
            warning = Warning(
                employee_id=employee_id,
                warning_type="WRONG_OBJECT",
                message=f"Mitarbeiter ist nicht am geplanten Objekt (Soll: Objekt {schedule.object_id})"
            )
            db.add(warning)
            db.commit()
            print(f"DEBUG: Warning created!")
            # Email senden
            EmailService.send_warning_email(
                f"Employee {employee_id}",
                "WRONG_OBJECT", 
                f"Ist bei Objekt {object_id} statt {schedule.object_id}"
            ) 
            return False
        return True
    
    @staticmethod
    def check_missing_checkout(db: Session):
        """Prüft auf vergessene Ausstempelungen"""
        # Alle offenen Stempelungen von gestern
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0)
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59)
        
        open_entries = db.query(TimeEntry).filter(
            TimeEntry.check_in >= yesterday_start,
            TimeEntry.check_in <= yesterday_end,
            TimeEntry.check_out == None
        ).all()
        
        for entry in open_entries:
            # Warnung nur wenn noch keine existiert
            existing = db.query(Warning).filter(
                Warning.employee_id == entry.employee_id,
                Warning.warning_type == "NO_CHECKOUT",
                Warning.created_at >= yesterday_start,
                Warning.is_resolved == False
            ).first()
            
            if not existing:
                warning = Warning(
                    employee_id=entry.employee_id,
                    warning_type="NO_CHECKOUT",
                    message=f"Vergessene Ausstempelung vom {entry.check_in.strftime('%d.%m.%Y %H:%M')}"
                )
                db.add(warning)
        
        db.commit()
        return len(open_entries)
    
    @staticmethod
    def check_max_working_time(db: Session, employee_id: int):
        """Prüft ob 14h Arbeitszeit überschritten"""
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        
        # Alle heutigen Einträge
        entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.check_in >= today_start
        ).all()
        
        total_minutes = 0
        for entry in entries:
            if entry.check_out:
                delta = entry.check_out - entry.check_in
            else:
                delta = datetime.now() - entry.check_in
            total_minutes += delta.total_seconds() / 60
        
        if total_minutes > 840:  # 14 Stunden = 840 Minuten
            warning = Warning(
                employee_id=employee_id,
                warning_type="MAX_TIME_EXCEEDED",
                message=f"Maximale Arbeitszeit überschritten! ({total_minutes/60:.1f} Stunden)"
            )
            db.add(warning)
            db.commit()
            return False
        return True
    
    @staticmethod
    def check_no_show(db: Session):
        """Prüft um 10 Uhr wer nicht erschienen ist"""
        current_time = datetime.now()
        if current_time.hour != 10:
            return 0
            
        today = current_time.weekday()
        
        # Alle die heute arbeiten sollten
        schedules = db.query(Schedule).filter(
            Schedule.weekday == today,
            Schedule.is_active == True
        ).all()
        
        warnings_created = 0
        for schedule in schedules:
            # Prüfen ob schon gestempelt
            today_entry = db.query(TimeEntry).filter(
                TimeEntry.employee_id == schedule.employee_id,
                TimeEntry.check_in >= current_time.replace(hour=0, minute=0, second=0)
            ).first()
            
            if not today_entry:
                warning = Warning(
                    employee_id=schedule.employee_id,
                    warning_type="NO_SHOW",
                    message=f"Mitarbeiter nicht erschienen (Sollte um {schedule.start_time} beginnen)"
                )
                db.add(warning)
                warnings_created += 1
        
        db.commit()
        return warnings_created
