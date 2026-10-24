"""
Telegram-Bot fuer SEDA24 V3.0
Ersetzt Browser-Push fuer Schichtbestaetigungen.

Funktionen:
- /start <Personalnummer> - Registrierung
- Schichtbestaetigung per InlineKeyboard
- Erinnerungen (12h, 24h, 48h Auto-Buchung)
- Monatsbestaetigung
- Admin-Benachrichtigungen
"""
import os
import json
import logging
import asyncio
import threading
from datetime import datetime, timedelta, date, time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from app.db.database import SessionLocal
from app.models.models import Employee, PushNotification, Schedule, AuditLog, User, EmployeeObjectAssignment

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

# Globale Bot-Instanz (wird in start_bot gesetzt)
_bot_instance = None
_bot_loop = None


# ========== HILFSFUNKTIONEN ==========

def get_bot() -> Bot:
    """Bot-Instanz fuer externe Aufrufe (z.B. aus Scheduler)."""
    global _bot_instance
    return _bot_instance


def get_bot_loop():
    """Event-Loop des Bot-Threads fuer asyncio-Aufrufe aus synchronem Code."""
    global _bot_loop
    return _bot_loop


async def send_message_async(chat_id: int, text: str,
                              reply_markup=None, parse_mode='HTML'):
    """Nachricht senden (async)."""
    bot = get_bot()
    if not bot:
        logger.error("Telegram-Bot nicht initialisiert")
        return None
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=reply_markup, parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Telegram-Fehler an {chat_id}: {e}")
        return None


def send_message_sync(chat_id: int, text: str,
                      reply_markup=None, parse_mode='HTML'):
    """Nachricht senden (synchron, fuer Aufrufe aus Scheduler)."""
    loop = get_bot_loop()
    if not loop:
        logger.error("Bot-Event-Loop nicht verfuegbar")
        return None
    future = asyncio.run_coroutine_threadsafe(
        send_message_async(chat_id, text, reply_markup, parse_mode),
        loop
    )
    try:
        return future.result(timeout=10)
    except Exception as e:
        logger.error(f"Sync-Send fehlgeschlagen: {e}")
        return None


def notify_admin(text: str, reply_markup=None):
    """Admin per Telegram benachrichtigen."""
    if not ADMIN_CHAT_ID:
        logger.warning("TELEGRAM_ADMIN_CHAT_ID nicht gesetzt")
        return
    try:
        admin_id = int(ADMIN_CHAT_ID)
        send_message_sync(admin_id, text, reply_markup)
    except ValueError:
        logger.error(f"Ungueltige TELEGRAM_ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")


# ========== COMMAND HANDLERS ==========

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start D0001 - Registrierung per Personalnummer.
    Speichert telegram_chat_id in employees.
    """
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "Willkommen bei SEDA24!\n\n"
            "Bitte registriere dich mit deiner Personalnummer:\n"
            "/start D0001\n\n"
            "(Ersetze D0001 durch deine Personalnummer)"
        )
        return

    personal_nr = context.args[0].strip().upper()

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(
            Employee.personal_nr == personal_nr,
            Employee.is_active == True,
        ).first()

        if not employee:
            await update.message.reply_text(
                f"Personalnummer {personal_nr} nicht gefunden.\n"
                "Bitte pruefe die Nummer und versuche es erneut."
            )
            return

        # Chat-ID speichern (als String, da varchar-Spalte)
        employee.telegram_chat_id = str(chat_id)
        from app.services.booking_service import log_audit
        log_audit(db, None, employee.id, 'telegram_registration',
            'employee', employee.id,
            details=f"Telegram registriert: {personal_nr} -> chat_id {chat_id}")
        db.commit()

        await update.message.reply_text(
            f"Willkommen bei SEDA24! \U0001f44b\n\n"
            f"Hallo {employee.first_name}, du bist jetzt verbunden ({personal_nr}).\n\n"
            f"So funktioniert es:\n"
            f"\u2705 Nach jeder Schicht bekommst du hier eine Nachricht\n"
            f"\u2705 Ein Tipp auf 'Ja' und deine Stunden sind gebucht\n"
            f"\u2705 Das war's - einfacher geht's nicht!\n\n"
            f"Bei Fragen wende dich an die Verwaltung."
        )
        logger.info(f"Telegram registriert: {personal_nr} -> chat_id {chat_id}")

    except Exception as e:
        logger.error(f"Fehler bei /start: {e}")
        await update.message.reply_text("Fehler bei der Registrierung. Bitte spaeter erneut versuchen.")
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status - Zeigt offene Bestaetigungen."""
    chat_id = update.effective_chat.id

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(
            Employee.telegram_chat_id == str(chat_id),
        ).first()

        if not employee:
            await update.message.reply_text(
                "Du bist noch nicht registriert.\n"
                "Nutze /start <Personalnummer>"
            )
            return

        pending = db.query(PushNotification).filter(
            PushNotification.employee_id == employee.id,
            PushNotification.status.in_(['pending_telegram', 'sent']),
            PushNotification.response_status.is_(None),
            PushNotification.notification_type == 'shift_confirm',
        ).all()

        if not pending:
            await update.message.reply_text(
                f"Hallo {employee.first_name}! \u2705\n"
                "Keine offenen Bestaetigungen."
            )
        else:
            text = f"Hallo {employee.first_name}!\n\n"
            text += f"\u26a0\ufe0f {len(pending)} offene Bestaetigung(en):\n\n"
            for n in pending:
                sched = db.query(Schedule).get(n.schedule_id) if n.schedule_id else None
                if sched and sched.object:
                    text += (f"\u2022 {sched.object.name}: "
                            f"{sched.start_time.strftime('%H:%M')}-{sched.end_time.strftime('%H:%M')} "
                            f"am {sched.date.strftime('%d.%m.')}\n")
            await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Fehler bei /status: {e}")
        await update.message.reply_text("Fehler beim Laden. Bitte spaeter erneut versuchen.")
    finally:
        db.close()


# ========== URLAUBSANTRAG PER TELEGRAM ==========

# Dict um zu speichern welche Chat-IDs gerade im Urlaubs-Flow sind
_vacation_pending = {}

async def cmd_urlaub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/urlaub - Urlaubsantrag starten."""
    chat_id = update.effective_chat.id
    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(Employee.telegram_chat_id == str(chat_id)).first()
        if not employee:
            await update.message.reply_text("Du bist noch nicht registriert. Nutze /start <Personalnummer>")
            return

        from app.models.models import VacationEntitlement
        current_year = datetime.now().year
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == employee.id,
            VacationEntitlement.year == current_year,
        ).first()
        remaining = entitlement.days_remaining if entitlement else 30

        _vacation_pending[chat_id] = {'employee_id': employee.id}

        await update.message.reply_text(
            f"\U0001f3d6\ufe0f <b>Urlaubsantrag</b>\n\n"
            f"Hallo {employee.first_name}!\n"
            f"Resturlaub: <b>{remaining:.0f} Tage</b>\n\n"
            f"Bitte schreibe den Zeitraum, z.B.:\n"
            f"<code>15.03. bis 19.03.</code>\n"
            f"oder: <code>15.03.-19.03.</code>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Urlaub-Cmd Fehler: {e}")
        await update.message.reply_text("Fehler. Bitte spaeter erneut versuchen.")
    finally:
        db.close()


async def handle_vacation_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet Datumseingabe fuer Urlaubsantrag."""
    chat_id = update.effective_chat.id

    if chat_id not in _vacation_pending:
        return  # Kein aktiver Urlaubs-Flow

    text = update.message.text.strip()
    import re

    # Verschiedene Formate erkennen: "15.03. bis 19.03.", "15.03.-19.03.", "15.3. - 19.3."
    pattern = r'(\d{1,2})\.(\d{1,2})\.?\s*[-–bis]+\s*(\d{1,2})\.(\d{1,2})\.?'
    match = re.search(pattern, text)

    if not match:
        await update.message.reply_text(
            "Format nicht erkannt. Bitte so schreiben:\n<code>15.03. bis 19.03.</code>",
            parse_mode='HTML'
        )
        return

    current_year = datetime.now().year
    try:
        start_day, start_month = int(match.group(1)), int(match.group(2))
        end_day, end_month = int(match.group(3)), int(match.group(4))
        start = date(current_year, start_month, start_day)
        end = date(current_year, end_month, end_day)
    except ValueError:
        await update.message.reply_text("Ungueltige Datumsangabe. Bitte pruefen.")
        return

    if end < start:
        # Evtl. Jahreswechsel
        end = date(current_year + 1, end_month, end_day)

    employee_id = _vacation_pending[chat_id]['employee_id']
    db = SessionLocal()
    try:
        from app.api.v1.endpoints.vacation import _count_working_days
        from app.models.models import VacationEntitlement

        working_days = _count_working_days(db, employee_id, start, end)

        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == employee_id,
            VacationEntitlement.year == start.year,
        ).first()
        remaining = entitlement.days_remaining if entitlement else 30
        remaining_after = remaining - working_days

        start_str = start.strftime("%d.%m.")
        end_str = end.strftime("%d.%m.%Y")

        _vacation_pending[chat_id]['start_date'] = start.isoformat()
        _vacation_pending[chat_id]['end_date'] = end.isoformat()
        _vacation_pending[chat_id]['working_days'] = working_days

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Absenden", callback_data=f"vac_send:{chat_id}"),
                InlineKeyboardButton("\u274c Abbrechen", callback_data=f"vac_cancel:{chat_id}"),
            ]
        ])

        await update.message.reply_text(
            f"\U0001f4c5 <b>Urlaubsantrag</b>\n\n"
            f"\U0001f4c5 {start_str} - {end_str}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n"
            f"\U0001f4b0 Resturlaub danach: {remaining_after:.0f} Tage\n\n"
            f"Antrag absenden?",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Vacation-Dates Fehler: {e}")
        await update.message.reply_text("Fehler bei der Berechnung.")
    finally:
        db.close()


# ========== SCHICHTBESTAETIGUNG SENDEN ==========

def send_shift_confirmation_telegram(notification_id: int):
    """
    Sendet Schichtbestaetigung per Telegram.
    Wird vom Scheduler aufgerufen wenn eine PushNotification erstellt wurde.
    """
    db = SessionLocal()
    try:
        notification = db.query(PushNotification).get(notification_id)
        if not notification:
            logger.warning(f"send_shift_confirmation_telegram: Notification {notification_id} nicht gefunden")
            return

        employee = db.query(Employee).get(notification.employee_id)
        if not employee or not employee.telegram_chat_id:
            logger.info(f"send_shift_confirmation_telegram: Employee {notification.employee_id} - Kein Telegram registriert")
            return

        schedule = db.query(Schedule).get(notification.schedule_id) if notification.schedule_id else None
        if not schedule:
            logger.warning(f"send_shift_confirmation_telegram: Schedule nicht gefunden fuer Notification {notification_id}")
            return

        # Keine Schichtbestaetigung fuer Objekte mit aktiver C-Zuweisung:
        # Dort wird gestempelt, nicht bestaetigt. Spiegelbildlich zur Sperre im
        # Antwort-Handler (_handle_confirm) und im Reminder-Job, die ebenfalls allein
        # auf die C-Zuweisung pruefen. Der Scheduler unterdrueckt das i.d.R. schon
        # vorher - dies ist die zweite Absicherung direkt am Versandweg.
        c_assignment = db.query(EmployeeObjectAssignment).filter(
            EmployeeObjectAssignment.employee_id == notification.employee_id,
            EmployeeObjectAssignment.object_id == schedule.object_id,
            EmployeeObjectAssignment.tracking_category == 'C',
            EmployeeObjectAssignment.is_active == True,
        ).first()
        if c_assignment:
            logger.info(f"send_shift_confirmation_telegram: C-Zuweisung Objekt {schedule.object_id}, "
                       f"keine shift_confirm-Abfrage ({employee.first_name} {employee.last_name})")
            notification.status = 'skipped_cat_c'
            db.commit()
            return

        emp_name = f"{employee.first_name} {employee.last_name}"
        obj_name = schedule.object.name if schedule.object else "Unbekannt"
        start_str = schedule.start_time.strftime("%H:%M") if schedule.start_time else ""
        end_str = schedule.end_time.strftime("%H:%M") if schedule.end_time else ""
        hours = schedule.planned_hours or 0
        date_str = schedule.date.strftime("%d.%m.%Y") if schedule.date else ""

        text = (
            f"\U0001f3e2 {obj_name}\n"
            f"{date_str} | {start_str}-{end_str}\n"
            f"Warst du da?"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Ja, ich war anwesend", callback_data=f"confirm:{notification.id}")],
            [InlineKeyboardButton("\u274c Nein, ich war nicht da", callback_data=f"decline:{notification.id}")],
        ])

        logger.info(f"TELEGRAM SENDE Erstanfrage: {emp_name} ({employee.personal_nr}), "
                    f"{obj_name}, {date_str} {start_str}-{end_str}, Notification {notification.id}")

        result = send_message_sync(employee.telegram_chat_id, text, keyboard)

        if result:
            notification.status = 'sent'
            notification.sent_at = datetime.now()
            notification.channel = 'telegram'
            db.commit()
            logger.info(f"TELEGRAM GESENDET Erstanfrage: {emp_name} -> Notification {notification.id} erfolgreich")
        else:
            logger.warning(f"TELEGRAM FEHLER Erstanfrage: {emp_name} -> Notification {notification.id} fehlgeschlagen")

    except Exception as e:
        logger.error(f"Fehler in send_shift_confirmation_telegram: {e}", exc_info=True)
    finally:
        db.close()


# ========== CALLBACK HANDLERS ==========

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet InlineKeyboard-Klicks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("confirm:"):
        await _handle_confirm(query, data, chat_id)
    elif data.startswith("decline:"):
        await _handle_decline(query, data, chat_id)
    elif data.startswith("reason:"):
        await _handle_decline_reason(query, data, chat_id)
    elif data.startswith("month_confirm:"):
        await _handle_month_confirm(query, data, chat_id)
    elif data.startswith("month_journal:"):
        await _handle_month_journal(query, data, chat_id)
    elif data.startswith("month_dispute:"):
        await _handle_month_dispute(query, data, chat_id)
    elif data.startswith("swa:"):
        await _handle_swap_approve(query, data, chat_id)
    elif data.startswith("swr:"):
        await _handle_swap_reject(query, data, chat_id)
    elif data.startswith("scr_done:"):
        await _handle_scr_done(query, data, chat_id)
    elif data.startswith("scr_note:"):
        await _handle_scr_noted(query, data, chat_id)
    elif data.startswith("vac_ok:"):
        await _handle_vacation_approve(query, data, chat_id)
    elif data.startswith("vac_no:"):
        await _handle_vacation_reject(query, data, chat_id)
    elif data.startswith("vac_send:"):
        await _handle_vacation_send(query, data, chat_id)
    elif data.startswith("vac_cancel:"):
        await _handle_vacation_cancel(query, data, chat_id)
    elif data.startswith("sick_today:"):
        await _handle_sick_today(query, data, chat_id)
    elif data.startswith("sick_multi:"):
        await _handle_sick_multi(query, data, chat_id)


async def _handle_vacation_approve(query, data, chat_id):
    """Admin genehmigt Urlaubsantrag per Telegram."""
    req_id = int(data.split(":")[1])
    db = SessionLocal()
    try:
        from app.models.models import VacationRequest, VacationEntitlement
        from app.api.v1.endpoints.vacation import _create_vacation_schedules
        req = db.query(VacationRequest).get(req_id)
        if not req:
            await query.edit_message_text("\u26a0\ufe0f Antrag nicht gefunden.")
            return
        if req.status != 'pending':
            await query.edit_message_text("\u26a0\ufe0f Antrag wurde bereits bearbeitet.")
            return

        req.status = 'approved'
        req.decided_at = datetime.now()

        employee = db.query(Employee).get(req.employee_id)

        # Schedule-Einträge erstellen
        _create_vacation_schedules(db, req, employee)

        # VacationEntitlement updaten
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == req.employee_id,
            VacationEntitlement.year == req.start_date.year,
        ).first()
        if entitlement:
            entitlement.days_taken = (entitlement.days_taken or 0) + req.working_days
            entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken

        from app.services.booking_service import log_audit
        log_audit(db, None, req.employee_id, 'vacation_request_approved',
            'vacation_request', req.id,
            details=f"Urlaub genehmigt per Telegram: {req.start_date} bis {req.end_date}")

        db.commit()

        # MA benachrichtigen
        if employee and employee.telegram_chat_id:
            start_str = req.start_date.strftime("%d.%m.")
            end_str = req.end_date.strftime("%d.%m.%Y")
            send_message_sync(
                employee.telegram_chat_id,
                f"\U0001f3d6\ufe0f Dein Urlaub vom {start_str} bis {end_str} wurde genehmigt! "
                f"Schoenen Urlaub!",
            )

        old_text = query.message.text or ''
        await query.edit_message_text(
            old_text + "\n\n\u2705 <b>GENEHMIGT</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Vacation-Approve Fehler: {e}")
        await query.edit_message_text("\u26a0\ufe0f Fehler bei der Genehmigung.")
    finally:
        db.close()


async def _handle_vacation_reject(query, data, chat_id):
    """Admin lehnt Urlaubsantrag ab."""
    req_id = int(data.split(":")[1])
    db = SessionLocal()
    try:
        from app.models.models import VacationRequest
        req = db.query(VacationRequest).get(req_id)
        if not req:
            await query.edit_message_text("\u26a0\ufe0f Antrag nicht gefunden.")
            return
        if req.status != 'pending':
            await query.edit_message_text("\u26a0\ufe0f Antrag wurde bereits bearbeitet.")
            return

        req.status = 'rejected'
        req.decided_at = datetime.now()

        from app.services.booking_service import log_audit
        log_audit(db, None, req.employee_id, 'vacation_request_rejected',
            'vacation_request', req.id,
            details=f"Urlaub abgelehnt per Telegram: {req.start_date} bis {req.end_date}")

        db.commit()

        employee = db.query(Employee).get(req.employee_id)
        if employee and employee.telegram_chat_id:
            start_str = req.start_date.strftime("%d.%m.")
            end_str = req.end_date.strftime("%d.%m.%Y")
            send_message_sync(
                employee.telegram_chat_id,
                f"\u274c Dein Urlaubsantrag vom {start_str} bis {end_str} wurde leider abgelehnt. "
                f"Bitte sprich mit der Verwaltung.",
            )

        old_text = query.message.text or ''
        await query.edit_message_text(
            old_text + "\n\n\u274c <b>ABGELEHNT</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Vacation-Reject Fehler: {e}")
        await query.edit_message_text("\u26a0\ufe0f Fehler bei der Ablehnung.")
    finally:
        db.close()


async def _handle_vacation_send(query, data, chat_id):
    """MA bestaetigt Urlaubsantrag per Telegram."""
    sender_chat_id = int(data.split(":")[1])
    if sender_chat_id != chat_id:
        return

    pending = _vacation_pending.pop(chat_id, None)
    if not pending:
        await query.edit_message_text("\u26a0\ufe0f Kein offener Urlaubsantrag gefunden.")
        return

    db = SessionLocal()
    try:
        from app.models.models import VacationRequest, VacationEntitlement
        from app.api.v1.endpoints.vacation import _count_working_days

        employee = db.query(Employee).get(pending['employee_id'])
        start = date.fromisoformat(pending['start_date'])
        end = date.fromisoformat(pending['end_date'])
        working_days = pending['working_days']

        # Resturlaub pruefen
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == employee.id,
            VacationEntitlement.year == start.year,
        ).first()
        remaining = entitlement.days_remaining if entitlement else 30

        exceeds = working_days > remaining

        # Antrag erstellen (auch wenn Restanspruch ueberschritten - Admin entscheidet)
        req = VacationRequest(
            employee_id=employee.id,
            start_date=start,
            end_date=end,
            working_days=working_days,
            status='pending',
        )
        db.add(req)
        db.flush()

        # Admin benachrichtigen
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        emp_name = f"{employee.first_name} {employee.last_name}"
        start_str = start.strftime("%d.%m.%Y")
        end_str = end.strftime("%d.%m.%Y")
        remaining_after = remaining - working_days

        warn_line = f"\n\u26a0\ufe0f <b>Uebersteigt Restanspruch!</b> (verfuegbar: {remaining:.0f})\n" if exceeds else ""
        admin_msg = (
            f"\U0001f3d6\ufe0f <b>URLAUBSANTRAG</b>\n\n"
            f"\U0001f464 {emp_name} ({employee.personal_nr})\n"
            f"\U0001f4c5 {start_str} - {end_str}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n"
            f"\U0001f4b0 Resturlaub danach: {remaining_after:.0f} Tage\n"
            f"{warn_line}"
        )
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Genehmigen", callback_data=f"vac_ok:{req.id}"),
                InlineKeyboardButton("\u274c Ablehnen", callback_data=f"vac_no:{req.id}"),
            ]
        ])
        notify_admin(admin_msg, reply_markup=admin_keyboard)

        from app.services.booking_service import log_audit
        log_audit(db, None, employee.id, 'vacation_request_created',
            'vacation_request', req.id,
            details=f"Urlaubsantrag per Telegram: {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}, {working_days:.0f} Tage")

        db.commit()

        warn_hint = "\n\u26a0\ufe0f Hinweis: uebersteigt deinen Restanspruch." if exceeds else ""
        await query.edit_message_text(
            f"\u2705 <b>Urlaubsantrag gesendet!</b>\n\n"
            f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n\n"
            f"Du bekommst Bescheid sobald der Antrag bearbeitet wurde.{warn_hint}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Vacation-Send Fehler: {e}")
        await query.edit_message_text("\u26a0\ufe0f Fehler beim Absenden.")
    finally:
        db.close()


async def _handle_vacation_cancel(query, data, chat_id):
    """MA bricht Urlaubsantrag ab."""
    sender_chat_id = int(data.split(":")[1])
    if sender_chat_id != chat_id:
        return

    _vacation_pending.pop(chat_id, None)
    await query.edit_message_text(
        "\u274c Urlaubsantrag abgebrochen.\n"
        "Du kannst jederzeit mit /urlaub einen neuen starten."
    )


async def _handle_scr_done(query, data, chat_id):
    """Admin: Vertretung eingetragen."""
    scr_id = int(data.split(":")[1])
    db = SessionLocal()
    try:
        from app.models.models import ShiftChangeRequest
        scr = db.query(ShiftChangeRequest).get(scr_id)
        if scr:
            scr.status = 'resolved'
            scr.admin_response = 'Vertretung eingetragen'
            from datetime import datetime
            scr.processed_at = datetime.now()
            db.commit()
            old_text = query.message.text or query.message.caption or ''
            await query.edit_message_text(
                old_text + "\n\n\u2705 <b>Vertretung eingetragen</b>",
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("\u26a0\ufe0f Anfrage nicht gefunden.")
    except Exception as e:
        logger.error(f"SCR-Done Fehler: {e}")
        await query.edit_message_text("\u26a0\ufe0f Fehler bei der Verarbeitung.")
    finally:
        db.close()


async def _handle_scr_noted(query, data, chat_id):
    """Admin: Notiert."""
    scr_id = int(data.split(":")[1])
    db = SessionLocal()
    try:
        from app.models.models import ShiftChangeRequest
        scr = db.query(ShiftChangeRequest).get(scr_id)
        if scr:
            scr.status = 'noted'
            scr.admin_response = 'Notiert'
            from datetime import datetime
            scr.processed_at = datetime.now()
            db.commit()
            old_text = query.message.text or query.message.caption or ''
            await query.edit_message_text(
                old_text + "\n\n\U0001f4cb <b>Notiert</b>",
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("\u26a0\ufe0f Anfrage nicht gefunden.")
    except Exception as e:
        logger.error(f"SCR-Noted Fehler: {e}")
        await query.edit_message_text("\u26a0\ufe0f Fehler bei der Verarbeitung.")
    finally:
        db.close()


async def _handle_confirm(query, data, chat_id):
    """Bestaetigung: Ja, war anwesend."""
    notification_id = int(data.split(":")[1])

    db = SessionLocal()
    result = None
    try:
        # C-Zuweisung pruefen: Keine Buchung per Telegram fuer C-Objekte
        notification = db.query(PushNotification).get(notification_id)
        if notification and notification.schedule_id:
            sched = db.query(Schedule).get(notification.schedule_id)
            if sched:
                c_check = db.query(EmployeeObjectAssignment).filter(
                    EmployeeObjectAssignment.employee_id == notification.employee_id,
                    EmployeeObjectAssignment.object_id == sched.object_id,
                    EmployeeObjectAssignment.tracking_category == 'C',
                    EmployeeObjectAssignment.is_active == True,
                ).first()
                if c_check:
                    db.close()
                    await query.edit_message_text(
                        "\u2139\ufe0f Fuer dieses Objekt bitte in der App stempeln.",
                        parse_mode='HTML'
                    )
                    return

        from app.services.booking_service import BookingService
        svc = BookingService(db)
        result = svc.process_push_response(notification_id, 'confirmed')
    except Exception as e:
        logger.error(f"Buchungs-Fehler: {e}")
        try:
            await query.edit_message_text(
                "\u26a0\ufe0f Fehler bei der Buchung. Bitte in der App bestaetigen.",
                parse_mode='HTML'
            )
        except Exception:
            pass
        return
    finally:
        db.close()

    # Telegram-Antwort separat: wenn hier ein Fehler auftritt,
    # ist die Buchung bereits gespeichert
    try:
        if result.get("status") == "booked":
            hours = result.get("hours", "?")
            obj_name = result.get("object_name", "?")
            date_str = result.get("date", "?")
            start_time = result.get("start_time", "?")
            end_time = result.get("end_time", "?")
            brutto = result.get("brutto", 0)
            brutto_str = f"{brutto:.2f}".replace(".", ",")
            await query.edit_message_text(
                f"\u2705 <b>Gebucht!</b>\n\n"
                f"\U0001f4c5 {date_str}\n"
                f"\U0001f3e2 {obj_name}\n"
                f"\u23f0 {start_time} - {end_time} ({hours}h)\n"
                f"\U0001f4b0 {brutto_str} \u20ac",
                parse_mode='HTML'
            )
        elif result.get("status") == "already_booked":
            await query.edit_message_text(
                "\u2139\ufe0f Diese Schicht wurde bereits gebucht.",
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                f"\u26a0\ufe0f Fehler: {result.get('message', 'Unbekannt')}",
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Telegram-Antwort-Fehler (Buchung war erfolgreich): {e}")
        if result and result.get("status") == "booked":
            try:
                await query.edit_message_text(
                    "\u2705 Buchung gespeichert!",
                    parse_mode='HTML'
                )
            except Exception:
                pass


async def _handle_decline(query, data, chat_id):
    """Nein geklickt - Gruende anzeigen."""
    notification_id = int(data.split(":")[1])

    # Schicht-Details laden fuer Anzeige
    db = SessionLocal()
    try:
        notif = db.query(PushNotification).get(notification_id)
        schedule = db.query(Schedule).get(notif.schedule_id) if notif and notif.schedule_id else None
        obj_name = schedule.object.name if schedule and schedule.object else "?"
        date_str = schedule.date.strftime("%d.%m.%Y") if schedule and schedule.date else "?"
        start_str = schedule.start_time.strftime("%H:%M") if schedule and schedule.start_time else "?"
        end_str = schedule.end_time.strftime("%H:%M") if schedule and schedule.end_time else "?"
    except Exception:
        obj_name = date_str = start_str = end_str = "?"
    finally:
        db.close()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f912 Krank", callback_data=f"reason:krank:{notification_id}")],
        [InlineKeyboardButton("\U0001f3e0 War nicht da", callback_data=f"reason:privat:{notification_id}")],
        [InlineKeyboardButton("\u23f0 Andere Zeiten", callback_data=f"reason:andere_zeiten:{notification_id}")],
    ])

    await query.edit_message_text(
        f"\U0001f4cb <b>Warum warst du nicht da?</b>\n\n"
        f"\U0001f3e2 {obj_name}\n"
        f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n\n"
        f"Bitte waehle einen Grund:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


async def _handle_decline_reason(query, data, chat_id):
    """Abwesenheitsgrund verarbeiten."""
    parts = data.split(":")
    reason_type = parts[1]
    notification_id = int(parts[2])

    db = SessionLocal()
    try:
        notification = db.query(PushNotification).get(notification_id)
        if not notification:
            await query.edit_message_text("\u26a0\ufe0f Benachrichtigung nicht gefunden.")
            return

        employee = db.query(Employee).get(notification.employee_id)
        schedule = db.query(Schedule).get(notification.schedule_id) if notification.schedule_id else None
        obj_name = schedule.object.name if schedule and schedule.object else "?"
        date_str = schedule.date.strftime("%d.%m.%Y") if schedule and schedule.date else "?"

        if reason_type == 'krank':
            from app.services.booking_service import BookingService
            svc = BookingService(db)
            svc.process_push_response(notification_id, 'not_present', {
                'reason': 'krank', 'absence_type': 'krank'
            })
            await query.edit_message_text(
                "\U0001f912 <b>Krankmeldung erfasst</b>\n\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                "Admin wird informiert. Gute Besserung!",
                parse_mode='HTML'
            )
            # Admin benachrichtigen
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"
            notify_admin(
                f"\U0001f912 <b>Krankmeldung</b>\n\n"
                f"Mitarbeiter: {emp_name}\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}"
            )

        elif reason_type == 'privat':
            from app.services.booking_service import BookingService
            svc = BookingService(db)
            svc.process_push_response(notification_id, 'not_present', {
                'reason': 'privat', 'absence_type': 'privat'
            })
            await query.edit_message_text(
                "\U0001f3e0 <b>Abwesenheit notiert</b>\n\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                "Admin wird informiert.",
                parse_mode='HTML'
            )
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"
            notify_admin(
                f"\U0001f3e0 <b>Abwesenheit (privat)</b>\n\n"
                f"Mitarbeiter: {emp_name}\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}"
            )

        elif reason_type == 'andere_zeiten':
            # Nur Status setzen, Admin muss handeln
            notification.response_status = 'correction'
            notification.response_data = json.dumps({"type": "andere_zeiten"})
            notification.responded_at = datetime.now()
            notification.status = 'responded'
            db.commit()

            await query.edit_message_text(
                "\u23f0 <b>Korrekturanfrage gesendet</b>\n\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                "Admin wird dich kontaktieren.",
                parse_mode='HTML'
            )
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"
            notify_admin(
                f"\u23f0 <b>Korrekturanfrage: Andere Zeiten</b>\n\n"
                f"Mitarbeiter: {emp_name}\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                f"Bitte Zeiten klaeren."
            )

        elif reason_type == 'mit_kollege':
            notification.response_status = 'correction'
            notification.response_data = json.dumps({"type": "mit_kollege"})
            notification.responded_at = datetime.now()
            notification.status = 'responded'
            db.commit()

            await query.edit_message_text(
                "\U0001f465 <b>Hinweis an Admin gesendet</b>\n\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                "Admin wird die Stunden aufteilen.",
                parse_mode='HTML'
            )
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"
            notify_admin(
                f"\U0001f465 <b>Stunden teilen: Mit Kollege</b>\n\n"
                f"Mitarbeiter: {emp_name}\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {date_str}\n\n"
                f"Bitte Stunden 50/50 aufteilen."
            )

    except Exception as e:
        logger.error(f"Decline-Reason Fehler: {e}")
        await query.edit_message_text(
            "\u26a0\ufe0f Fehler. Bitte in der App bearbeiten.",
            parse_mode='HTML'
        )
    finally:
        db.close()


async def _handle_swap_approve(query, data, chat_id):
    """Admin genehmigt Tauschanfrage."""
    request_id = int(data.split(":")[1])

    # Sofort Admin-Nachricht aktualisieren (schnelle Reaktion)
    original_text = query.message.text or ""
    await query.edit_message_text(
        original_text + "\n\n\u2705 GENEHMIGT",
        parse_mode=None
    )

    db = SessionLocal()
    try:
        from app.models.models import ShiftChangeRequest, Schedule, Object
        sr = db.query(ShiftChangeRequest).get(request_id)
        if not sr:
            return

        sr.status = 'approved'
        sr.processed_at = datetime.now()
        db.commit()

        # MA per Telegram benachrichtigen (async = schnell)
        employee = db.query(Employee).get(sr.employee_id)
        schedule = db.query(Schedule).get(sr.schedule_id) if sr.schedule_id else None
        obj_name = "?"
        date_str = "?"
        if schedule:
            obj = db.query(Object).get(schedule.object_id)
            obj_name = obj.name if obj else "?"
            date_str = schedule.date.strftime("%d.%m.") if schedule.date else "?"

        if employee and employee.telegram_chat_id:
            await send_message_async(
                employee.telegram_chat_id,
                f"\u2705 Deine Tauschanfrage fuer {date_str} bei {obj_name} wurde genehmigt!"
            )
    except Exception as e:
        logger.error(f"Swap-Approve Fehler: {e}")
    finally:
        db.close()


async def _handle_swap_reject(query, data, chat_id):
    """Admin lehnt Tauschanfrage ab."""
    request_id = int(data.split(":")[1])

    # Sofort Admin-Nachricht aktualisieren (schnelle Reaktion)
    original_text = query.message.text or ""
    await query.edit_message_text(
        original_text + "\n\n\u274c ABGELEHNT",
        parse_mode=None
    )

    db = SessionLocal()
    try:
        from app.models.models import ShiftChangeRequest, Schedule, Object
        sr = db.query(ShiftChangeRequest).get(request_id)
        if not sr:
            return

        sr.status = 'rejected'
        sr.processed_at = datetime.now()
        db.commit()

        # MA per Telegram benachrichtigen
        employee = db.query(Employee).get(sr.employee_id)
        schedule = db.query(Schedule).get(sr.schedule_id) if sr.schedule_id else None
        obj_name = "?"
        date_str = "?"
        if schedule:
            obj = db.query(Object).get(schedule.object_id)
            obj_name = obj.name if obj else "?"
            date_str = schedule.date.strftime("%d.%m.") if schedule.date else "?"

        if employee and employee.telegram_chat_id:
            await send_message_async(
                employee.telegram_chat_id,
                f"\u274c Deine Tauschanfrage fuer {date_str} bei {obj_name} wurde abgelehnt."
            )
    except Exception as e:
        logger.error(f"Swap-Reject Fehler: {e}")
    finally:
        db.close()


# ========== ERINNERUNGEN ==========

def send_telegram_reminders():
    """
    Wird vom Scheduler aufgerufen (alle 30 Min).
    Prueft auf Erinnerungen (12h, 24h, 48h).
    Bei 48h: KEINE Auto-Buchung, nur Admin benachrichtigen.
    Nur im Fenster 09:00-21:00.
    """
    from app.models.models import TimeEntry

    now = datetime.now()
    if now.hour < 9 or now.hour >= 21:
        return

    db = SessionLocal()
    try:
        # Finde alle offenen Telegram-Notifications
        pending = db.query(PushNotification).filter(
            PushNotification.status.in_(['sent', 'pending_telegram']),
            PushNotification.response_status.is_(None),
            PushNotification.notification_type == 'shift_confirm',
        ).all()

        logger.info(f"send_telegram_reminders: {len(pending)} offene Notifications gefunden")

        for notif in pending:
            employee = db.query(Employee).get(notif.employee_id)
            if not employee or not employee.telegram_chat_id:
                continue

            emp_name = f"{employee.first_name} {employee.last_name}"

            # Pruefe ob Schicht schon gebucht wurde (TimeEntry existiert)
            if notif.schedule_id:
                existing_entry = db.query(TimeEntry).filter(
                    TimeEntry.schedule_id == notif.schedule_id,
                ).first()
                if existing_entry:
                    # Schicht wurde bereits gebucht - Notification als responded markieren
                    notif.status = 'responded'
                    notif.response_status = 'confirmed'
                    notif.responded_at = now
                    logger.info(f"send_telegram_reminders: {emp_name} Schedule {notif.schedule_id} "
                               f"- TimeEntry {existing_entry.id} existiert, Notification {notif.id} als erledigt markiert")
                    continue

            sent_at = notif.sent_at or notif.created_at
            if not sent_at:
                continue

            hours_since = (now - sent_at).total_seconds() / 3600
            schedule = db.query(Schedule).get(notif.schedule_id) if notif.schedule_id else None

            # C-Zuweisung pruefen: Keine Erinnerung fuer Objekte mit aktiver C-Zuweisung
            if schedule:
                c_assignment = db.query(EmployeeObjectAssignment).filter(
                    EmployeeObjectAssignment.employee_id == notif.employee_id,
                    EmployeeObjectAssignment.object_id == schedule.object_id,
                    EmployeeObjectAssignment.tracking_category == 'C',
                    EmployeeObjectAssignment.is_active == True,
                ).first()
                if c_assignment:
                    notif.status = 'skipped_cat_c'
                    notif.response_status = 'skipped_cat_c'
                    logger.info(f"send_telegram_reminders: {emp_name} - C-Zuweisung, uebersprungen")
                    continue

            obj_name = schedule.object.name if schedule and schedule.object else "?"
            date_str = schedule.date.strftime("%d.%m.%Y") if schedule and schedule.date else "?"
            start_str = schedule.start_time.strftime("%H:%M") if schedule and schedule.start_time else "?"
            end_str = schedule.end_time.strftime("%H:%M") if schedule and schedule.end_time else "?"

            # 48h: KEINE Auto-Buchung! Nur Admin informieren + Notification auf expired setzen
            if hours_since >= 48:
                logger.info(f"send_telegram_reminders: {emp_name} - 48h abgelaufen, Admin informieren "
                           f"(Notification {notif.id}, Schedule {notif.schedule_id})")
                _notify_admin_48h(db, notif, employee, schedule, obj_name, date_str, start_str, end_str)
                continue

            # 24h: Zweite Erinnerung
            if hours_since >= 24:
                reminder_count = _get_reminder_count(notif)
                if reminder_count < 2:
                    logger.info(f"send_telegram_reminders: ERINNERUNG 2 an {emp_name} "
                               f"({obj_name}, {date_str}, {hours_since:.1f}h seit Versand)")
                    _send_reminder(employee, notif, obj_name, date_str, start_str, end_str, "Letzte Erinnerung", 2)
                continue

            # 12h: Erste Erinnerung
            if hours_since >= 12:
                reminder_count = _get_reminder_count(notif)
                if reminder_count < 1:
                    logger.info(f"send_telegram_reminders: ERINNERUNG 1 an {emp_name} "
                               f"({obj_name}, {date_str}, {hours_since:.1f}h seit Versand)")
                    _send_reminder(employee, notif, obj_name, date_str, start_str, end_str, "Erinnerung", 1)

        db.commit()

    except Exception as e:
        logger.error(f"Fehler in send_telegram_reminders: {e}")
        db.rollback()
    finally:
        db.close()


def _get_reminder_count(notification):
    """Zaehle gesendete Erinnerungen (gespeichert in payload)."""
    try:
        if notification.payload:
            data = json.loads(notification.payload)
            return data.get('reminder_count', 0)
    except (json.JSONDecodeError, AttributeError):
        pass
    return 0


def _send_reminder(employee, notification, obj_name, date_str, start_str, end_str, label, count):
    """Erinnerung per Telegram senden mit Schicht-Details."""
    emp_name = f"{employee.first_name} {employee.last_name}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2705 Ja, ich war anwesend", callback_data=f"confirm:{notification.id}")],
        [InlineKeyboardButton("\u274c Nein, ich war nicht da", callback_data=f"decline:{notification.id}")],
    ])

    text = (
        f"\u26a0\ufe0f <b>{label}</b>\n\n"
        f"\U0001f3e2 {obj_name}\n"
        f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n\n"
        f"Bitte bestaetigen!"
    )

    logger.info(f"TELEGRAM SENDE Erinnerung {count}: {emp_name} ({employee.personal_nr}), "
                f"{obj_name}, {date_str} {start_str}-{end_str}, Notification {notification.id}")

    result = send_message_sync(employee.telegram_chat_id, text, keyboard)
    if result:
        # Reminder-Count in payload speichern
        try:
            payload_data = json.loads(notification.payload) if notification.payload else {}
        except json.JSONDecodeError:
            payload_data = {}
        payload_data['reminder_count'] = count
        notification.payload = json.dumps(payload_data)
        logger.info(f"TELEGRAM GESENDET Erinnerung {count}: {emp_name} -> Notification {notification.id} erfolgreich")
    else:
        logger.warning(f"TELEGRAM FEHLER Erinnerung {count}: {emp_name} -> Notification {notification.id} fehlgeschlagen")


def _notify_admin_48h(db, notification, employee, schedule, obj_name, date_str, start_str, end_str):
    """48h ohne Antwort: KEINE Auto-Buchung! Nur Admin informieren + expired setzen."""
    notification.status = 'expired'
    notification.response_status = 'expired_48h'
    notification.responded_at = datetime.now()

    emp_name = f"{employee.first_name} {employee.last_name}"
    hours = schedule.planned_hours or "?" if schedule else "?"

    # MA informieren: Nicht gebucht, bitte App nutzen
    send_message_sync(
        employee.telegram_chat_id,
        f"\u26a0\ufe0f <b>Keine Bestaetigung erhalten (48h)</b>\n\n"
        f"\U0001f3e2 {obj_name}\n"
        f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n"
        f"\U0001f552 {hours}h\n\n"
        f"Deine Schicht wurde <b>NICHT</b> automatisch gebucht.\n"
        f"Bitte klaere das mit der Verwaltung.",
        parse_mode='HTML'
    )

    # Admin informieren
    notify_admin(
        f"\u26a0\ufe0f <b>48h ohne Antwort</b>\n\n"
        f"\U0001f464 {emp_name} ({employee.personal_nr})\n"
        f"\U0001f3e2 {obj_name}\n"
        f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n"
        f"\U0001f552 {hours}h\n\n"
        f"Mitarbeiter hat 48h nicht bestaetigt.\n"
        f"Schicht wurde NICHT gebucht."
    )

    # Audit-Log
    from app.services.booking_service import log_audit
    log_audit(
        db, None, employee.id, 'expired_48h_no_autobook',
        'push_notification', notification.id,
        details=f"48h abgelaufen ohne Bestaetigung: {obj_name}, {date_str}"
    )

    logger.info(f"48h expired (kein Auto-Book): Employee {employee.id}, Notification {notification.id}")


# ========== MONATSBESTAETIGUNG ==========

def send_monthly_confirmation(employee_id: int, year: int, month: int,
                               total_hours: float, total_km: float,
                               notification_id: int = None,
                               shift_count: int = 0, total_amount: float = 0):
    """Monatsbestaetigung per Telegram senden mit Details."""
    db = SessionLocal()
    try:
        employee = db.query(Employee).get(employee_id)
        if not employee or not employee.telegram_chat_id:
            return

        MONATSNAMEN = [
            "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"
        ]
        monat = MONATSNAMEN[month] if 1 <= month <= 12 else str(month)

        # Minijob -> Netto, sonst Brutto
        is_minijob = getattr(employee, 'employment_type', '') in ('minijob',)
        betrag_label = "Netto" if is_minijob else "Brutto"

        amount_str = f"{total_amount:.2f}".replace(".", ",")
        text = (
            f"\U0001f4ca <b>Monatsabschluss {monat} {year}</b>\n\n"
            f"Bitte bestaetigt eure Buchungen.\n"
            f"Ihr habt 24 Stunden Zeit.\n\n"
            f"\U0001f4cb {shift_count} Schichten\n"
            f"\U0001f552 {total_hours:.1f} Stunden\n"
            f"\U0001f4b0 {amount_str} \u20ac ({betrag_label})\n"
        )
        if total_km > 0:
            text += f"\U0001f697 {total_km:.1f} km\n"
        text += (
            f"\n"
            f"Sind diese Angaben korrekt?"
        )

        cb_id = notification_id or 0
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "\u2705 Alles korrekt",
                    callback_data=f"month_confirm:{year}:{month}:{cb_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "\U0001f4cb Erst im Journal pruefen",
                    callback_data=f"month_journal:{year}:{month}:{cb_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "\u274c Korrektur noetig",
                    callback_data=f"month_dispute:{year}:{month}:{cb_id}"
                ),
            ]
        ])

        send_message_sync(employee.telegram_chat_id, text, keyboard)
        logger.info(f"Monatsbestaetigung gesendet an {employee.first_name}: {monat} {year}, "
                    f"{shift_count} Schichten, {total_hours:.1f}h, {amount_str}EUR, {betrag_label}")

    except Exception as e:
        logger.error(f"Fehler in send_monthly_confirmation: {e}")
    finally:
        db.close()


async def _handle_month_confirm(query, data, chat_id):
    """Monatsbestaetigung: Alles korrekt."""
    parts = data.split(":")
    year = int(parts[1])
    month = int(parts[2])

    MONATSNAMEN = [
        "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    monat = MONATSNAMEN[month] if 1 <= month <= 12 else str(month)

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(
            Employee.telegram_chat_id == str(chat_id),
        ).first()

        if not employee:
            logger.error(f"Month-Confirm: Kein Employee fuer chat_id={chat_id}")
            await query.edit_message_text(
                f"\u26a0\ufe0f Mitarbeiter nicht gefunden. Bitte in der App bestaetigen.",
                parse_mode='HTML'
            )
            return

        from app.models.models import MonthlyConfirmation
        confirmation = db.query(MonthlyConfirmation).filter(
            MonthlyConfirmation.employee_id == employee.id,
            MonthlyConfirmation.year == year,
            MonthlyConfirmation.month == month,
        ).first()

        if confirmation and confirmation.status == 'confirmed':
            logger.info(f"Month-Confirm: {employee.first_name} {employee.last_name} - bereits bestaetigt")
            await query.edit_message_text(
                f"\u2705 <b>{monat} war bereits bestaetigt!</b>",
                parse_mode='HTML'
            )
            return

        if confirmation:
            confirmation.status = 'confirmed'
            confirmation.confirmed_at = datetime.now()
            confirmation.confirmed_by = 'employee'
        else:
            confirmation = MonthlyConfirmation(
                employee_id=employee.id,
                year=year,
                month=month,
                status='confirmed',
                confirmed_at=datetime.now(),
                confirmed_by='employee',
            )
            db.add(confirmation)

        db.commit()
        logger.info(f"Month-Confirm: {employee.first_name} {employee.last_name} hat {monat} {year} bestaetigt")

        await query.edit_message_text(
            f"\u2705 <b>Danke, {monat} ist abgeschlossen!</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Month-Confirm Fehler fuer chat_id={chat_id}: {e}", exc_info=True)
        try:
            await query.edit_message_text("\u26a0\ufe0f Fehler. Bitte in der App bestaetigen.")
        except Exception:
            pass
    finally:
        db.close()


async def _handle_month_journal(query, data, chat_id):
    """Monatsbestaetigung: Erst im Journal pruefen. Buttons bleiben aktiv."""
    # Neue separate Nachricht senden - Original mit Buttons bleibt stehen
    try:
        await query.message.chat.send_message(
            text=(
                "\U0001f4cb <b>Journal pruefen</b>\n\n"
                "Oeffne die App und pruefe deine Buchungen:\n"
                "\U0001f449 <a href=\"https://app.seda.de\">https://app.seda.de</a>\n\n"
                "Komm danach hierher zurueck und bestaetige mit \u2705 oder \u274c."
            ),
            parse_mode='HTML',
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Month-Journal Fehler: {e}")


async def _handle_month_dispute(query, data, chat_id):
    """Monatsbestaetigung: Korrektur noetig - fragt nach Freitext-Grund."""
    parts = data.split(":")
    year = int(parts[1])
    month = int(parts[2])

    MONATSNAMEN = [
        "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    monat = MONATSNAMEN[month] if 1 <= month <= 12 else str(month)

    # Pending-State setzen: warte auf Freitext-Beschreibung
    _dispute_pending[chat_id] = {
        'year': year,
        'month': month,
        'monat': monat,
    }

    await query.edit_message_text(
        f"\u274c <b>Korrektur fuer {monat} {year}</b>\n\n"
        f"Was stimmt nicht? Bitte beschreibe kurz:",
        parse_mode='HTML'
    )


# ========== MONATS-KORREKTUR PENDING ==========

_dispute_pending = {}  # chat_id -> {'year': ..., 'month': ..., 'monat': ...}


async def _handle_dispute_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet den Freitext-Grund fuer Monatskorrektur."""
    chat_id = update.effective_chat.id
    pending = _dispute_pending.get(chat_id)
    if not pending:
        return

    reason = (update.message.text or '').strip()
    if not reason:
        await update.message.reply_text("Bitte beschreibe kurz was nicht stimmt.")
        return

    year = pending['year']
    month = pending['month']
    monat = pending['monat']

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(
            Employee.telegram_chat_id == str(chat_id),
        ).first()

        if employee:
            from app.models.models import MonthlyConfirmation
            confirmation = db.query(MonthlyConfirmation).filter(
                MonthlyConfirmation.employee_id == employee.id,
                MonthlyConfirmation.year == year,
                MonthlyConfirmation.month == month,
            ).first()

            if confirmation:
                confirmation.status = 'disputed'
                confirmation.dispute_reason = reason
            else:
                confirmation = MonthlyConfirmation(
                    employee_id=employee.id,
                    year=year,
                    month=month,
                    status='disputed',
                    dispute_reason=reason,
                )
                db.add(confirmation)

            db.commit()

            emp_name = f"{employee.first_name} {employee.last_name}"
            notify_admin(
                f"\u274c <b>Monatskorrektur angefragt</b>\n\n"
                f"Mitarbeiter: {emp_name}\n"
                f"Monat: {monat} {year}\n"
                f"Grund: {reason}\n\n"
                f"Bitte Buchungen pruefen und erneut senden."
            )

            await update.message.reply_text(
                f"\u2705 Danke, die Verwaltung wurde informiert.\n"
                f"Dein Hinweis: \"{reason}\"\n\n"
                f"Du bekommst eine neue Bestaetigung sobald alles korrigiert ist.",
                parse_mode='HTML' if '<' in reason else None,
            )
            logger.info(f"Monatskorrektur von {emp_name} fuer {monat} {year}: {reason}")

    except Exception as e:
        logger.error(f"Dispute-Text Fehler: {e}")
        await update.message.reply_text("\u26a0\ufe0f Fehler. Bitte Admin kontaktieren.")
    finally:
        db.close()
        _dispute_pending.pop(chat_id, None)


# ========== DATUM-TEXT-ROUTER ==========

async def _handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routet alle Freitext-Eingaben an den richtigen Handler."""
    chat_id = update.effective_chat.id

    # Monats-Korrektur hat hoechste Prioritaet (beliebiger Text)
    if chat_id in _dispute_pending:
        await _handle_dispute_text(update, context)
        return

    # Nachricht-Pending (beliebiger Text)
    if chat_id in _nachricht_pending and _nachricht_pending[chat_id].get('awaiting_text'):
        await _handle_nachricht_text(update, context)
        return

    # Ab hier nur weiter wenn Text ein Datum enthaelt
    import re
    if not re.search(r'\d{1,2}\.\d{1,2}', update.message.text or ''):
        return

    # Krankmeldung Enddatum
    if chat_id in _sick_pending and _sick_pending[chat_id].get('awaiting_end_date'):
        await handle_sick_end_date(update, context)
        return

    # Urlaubsantrag
    if chat_id in _vacation_pending:
        await handle_vacation_dates(update, context)
        return

    # Keine aktive Session - ignorieren


async def _handle_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy-Router - delegiert an _handle_all_text."""
    await _handle_all_text(update, context)


# ========== KRANKMELDUNG PER TELEGRAM ==========

_sick_pending = {}  # chat_id -> {'employee_id': ..., 'awaiting_photo': bool}

async def cmd_krank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/krank - Krankmeldung starten."""
    chat_id = update.effective_chat.id
    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(Employee.telegram_chat_id == str(chat_id)).first()
        if not employee:
            await update.message.reply_text("Du bist noch nicht registriert. Nutze /start <Personalnummer>")
            return

        today = date.today()
        _sick_pending[chat_id] = {
            'employee_id': employee.id,
            'start_date': today.isoformat(),
            'awaiting_photo': False,
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Nur heute", callback_data=f"sick_today:{chat_id}")],
            [InlineKeyboardButton("Mehrere Tage", callback_data=f"sick_multi:{chat_id}")],
        ])

        await update.message.reply_text(
            f"\U0001f912 <b>Krankmeldung</b>\n\n"
            f"Hallo {employee.first_name}, gute Besserung!\n\n"
            f"Wie lange bist du krank?",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Krank-Cmd Fehler: {e}")
        await update.message.reply_text("Fehler. Bitte spaeter erneut versuchen.")
    finally:
        db.close()


async def handle_sick_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AU-Foto empfangen."""
    chat_id = update.effective_chat.id
    pending = _sick_pending.get(chat_id)
    if not pending or not pending.get('awaiting_photo'):
        return

    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        return

    db = SessionLocal()
    try:
        import os
        # Foto herunterladen
        file = await photo.get_file()
        upload_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'uploads', 'au_photos'
        )
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, f"au_{pending['employee_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await file.download_to_drive(file_path)

        # SickNote erstellen
        from app.models.models import SickNote
        from app.api.v1.endpoints.vacation import _count_working_days

        start = date.fromisoformat(pending['start_date'])
        end = date.fromisoformat(pending.get('end_date', pending['start_date']))
        working_days = _count_working_days(db, pending['employee_id'], start, end)

        note = SickNote(
            employee_id=pending['employee_id'],
            start_date=start,
            end_date=end,
            working_days=working_days,
            au_photo_path=file_path,
            status='pending',
            notes='Per Telegram gemeldet (mit AU-Foto)',
        )
        db.add(note)
        db.flush()

        employee = db.query(Employee).get(pending['employee_id'])
        emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"

        # Admin benachrichtigen
        notify_admin(
            f"\U0001f912 <b>KRANKMELDUNG mit AU-Foto</b>\n\n"
            f"\U0001f464 {emp_name} ({employee.personal_nr if employee else '?'})\n"
            f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n"
            f"\U0001f4f8 AU-Foto empfangen\n\n"
            f"Bitte in der App bestaetigen."
        )

        from app.services.booking_service import log_audit
        log_audit(db, None, pending['employee_id'], 'sick_note_telegram',
            'sick_note', note.id,
            details=f"Krankmeldung per Telegram (mit AU-Foto): {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}, {working_days:.0f} Tage")

        db.commit()
        _sick_pending.pop(chat_id, None)

        await update.message.reply_text(
            f"\u2705 <b>Krankmeldung eingereicht!</b>\n\n"
            f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n"
            f"\U0001f4f8 AU-Foto gespeichert\n\n"
            f"Admin wird informiert. Gute Besserung!",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Sick-Photo Fehler: {e}")
        await update.message.reply_text("\u26a0\ufe0f Fehler beim Speichern.")
    finally:
        db.close()


async def _handle_sick_today(query, data, chat_id):
    """Krankmeldung nur fuer heute."""
    sender_id = int(data.split(":")[1])
    if sender_id != chat_id:
        return

    pending = _sick_pending.get(chat_id)
    if not pending:
        await query.edit_message_text("\u26a0\ufe0f Kein offener Vorgang.")
        return

    today = date.today()
    pending['start_date'] = today.isoformat()
    pending['end_date'] = today.isoformat()
    pending['awaiting_photo'] = True

    await query.edit_message_text(
        f"\U0001f912 <b>Krankmeldung fuer heute ({today.strftime('%d.%m.%Y')})</b>\n\n"
        f"Hast du ein AU-Foto? Dann schicke es jetzt als Bild.\n"
        f"Oder tippe /skip um ohne Foto fortzufahren.",
        parse_mode='HTML'
    )


async def _handle_sick_multi(query, data, chat_id):
    """Krankmeldung fuer mehrere Tage - Enddatum abfragen."""
    sender_id = int(data.split(":")[1])
    if sender_id != chat_id:
        return

    pending = _sick_pending.get(chat_id)
    if not pending:
        await query.edit_message_text("\u26a0\ufe0f Kein offener Vorgang.")
        return

    pending['awaiting_end_date'] = True

    await query.edit_message_text(
        f"\U0001f912 <b>Krankmeldung - Enddatum</b>\n\n"
        f"Bis wann bist du krank?\n"
        f"Schreibe das Enddatum, z.B.:\n"
        f"<code>28.02.</code> oder <code>28.02.2026</code>",
        parse_mode='HTML'
    )


async def handle_sick_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enddatum fuer Krankmeldung verarbeiten."""
    chat_id = update.effective_chat.id
    pending = _sick_pending.get(chat_id)
    if not pending or not pending.get('awaiting_end_date'):
        return

    text = update.message.text.strip()
    import re
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?', text)
    if not match:
        await update.message.reply_text("Format nicht erkannt. Bitte z.B. <code>28.02.</code>", parse_mode='HTML')
        return

    current_year = datetime.now().year
    try:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else current_year
        if year < 100:
            year += 2000
        end = date(year, month, day)
    except ValueError:
        await update.message.reply_text("Ungueltiges Datum.")
        return

    pending['end_date'] = end.isoformat()
    pending['awaiting_end_date'] = False
    pending['awaiting_photo'] = True

    start = date.fromisoformat(pending['start_date'])
    await update.message.reply_text(
        f"\U0001f912 <b>Krankmeldung</b>\n\n"
        f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n\n"
        f"Hast du ein AU-Foto? Dann schicke es jetzt als Bild.\n"
        f"Oder tippe /skip um ohne Foto fortzufahren.",
        parse_mode='HTML'
    )


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/skip - Krankmeldung ohne AU-Foto abschicken."""
    chat_id = update.effective_chat.id
    pending = _sick_pending.get(chat_id)
    if not pending or not pending.get('awaiting_photo'):
        await update.message.reply_text("Kein offener Vorgang.")
        return

    db = SessionLocal()
    try:
        from app.models.models import SickNote
        from app.api.v1.endpoints.vacation import _count_working_days

        start = date.fromisoformat(pending['start_date'])
        end = date.fromisoformat(pending.get('end_date', pending['start_date']))
        working_days = _count_working_days(db, pending['employee_id'], start, end)

        note = SickNote(
            employee_id=pending['employee_id'],
            start_date=start,
            end_date=end,
            working_days=working_days,
            status='pending',
            notes='Per Telegram gemeldet (ohne AU-Foto)',
        )
        db.add(note)
        db.flush()

        employee = db.query(Employee).get(pending['employee_id'])
        emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"

        notify_admin(
            f"\U0001f912 <b>KRANKMELDUNG</b>\n\n"
            f"\U0001f464 {emp_name} ({employee.personal_nr if employee else '?'})\n"
            f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n"
            f"\U0001f4f8 Kein AU-Foto\n\n"
            f"Bitte in der App bestaetigen."
        )

        from app.services.booking_service import log_audit
        log_audit(db, None, pending['employee_id'], 'sick_note_telegram',
            'sick_note', note.id,
            details=f"Krankmeldung per Telegram (ohne AU-Foto): {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}, {working_days:.0f} Tage")

        db.commit()
        _sick_pending.pop(chat_id, None)

        await update.message.reply_text(
            f"\u2705 <b>Krankmeldung eingereicht!</b>\n\n"
            f"\U0001f4c5 {start.strftime('%d.%m.')} - {end.strftime('%d.%m.%Y')}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n\n"
            f"Admin wird informiert. Gute Besserung!",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Skip-Sick Fehler: {e}")
        await update.message.reply_text("\u26a0\ufe0f Fehler beim Speichern.")
    finally:
        db.close()


# ========== NACHRICHT PER TELEGRAM ==========

_nachricht_pending = {}  # chat_id -> {'employee_id': ..., 'awaiting_text': bool}

async def cmd_nachricht(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/nachricht [Text] - Nachricht an Verwaltung senden."""
    chat_id = update.effective_chat.id
    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(Employee.telegram_chat_id == str(chat_id)).first()
        if not employee:
            await update.message.reply_text(
                "\u26a0\ufe0f Du bist nicht registriert. Nutze /start <Personalnummer>"
            )
            return

        # Pruefen ob Text direkt mitgegeben wurde: /nachricht Mein Text hier
        text = ' '.join(context.args) if context.args else ''

        if text.strip():
            # Direkt speichern
            from app.models.models import Message as MsgModel
            msg = MsgModel(
                sender_employee_id=employee.id,
                category='sonstiges',
                subject='Per Telegram',
                body=text.strip(),
                status='neu',
            )
            db.add(msg)
            db.flush()

            emp_name = f"{employee.first_name} {employee.last_name}"
            notify_admin(
                f"\U0001f4e8 <b>NACHRICHT per Telegram</b>\n\n"
                f"\U0001f464 {emp_name} ({employee.personal_nr})\n"
                f"\U0001f4dd {text.strip()[:300]}"
            )

            db.commit()
            await update.message.reply_text(
                f"\u2705 <b>Nachricht gesendet!</b>\n\n"
                f"\U0001f4dd {text.strip()[:100]}{'...' if len(text.strip()) > 100 else ''}\n\n"
                f"Admin wird benachrichtigt.",
                parse_mode='HTML'
            )
        else:
            # Auf Nachrichtentext warten
            _nachricht_pending[chat_id] = {
                'employee_id': employee.id,
                'awaiting_text': True,
            }
            await update.message.reply_text(
                "\U0001f4dd <b>Nachricht an Verwaltung</b>\n\n"
                "Schreibe jetzt deine Nachricht als Text:",
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Nachricht-Command Fehler: {e}")
        await update.message.reply_text("\u26a0\ufe0f Fehler. Bitte versuche es spaeter.")
    finally:
        db.close()


async def _handle_nachricht_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Freitext-Handler fuer /nachricht Eingaben."""
    chat_id = update.effective_chat.id
    pending = _nachricht_pending.get(chat_id)
    if not pending or not pending.get('awaiting_text'):
        return False

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Bitte schreibe eine Nachricht.")
        return True

    db = SessionLocal()
    try:
        from app.models.models import Message as MsgModel
        employee = db.query(Employee).get(pending['employee_id'])

        msg = MsgModel(
            sender_employee_id=pending['employee_id'],
            category='sonstiges',
            subject='Per Telegram',
            body=text,
            status='neu',
        )
        db.add(msg)
        db.flush()

        emp_name = f"{employee.first_name} {employee.last_name}" if employee else "?"
        notify_admin(
            f"\U0001f4e8 <b>NACHRICHT per Telegram</b>\n\n"
            f"\U0001f464 {emp_name} ({employee.personal_nr if employee else '?'})\n"
            f"\U0001f4dd {text[:300]}"
        )

        db.commit()
        _nachricht_pending.pop(chat_id, None)

        await update.message.reply_text(
            f"\u2705 <b>Nachricht gesendet!</b>\n\n"
            f"\U0001f4dd {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
            f"Admin wird benachrichtigt.",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Nachricht-Text Fehler: {e}")
        await update.message.reply_text("\u26a0\ufe0f Fehler beim Senden.")
    finally:
        db.close()
    return True


# ========== BOT STARTEN ==========

_application = None


async def _run_bot_async():
    """Bot async starten - ohne Signal-Handler (laeuft im Thread)."""
    global _bot_instance, _application

    app = Application.builder().token(BOT_TOKEN).build()
    _application = app

    # Command Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("urlaub", cmd_urlaub))
    app.add_handler(CommandHandler("krank", cmd_krank))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("nachricht", cmd_nachricht))

    # Message Handler: Freitext fuer /nachricht (muss VOR date_text kommen)
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _handle_all_text
    ))

    # Date-Text Handler nicht mehr separat noetig - wird ueber _handle_all_text geroutet

    # Photo Handler (AU-Foto)
    app.add_handler(MessageHandler(filters.PHOTO, handle_sick_photo))

    # Callback Handler (InlineKeyboard-Klicks)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Manuell initialisieren (statt run_polling das Signal-Handler setzt)
    await app.initialize()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    await app.start()

    _bot_instance = app.bot
    logger.info("Telegram-Bot gestartet (Polling ohne Signal-Handler)")

    # Event-Loop am Leben halten bis er gestoppt wird
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Telegram-Bot sauber heruntergefahren")


def _run_bot(loop):
    """Bot im eigenen Event-Loop starten."""
    asyncio.set_event_loop(loop)

    if not BOT_TOKEN or BOT_TOKEN == "HIER_TOKEN_EINFUEGEN":
        logger.warning("TELEGRAM_BOT_TOKEN nicht konfiguriert - Bot wird nicht gestartet")
        return

    try:
        loop.run_until_complete(_run_bot_async())
    except Exception as e:
        logger.error(f"Telegram-Bot Fehler: {e}")


def start_bot():
    """Bot in separatem Thread starten."""
    global _bot_loop

    if not BOT_TOKEN or BOT_TOKEN == "HIER_TOKEN_EINFUEGEN":
        logger.warning("TELEGRAM_BOT_TOKEN nicht konfiguriert - Bot uebersprungen")
        return

    _bot_loop = asyncio.new_event_loop()

    thread = threading.Thread(target=_run_bot, args=(_bot_loop,), daemon=True)
    thread.start()
    logger.info("Telegram-Bot Thread gestartet")


def stop_bot():
    """Bot stoppen."""
    global _bot_loop
    if _bot_loop and _bot_loop.is_running():
        # Alle Tasks im Loop abbrechen
        for task in asyncio.all_tasks(_bot_loop):
            _bot_loop.call_soon_threadsafe(task.cancel)
        _bot_loop.call_soon_threadsafe(_bot_loop.stop)
    logger.info("Telegram-Bot gestoppt")
