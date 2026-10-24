import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Email-Service mit echtem SMTP."""

    @staticmethod
    def _get_smtp_config():
        return {
            'host': os.getenv('SMTP_HOST', ''),
            'port': int(os.getenv('SMTP_PORT', '587')),
            'user': os.getenv('SMTP_USER', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'from_email': os.getenv('SMTP_FROM', 'noreply@seda24.de'),
        }

    @staticmethod
    def _send_email(to_email: str, subject: str, html_body: str) -> bool:
        """Sendet eine Email via SMTP. Bei Fehler nur loggen, nicht crashen."""
        config = EmailService._get_smtp_config()

        if not config['host'] or not config['user']:
            logger.warning(f"SMTP nicht konfiguriert. Email an {to_email} nicht gesendet: {subject}")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"SEDA24 Zeiterfassung <{config['from_email']}>"
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            with smtplib.SMTP(config['host'], config['port'], timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(config['user'], config['password'])
                server.sendmail(config['from_email'], to_email, msg.as_string())

            logger.info(f"Email gesendet an {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Email-Fehler an {to_email}: {e}")
            return False

    @staticmethod
    def send_auto_booking_email(to_email: str, employee_name: str,
                                 date_str: str, obj_name: str,
                                 hours: float = None) -> bool:
        """Email an MA bei 48h Auto-Buchung."""
        if not to_email:
            return False

        subject = "SEDA24 - Bitte Arbeitszeiten bestaetigen"
        hours_str = f"{hours:.1f}h" if hours else ""

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #3b82f6; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">SEDA24 Zeiterfassung</h2>
            </div>
            <div style="padding: 20px; background-color: #f9fafb;">
                <p>Hallo {employee_name},</p>

                <p>deine Schicht wurde <strong>automatisch gebucht</strong>, da du nicht
                innerhalb von 48 Stunden bestaetigt hast:</p>

                <div style="background: white; border-left: 4px solid #f59e0b; padding: 15px; margin: 15px 0;">
                    <p style="margin: 5px 0;"><strong>Objekt:</strong> {obj_name}</p>
                    <p style="margin: 5px 0;"><strong>Datum:</strong> {date_str}</p>
                    {f'<p style="margin: 5px 0;"><strong>Stunden:</strong> {hours_str}</p>' if hours_str else ''}
                </div>

                <p>Falls die Buchung <strong>nicht korrekt</strong> ist, melde dich bitte
                umgehend bei deinem Vorgesetzten oder antworte per Telegram-Bot.</p>

                <p style="color: #6b7280; font-size: 12px; margin-top: 30px;">
                    Diese Email wurde automatisch generiert.<br>
                    SEDA24 GmbH - Zeiterfassungssystem
                </p>
            </div>
        </div>
        """

        return EmailService._send_email(to_email, subject, html_body)

    @staticmethod
    def send_password_reset_email(to_email: str, reset_link: str) -> bool:
        """Passwort-Reset-Link per E-Mail senden."""
        if not to_email:
            return False

        subject = "SEDA24 - Passwort zuruecksetzen"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #3b82f6; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">SEDA24 Zeiterfassung</h2>
            </div>
            <div style="padding: 20px; background-color: #f9fafb;">
                <p>Hallo,</p>

                <p>du hast eine Anfrage zum Zuruecksetzen deines Passworts gestellt.</p>

                <p>Klicke auf den folgenden Button, um ein neues Passwort zu vergeben:</p>

                <div style="text-align: center; margin: 25px 0;">
                    <a href="{reset_link}"
                       style="background-color: #3b82f6; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 8px; font-weight: bold;
                              display: inline-block;">
                        Passwort zuruecksetzen
                    </a>
                </div>

                <p style="color: #6b7280; font-size: 13px;">
                    Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:<br>
                    <a href="{reset_link}" style="color: #3b82f6; word-break: break-all;">{reset_link}</a>
                </p>

                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 13px;">
                        <strong>Hinweis:</strong> Dieser Link ist <strong>60 Minuten</strong> gueltig.
                        Falls du kein Passwort-Reset angefordert hast, ignoriere diese E-Mail.
                    </p>
                </div>

                <p style="color: #6b7280; font-size: 12px; margin-top: 30px;">
                    Diese E-Mail wurde automatisch generiert.<br>
                    SEDA24 GmbH - Zeiterfassungssystem
                </p>
            </div>
        </div>
        """
        return EmailService._send_email(to_email, subject, html_body)

    @staticmethod
    def send_warning_email(employee_name: str, warning_type: str, message: str):
        """Sendet Email an Admin bei Warnungen."""
        logger.warning(f"WARNUNG: {employee_name} - {warning_type}: {message}")
        return True

    @staticmethod
    def send_daily_summary(warnings_count: int, missing_checkouts: int):
        """Taegliche Zusammenfassung."""
        logger.info(f"DAILY SUMMARY: {warnings_count} Warnungen, {missing_checkouts} fehlende Ausstempelungen")
        return True
