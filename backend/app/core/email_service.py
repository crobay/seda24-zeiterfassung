from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Email-Service - später mit echtem SMTP"""
    
    @staticmethod
    def send_warning_email(employee_name: str, warning_type: str, message: str):
        """Sendet Email an Admin bei Warnungen"""
        # TODO: Später echte Email-Implementation
        email_content = f"""
        ⚠️ WARNUNG IM ZEITERFASSUNGSSYSTEM
        
        Mitarbeiter: {employee_name}
        Typ: {warning_type}
        Nachricht: {message}
        Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        
        Bitte im System prüfen!
        """
        
        # Erstmal nur loggen
        logger.warning(f"EMAIL WÜRDE GESENDET: {email_content}")
        print(f"\n📧 EMAIL-SIMULATION:\n{email_content}\n")
        return True
    
    @staticmethod
    def send_daily_summary(warnings_count: int, missing_checkouts: int):
        """Tägliche Zusammenfassung"""
        summary = f"""
        📊 TÄGLICHE ZUSAMMENFASSUNG
        
        Datum: {datetime.now().strftime('%d.%m.%Y')}
        Neue Warnungen: {warnings_count}
        Vergessene Ausstempelungen: {missing_checkouts}
        
        Details im System einsehen!
        """
        
        logger.info(f"DAILY SUMMARY: {summary}")
        print(f"\n📧 TAGES-EMAIL:\n{summary}\n")
        return True
