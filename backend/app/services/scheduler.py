"""
APScheduler-Integration fuer SEDA24 V3.0
Verwaltet alle periodischen Jobs: Push-Trigger, Erinnerungen, KM-Bereinigung, Kat-A-Buchung.
"""
import logging
from datetime import datetime, timedelta, date, time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.database import SessionLocal
from app.models.models import Schedule, Employee, PushNotification, TimeEntry, EmployeeObjectAssignment, Object
from app.services import push_service

logger = logging.getLogger(__name__)

# --- TEMPORAERE TEST-AUSNAHME (2026-10-21) ---------------------------------
# auto_book_category_a ueberspringt diese Employee-IDs (Manuell-Stempel-Test).
# Zum Entfernen: Liste leeren -> AUTO_BOOK_SKIP_EMPLOYEE_IDS = set()
# Enthaelt: 4 = D0002 Ruzica Sertic
AUTO_BOOK_SKIP_EMPLOYEE_IDS = {4}
# ---------------------------------------------------------------------------

scheduler = BackgroundScheduler()


def init_scheduler():
    """APScheduler initialisieren und Jobs registrieren."""
    # Job 1: Schichtende pruefen (jede Minute)
    scheduler.add_job(
        check_shift_endings,
        IntervalTrigger(minutes=1),
        id='check_shift_endings',
        replace_existing=True,
        max_instances=1,
    )

    # Job 2: Erinnerungen senden (alle 2 Stunden, 09:00-21:00)
    scheduler.add_job(
        send_reminders,
        CronTrigger(hour='9,11,13,15,17,19,21', minute=0),
        id='send_reminders',
        replace_existing=True,
    )

    # Job 3: Ablauf pruefen (stuendlich)
    scheduler.add_job(
        expire_notifications,
        IntervalTrigger(hours=1),
        id='expire_notifications',
        replace_existing=True,
    )

    # Job 4: KM Tagesbereinigung (23:55)
    scheduler.add_job(
        cleanup_km_daily,
        CronTrigger(hour=23, minute=55),
        id='cleanup_km_daily',
        replace_existing=True,
    )

    # Job 5: Kategorie A Auto-Booking (alle 5 Min)
    scheduler.add_job(
        auto_book_category_a,
        IntervalTrigger(minutes=5),
        id='auto_book_cat_a',
        replace_existing=True,
        max_instances=1,
    )

    # Job 6: Telegram-Erinnerungen (alle 30 Min, 09:00-21:00)
    scheduler.add_job(
        telegram_reminders,
        IntervalTrigger(minutes=30),
        id='telegram_reminders',
        replace_existing=True,
        max_instances=1,
    )

    # Job 7: Monatsbestaetigung automatisch (taeglich 09:00 - Morgen nach letzter Schicht)
    scheduler.add_job(
        auto_monthly_confirmation,
        CronTrigger(hour=9, minute=0),
        id='auto_monthly_confirmation',
        replace_existing=True,
        max_instances=1,
    )

    # Job 8: Auto-Fill Monatsumsaetze (1. jeden Monats, 06:00)
    scheduler.add_job(
        auto_fill_monthly_revenues,
        CronTrigger(day=1, hour=6, minute=0),
        id='auto_fill_monthly_revenues',
        replace_existing=True,
        max_instances=1,
    )

    # Job 9: Urlaubssaetze wöchentlich aktualisieren (Sonntag 02:00)
    scheduler.add_job(
        update_vacation_rates_weekly,
        CronTrigger(day_of_week='sun', hour=2, minute=0),
        id='update_vacation_rates_weekly',
        replace_existing=True,
        max_instances=1,
    )

    # Job 10: Offene Genehmigungen - Telegram an Admin (taeglich 20:00)
    scheduler.add_job(
        notify_pending_approvals,
        CronTrigger(hour=20, minute=0),
        id='notify_pending_approvals',
        replace_existing=True,
        max_instances=1,
    )

    # Job 11: Ueberfaellige offene Stempel pruefen (alle 15 Min)
    scheduler.add_job(
        check_overdue_entries,
        IntervalTrigger(minutes=15),
        id='check_overdue_entries',
        replace_existing=True,
        max_instances=1,
    )

    # Job 12: Fehlende Stempelungen pruefen (alle 15 Min)
    scheduler.add_job(
        check_missing_stamps,
        IntervalTrigger(minutes=15),
        id='check_missing_stamps',
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("APScheduler gestartet mit 12 Jobs")


def shutdown_scheduler():
    """APScheduler sauber herunterfahren."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler heruntergefahren")


def check_shift_endings():
    """
    Laeuft jede Minute. Prueft welche Kat-B-Schichten vor 5-35 Min
    geendet haben und sendet Push-Notifications (einmalig pro Schicht).
    5 Min Verzoegerung damit der MA erst einpacken kann.
    """
    db = SessionLocal()
    try:
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)

        # Zeitfenster: Schichten die vor 5-35 Minuten geendet haben
        # Berechne exaktes Zeitfenster als volle Datetimes
        window_start_dt = now - timedelta(minutes=35)
        window_end_dt = now - timedelta(minutes=5)

        from sqlalchemy import or_
        base_filters = [
            Employee.tracking_mode == 'B',
            Employee.is_active == True,
            Schedule.status.in_(['normal', 'vertretung']),
        ]

        # Kandidaten suchen: heute und gestern (fuer Mitternacht-Schichten)
        schedules = db.query(Schedule).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            *base_filters,
            Schedule.date.in_([today, yesterday]),
            Schedule.end_time != None,
            Schedule.start_time != None,
        ).all()

        # Filtern: Nur Schichten deren tatsaechliches Ende im Zeitfenster liegt
        matched = []
        for sched in schedules:
            # Tatsaechliches Ende berechnen (Mitternacht-Ueberschreitung beruecksichtigen)
            sched_end_dt = datetime.combine(sched.date, sched.end_time)
            if sched.end_time < sched.start_time:
                # Schicht geht ueber Mitternacht (z.B. 22:00-02:00)
                sched_end_dt += timedelta(days=1)

            if window_start_dt <= sched_end_dt <= window_end_dt:
                matched.append(sched)

        if matched:
            logger.info(f"check_shift_endings: {len(matched)} beendete Kat-B-Schichten gefunden "
                       f"(Fenster {window_start_dt.strftime('%H:%M')}-{window_end_dt.strftime('%H:%M')})")

        for sched in matched:
            employee = db.query(Employee).get(sched.employee_id)
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else f"ID {sched.employee_id}"

            # Pruefe ob Push schon gesendet wurde (egal welcher Status)
            existing = db.query(PushNotification).filter(
                PushNotification.schedule_id == sched.id,
                PushNotification.notification_type == 'shift_confirm',
            ).first()

            if existing:
                logger.debug(f"check_shift_endings: {emp_name} Schedule {sched.id} - Push existiert bereits (ID {existing.id})")
                continue

            # Pruefe ob diese spezifische Schicht schon gebucht wurde (exakt per schedule_id)
            existing_entry = db.query(TimeEntry).filter(
                TimeEntry.schedule_id == sched.id,
            ).first()

            if existing_entry:
                logger.info(f"check_shift_endings: {emp_name} Schedule {sched.id} - Schon gebucht (Entry {existing_entry.id}), kein Push")
                continue

            # Keine Schichtbestaetigung fuer Objekte mit aktiver C-Zuweisung:
            # Wer dort stempeln soll, bekommt keine "Warst du da?"-Abfrage - sonst
            # koennte eine Bestaetigung entstehen, waehrend parallel ein offline
            # gepufferter Stempel unterwegs ist (Doppelbuchung). Die normale Stempel-
            # Erinnerung (check_missing_stamps) laeuft davon unabhaengig weiter.
            # Spiegelbildlich zur Sperre im Antwort-Handler (_handle_confirm) und im
            # Reminder-Job (send_telegram_reminders), die ebenfalls allein auf die
            # C-Zuweisung pruefen.
            c_assignment = db.query(EmployeeObjectAssignment).filter(
                EmployeeObjectAssignment.employee_id == sched.employee_id,
                EmployeeObjectAssignment.object_id == sched.object_id,
                EmployeeObjectAssignment.tracking_category == 'C',
                EmployeeObjectAssignment.is_active == True,
            ).first()
            if c_assignment:
                logger.info(f"check_shift_endings: {emp_name} Schedule {sched.id} - "
                           f"C-Zuweisung Objekt {sched.object_id}, keine shift_confirm-Abfrage")
                continue

            # Notification erstellen (Browser-Push deaktiviert, wird pending_telegram)
            result = push_service.send_shift_confirmation(db, sched.employee_id, sched.id)
            status = result.status if result else 'null'
            logger.info(f"check_shift_endings: PUSH ERSTELLT fuer {emp_name}, "
                       f"Schedule {sched.id} ({sched.date} {sched.start_time}-{sched.end_time}) -> Status: {status}")

            # Telegram-Bestaetigung senden
            if result and result.id:
                try:
                    from app.services.telegram_bot import send_shift_confirmation_telegram
                    send_shift_confirmation_telegram(result.id)
                    logger.info(f"check_shift_endings: Telegram gesendet an {emp_name} (Notification {result.id})")
                except Exception as tg_err:
                    logger.error(f"check_shift_endings: Telegram-Senden fehlgeschlagen fuer {emp_name}: {tg_err}")

    except Exception as e:
        logger.error(f"Fehler in check_shift_endings: {e}", exc_info=True)
    finally:
        db.close()


def send_reminders():
    """Erinnerungen fuer unbearbeitete Pushes senden (09:00-21:00)."""
    db = SessionLocal()
    try:
        push_service.check_and_send_reminders(db)
    except Exception as e:
        logger.error(f"Fehler in send_reminders: {e}")
    finally:
        db.close()


def expire_notifications():
    """24h abgelaufene Pushes als expired markieren."""
    db = SessionLocal()
    try:
        push_service.expire_old_notifications(db)
    except Exception as e:
        logger.error(f"Fehler in expire_notifications: {e}")
    finally:
        db.close()


def cleanup_km_daily():
    """
    23:55 - KM-Tagesbereinigung.
    Nur die laengste Fahrt pro Mitarbeiter/Tag bleibt billable.
    """
    db = SessionLocal()
    try:
        from sqlalchemy import text
        today = date.today()

        # Finde alle MA die heute KM-Eintraege haben
        result = db.execute(text("""
            SELECT DISTINCT employee_id FROM km_daily_entries
            WHERE date = :today
        """), {"today": today})
        employee_ids = [row[0] for row in result]

        for emp_id in employee_ids:
            # Alle Eintraege des Tages
            entries = db.execute(text("""
                SELECT id, distance_km FROM km_daily_entries
                WHERE employee_id = :emp_id AND date = :today
                ORDER BY distance_km DESC
            """), {"emp_id": emp_id, "today": today}).fetchall()

            if len(entries) <= 1:
                continue

            # Nur die laengste bleibt billable
            longest_id = entries[0][0]
            for entry in entries:
                if entry[0] == longest_id:
                    db.execute(text("""
                        UPDATE km_daily_entries
                        SET is_billable = TRUE, is_longest_trip = TRUE
                        WHERE id = :entry_id
                    """), {"entry_id": entry[0]})
                else:
                    db.execute(text("""
                        UPDATE km_daily_entries
                        SET is_billable = FALSE, is_longest_trip = FALSE
                        WHERE id = :entry_id
                    """), {"entry_id": entry[0]})

        db.commit()
        logger.info(f"KM-Tagesbereinigung fuer {len(employee_ids)} Mitarbeiter abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler in cleanup_km_daily: {e}")
        db.rollback()
    finally:
        db.close()


def auto_book_category_a():
    """
    Alle 5 Minuten: Auto-Booking fuer Kategorie-A-Mitarbeiter.
    Erstellt automatisch Buchungen basierend auf dem Dienstplan
    mit zufaelliger Zeitvariation (+-2-3 Min) fuer GDPR.
    """
    import random
    db = SessionLocal()
    try:
        now = datetime.now()
        today = now.date()

        # Finde Kategorie-A Schichten die geendet haben
        schedules = db.query(Schedule).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            Employee.tracking_mode == 'A',
            Employee.is_active == True,
            Schedule.date == today,
            Schedule.status.in_(['normal', 'vertretung']),
        ).all()

        for sched in schedules:
            if sched.employee_id in AUTO_BOOK_SKIP_EMPLOYEE_IDS:
                logger.info(f"auto_book_category_a: Employee {sched.employee_id} per TEST-SKIP-Liste uebersprungen")
                continue
            if not sched.end_time:
                continue

            sched_end = datetime.combine(today, sched.end_time)
            if now < sched_end:
                continue  # Schicht noch nicht vorbei

            # Pruefe ob schon gebucht
            existing = db.query(TimeEntry).filter(
                TimeEntry.employee_id == sched.employee_id,
                TimeEntry.object_id == sched.object_id,
                TimeEntry.check_in >= datetime.combine(today, time(0, 0)),
                TimeEntry.check_in < datetime.combine(today + timedelta(days=1), time(0, 0)),
            ).first()

            if existing:
                continue

            # Randomisierung +-2-3 Min
            start_var = random.randint(-3, 2)
            end_var = random.randint(-2, 3)

            check_in = datetime.combine(today, sched.start_time) + timedelta(minutes=start_var)
            check_out = datetime.combine(today, sched.end_time) + timedelta(minutes=end_var)

            # custom_hourly_rate aus Zuweisung hat Vorrang
            assignment = db.query(EmployeeObjectAssignment).filter(
                EmployeeObjectAssignment.employee_id == sched.employee_id,
                EmployeeObjectAssignment.object_id == sched.object_id,
                EmployeeObjectAssignment.is_active == True
            ).first()
            if assignment and assignment.custom_hourly_rate:
                rate = float(assignment.custom_hourly_rate)
            else:
                rate = sched.employee.hourly_rate or 15.50
            if assignment and assignment.custom_service_type:
                svc = assignment.custom_service_type
            else:
                obj = db.query(Object).filter(Object.id == sched.object_id).first()
                obj_name = (obj.name or "").upper() if obj else ""
                if any(kw in obj_name for kw in ['FENSTER', 'WINDOW']):
                    svc = 'Fensterreinigung'
                elif any(kw in obj_name for kw in ['GRUND', 'BASIC']):
                    svc = 'Grundreinigung'
                else:
                    svc = 'Unterhaltsreinigung'

            entry = TimeEntry(
                employee_id=sched.employee_id,
                object_id=sched.object_id,
                check_in=check_in,
                check_out=check_out,
                billed_hours=sched.planned_hours,
                hourly_rate=rate,
                is_manual_entry=True,
                service_type=svc,
                notes='Automatische Buchung Kategorie A',
            )
            db.add(entry)
            logger.info(f"Kat-A Auto-Booking: Employee {sched.employee_id}, "
                       f"Object {sched.object_id}, {sched.planned_hours}h")

        db.commit()
    except Exception as e:
        logger.error(f"Fehler in auto_book_category_a: {e}")
        db.rollback()
    finally:
        db.close()


def auto_monthly_confirmation():
    """
    Taeglich 09:00: Prueft PRO MITARBEITER:
    1. Hat er diesen Monat Schichten gehabt?
    2. Sind fuer den Rest des Monats KEINE weiteren Schichten geplant?
    3. Hat er noch NICHT bestaetigt?
    Wenn alle drei JA -> Telegram-Monatsbestaetigung senden.
    """
    from calendar import monthrange
    from app.models.models import MonthlyConfirmation, KmDailyEntry
    db = SessionLocal()
    try:
        today = date.today()
        year = today.year
        month = today.month
        _, last_day_num = monthrange(year, month)
        last_day = date(year, month, last_day_num)
        first_day = date(year, month, 1)

        logger.info(f"auto_monthly_confirmation: Pruefe fuer {month}/{year}, heute={today}")

        employees = db.query(Employee).filter(
            Employee.is_active == True,
            Employee.tracking_mode.in_(['B', 'C']),
        ).all()

        sent_count = 0
        skipped_no_shifts = 0
        skipped_future_shifts = 0
        skipped_already = 0

        for emp in employees:
            # Bedingung 3: Schon bestaetigt oder schon gesendet?
            existing_conf = db.query(MonthlyConfirmation).filter(
                MonthlyConfirmation.employee_id == emp.id,
                MonthlyConfirmation.year == year,
                MonthlyConfirmation.month == month,
                MonthlyConfirmation.status.in_(['confirmed', 'disputed']),
            ).first()
            if existing_conf:
                skipped_already += 1
                continue

            # Schon Telegram-Bestaetigung gesendet diesen Monat? (Duplikat-Schutz)
            existing_push = db.query(PushNotification).filter(
                PushNotification.employee_id == emp.id,
                PushNotification.notification_type == 'monthly_confirmation',
                PushNotification.created_at >= datetime.combine(first_day, time(0, 0)),
            ).first()
            if existing_push:
                skipped_already += 1
                continue

            # Bedingung 1: Hat der Admin eine Schicht als "letzte Schicht des Monats" markiert?
            marked_shift = db.query(Schedule).filter(
                Schedule.employee_id == emp.id,
                Schedule.date >= first_day,
                Schedule.date <= last_day,
                Schedule.is_last_shift_of_month == True,
            ).first()

            if not marked_shift:
                # Keine Markierung = kein automatischer Monatsabschluss
                skipped_no_shifts += 1
                continue

            # Bedingung 2: Ist die markierte Schicht abgeschlossen (Datum <= heute)?
            if marked_shift.date > today:
                skipped_future_shifts += 1
                logger.info(f"auto_monthly_confirmation: {emp.first_name} - markierte letzte Schicht ({marked_shift.date}) noch nicht erreicht, warte.")
                continue

            # Bedingung 2b: Wurde die markierte Schicht auch tatsaechlich gebucht?
            booked = db.query(TimeEntry).filter(
                TimeEntry.schedule_id == marked_shift.id,
            ).first()
            if not booked:
                # Auch check per Datum + Employee (falls schedule_id nicht gesetzt)
                from sqlalchemy import func as sqlfunc
                booked = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == emp.id,
                    sqlfunc.date(TimeEntry.check_in) == marked_shift.date,
                    TimeEntry.check_out != None,
                ).first()

            if not booked:
                skipped_future_shifts += 1
                logger.info(f"auto_monthly_confirmation: {emp.first_name} - markierte Schicht ({marked_shift.date}) noch nicht gebucht, warte.")
                continue

            # Alle 3 Bedingungen erfuellt -> Stunden + KM berechnen und senden
            entries = db.query(TimeEntry).filter(
                TimeEntry.employee_id == emp.id,
                TimeEntry.check_in >= datetime.combine(first_day, time(0, 0)),
                TimeEntry.check_in <= datetime.combine(last_day, time(23, 59, 59)),
                TimeEntry.object_id != 999,  # Urlaub ausschliessen
            ).all()
            total_hours = sum(e.billed_hours or 0 for e in entries)
            shift_count = len(entries)
            total_amount = sum((e.billed_hours or 0) * float(e.hourly_rate or 15.0) for e in entries)

            # KM
            km_entries = db.query(KmDailyEntry).filter(
                KmDailyEntry.employee_id == emp.id,
                KmDailyEntry.date >= first_day,
                KmDailyEntry.date <= last_day,
            ).all()
            total_km = sum(e.distance_km or 0 for e in km_entries)

            # Telegram senden
            if emp.telegram_chat_id:
                try:
                    from app.services.telegram_bot import send_monthly_confirmation
                    send_monthly_confirmation(
                        emp.id, year, month,
                        total_hours, total_km,
                        shift_count=shift_count,
                        total_amount=total_amount,
                    )
                    sent_count += 1
                    # sent_at in MonthlyConfirmation setzen
                    conf = db.query(MonthlyConfirmation).filter(
                        MonthlyConfirmation.employee_id == emp.id,
                        MonthlyConfirmation.year == year,
                        MonthlyConfirmation.month == month,
                    ).first()
                    if not conf:
                        conf = MonthlyConfirmation(
                            employee_id=emp.id, year=year, month=month,
                            status='pending', sent_at=datetime.now(),
                        )
                        db.add(conf)
                    else:
                        conf.sent_at = datetime.now()
                    db.commit()
                    logger.info(f"auto_monthly_confirmation: Gesendet an {emp.first_name} {emp.last_name} "
                               f"({shift_count} Schichten, {total_hours:.1f}h, {total_amount:.2f}EUR)")
                except Exception as e:
                    logger.error(f"Monatsbestaetigung Telegram Fehler fuer {emp.id}: {e}")
            else:
                logger.info(f"auto_monthly_confirmation: {emp.first_name} hat kein Telegram, uebersprungen")

        logger.info(f"auto_monthly_confirmation: Ergebnis fuer {month}/{year}: "
                    f"{sent_count} gesendet, {skipped_no_shifts} ohne Schichten, "
                    f"{skipped_future_shifts} noch Schichten offen, {skipped_already} schon bestaetigt")

    except Exception as e:
        logger.error(f"Fehler in auto_monthly_confirmation: {e}", exc_info=True)
    finally:
        db.close()


def auto_fill_monthly_revenues():
    """
    Am 1. jeden Monats: Standard-Umsaetze fuer den Vormonat eintragen,
    falls kein manueller Wert existiert. Gilt fuer Feb-Nov (Monate 2-11).
    Jan + Dez werden manuell eingetragen.
    """
    from app.models.models import Object as Obj, CustomerRevenue
    db = SessionLocal()
    try:
        today = date.today()
        # Vormonat berechnen
        if today.month == 1:
            prev_month = 12
            prev_year = today.year - 1
        else:
            prev_month = today.month - 1
            prev_year = today.year

        # Nur Feb-Nov automatisch fuellen
        if prev_month not in range(2, 12):
            logger.info(f"auto_fill_revenues: Monat {prev_month} nicht im Auto-Bereich (Feb-Nov), uebersprungen")
            return

        objects = db.query(Obj).filter(
            Obj.is_active == True,
            Obj.monthly_amount_netto != None,
            Obj.monthly_amount_netto > 0,
        ).all()

        filled = 0
        skipped = 0
        for obj in objects:
            # Pruefen ob schon ein Eintrag existiert
            existing = db.query(CustomerRevenue).filter(
                CustomerRevenue.object_id == obj.id,
                CustomerRevenue.year == prev_year,
                CustomerRevenue.month == prev_month,
            ).first()

            if existing:
                skipped += 1
                continue

            rev = CustomerRevenue(
                object_id=obj.id,
                customer_id=obj.customer_id,
                year=prev_year,
                month=prev_month,
                revenue=obj.monthly_amount_netto,
                notes='Auto-Eintrag Standard-Umsatz',
            )
            db.add(rev)
            filled += 1

        db.commit()
        logger.info(f"auto_fill_revenues: {prev_month}/{prev_year} - {filled} eingetragen, {skipped} uebersprungen (bereits vorhanden)")

    except Exception as e:
        logger.error(f"Fehler in auto_fill_monthly_revenues: {e}", exc_info=True)
    finally:
        db.close()


def telegram_reminders():
    """
    Alle 30 Min: Telegram-Erinnerungen fuer offene Bestaetigungen.
    Delegiert an telegram_bot.send_telegram_reminders().
    """
    try:
        from app.services.telegram_bot import send_telegram_reminders
        send_telegram_reminders()
    except Exception as e:
        logger.error(f"Fehler in telegram_reminders: {e}")


def update_vacation_rates_weekly():
    """
    Sonntag 02:00: Aktualisiert den Referenz-Urlaubssatz (vacation_rate)
    in vacation_entitlements fuer alle aktiven MAs nach § 11 BUrlG.
    Durchschnittsverdienst pro Arbeitstag der letzten 13 Wochen.

    WICHTIG: Aendert NUR den Referenzwert in vacation_entitlements.
    Bereits gebuchte Urlaubstage (time_entries) bleiben unveraendert.
    """
    from app.models.models import VacationEntitlement
    from sqlalchemy import func as sqlfunc
    db = SessionLocal()
    try:
        today = date.today()
        current_year = today.year
        start_date = today - timedelta(days=91)  # 13 Wochen

        employees = db.query(Employee).filter(
            Employee.is_active == True,
        ).all()

        updated = 0
        skipped = 0

        for emp in employees:
            if emp.personal_nr and emp.personal_nr.startswith('A'):
                continue

            # Arbeitstage der letzten 13 Wochen (ohne Urlaub/Krank)
            entries = db.query(TimeEntry).filter(
                TimeEntry.employee_id == emp.id,
                TimeEntry.object_id != 999,
                sqlfunc.date(TimeEntry.check_in) >= start_date,
                sqlfunc.date(TimeEntry.check_in) < today,
                TimeEntry.check_out != None,
            ).all()

            daily_earnings = {}
            for e in entries:
                day = e.check_in.date()
                earnings = (e.billed_hours or 0) * float(e.hourly_rate or 0)
                daily_earnings[day] = daily_earnings.get(day, 0) + earnings

            worked_days = len(daily_earnings)
            if worked_days == 0:
                skipped += 1
                continue

            total_earnings = sum(daily_earnings.values())
            new_rate = round(total_earnings / worked_days, 2)

            # Entitlement holen oder erstellen
            ent = db.query(VacationEntitlement).filter(
                VacationEntitlement.employee_id == emp.id,
                VacationEntitlement.year == current_year,
            ).first()

            if not ent:
                ent = VacationEntitlement(
                    employee_id=emp.id, year=current_year,
                    days_entitled=0, days_taken=0, days_remaining=0,
                    vacation_rate=new_rate,
                )
                db.add(ent)
            else:
                ent.vacation_rate = new_rate

            updated += 1

        db.commit()
        logger.info(f"update_vacation_rates_weekly: {updated} aktualisiert, {skipped} uebersprungen (keine Daten)")

    except Exception as e:
        logger.error(f"Fehler in update_vacation_rates_weekly: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _vacation_rate_for(db, employee_id, ref_date):
    """§ 11 BUrlG: Ø-Verdienst pro Arbeitstag im 13-Wochen-Fenster
    [ref_date-91d, ref_date). Identische Formel wie update_vacation_rates_weekly."""
    from sqlalchemy import func as sqlfunc
    start_date = ref_date - timedelta(days=91)
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.object_id != 999,
        sqlfunc.date(TimeEntry.check_in) >= start_date,
        sqlfunc.date(TimeEntry.check_in) < ref_date,
        TimeEntry.check_out != None,
    ).all()
    daily = {}
    for e in entries:
        d = e.check_in.date()
        daily[d] = daily.get(d, 0) + (e.billed_hours or 0) * float(e.hourly_rate or 0)
    worked_days = len(daily)
    if worked_days == 0:
        return 0.0
    return round(sum(daily.values()) / worked_days, 2)


def finalize_due_vacation_rates(db=None, commit=True):
    """Bestimmt den Urlaubstagessatz FAELLIGER Urlaubstage (Urlaubsbeginn erreicht), die
    noch den Provisorik-Marker tragen (hourly_rate < 0). § 11 BUrlG: ein Satz je Antrag,
    13-Wochen-Fenster bis zum ERSTEN Urlaubstag des Antrags, ausgewertet erst wenn dieser
    erreicht ist (nicht am Genehmigungstag).

    HARTE GARANTIE: Es werden ausschliesslich Zeilen mit hourly_rate < 0 angefasst.
    Alle bereits bewerteten Urlaubstage (Satz >= 0, inkl. aller Altdaten) bleiben
    unveraendert. Idempotent -> mehrfaches Aufrufen ist gefahrlos.

    Haengt am 15-Min-Job check_overdue_entries (kein eigener APScheduler-Job) und ist
    zusaetzlich mit db=... / commit=False manuell bzw. als Trockenlauf anstossbar.
    """
    import re
    own = db is None
    if own:
        db = SessionLocal()
    try:
        today = date.today()
        offen = db.query(TimeEntry).filter(
            TimeEntry.object_id == 999,
            TimeEntry.service_type == 'Urlaub',
            TimeEntry.hourly_rate < 0,
        ).all()
        # Je Antrag gruppieren (#<id> aus notes; Fallback: eigene Zeile)
        gruppen = {}
        for e in offen:
            m = re.search(r'#(\d+)', e.notes or '')
            key = (e.employee_id, m.group(1) if m else f"row{e.id}")
            gruppen.setdefault(key, []).append(e)
        geaendert = 0
        for (emp_id, _), rows in gruppen.items():
            start = min(r.check_in.date() for r in rows)
            if start > today:
                continue  # Urlaubsbeginn noch nicht erreicht -> warten (richtiger Zeitpunkt)
            rate = _vacation_rate_for(db, emp_id, start)
            if rate <= 0:
                # Fallback: Referenzwert aus vacation_entitlements des Urlaubsjahres
                from app.models.models import VacationEntitlement
                ent = db.query(VacationEntitlement).filter(
                    VacationEntitlement.employee_id == emp_id,
                    VacationEntitlement.year == start.year,
                ).first()
                rate = round(ent.vacation_rate, 2) if ent and ent.vacation_rate and ent.vacation_rate > 0 else 0.0
            if rate <= 0:
                continue  # keine Datenbasis -> Marker bleibt, naechster Lauf versucht erneut
            for r in rows:
                r.hourly_rate = rate
                r.notes = (r.notes or "") + f" | Satz {rate:.2f}EUR am {today.isoformat()} bestimmt"
                geaendert += 1
        if commit:
            db.commit()
        logger.info(f"finalize_due_vacation_rates: {geaendert} faellige Urlaubstage bewertet")
        return geaendert
    except Exception as ex:
        logger.error(f"finalize_due_vacation_rates Fehler: {ex}", exc_info=True)
        if commit:
            db.rollback()
        raise
    finally:
        if own:
            db.close()


def _job_last_run(db, job_name):
    from sqlalchemy import text
    row = db.execute(text("SELECT last_run_at FROM job_runs WHERE job_name = :n"), {"n": job_name}).fetchone()
    return row[0] if row else None


def _mark_job_run(db, job_name, when):
    from sqlalchemy import text
    db.execute(text("""
        INSERT INTO job_runs (job_name, last_run_at) VALUES (:n, :t)
        ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at
    """), {"n": job_name, "t": when})


def run_due_catchup_jobs():
    """Nachhol-Verhalten fuer enge Cron-Jobs (MemoryJobStore verliert sie bei Neustart).
    Haengt am 15-Min-Job check_overdue_entries - KEIN eigener APScheduler-Job.

    Je Job max. 1x pro Periode: laeuft nur, wenn der letzte faellige Cron-Termin vorbei
    ist UND seit diesem Termin noch nicht gelaufen (job_runs.last_run_at). Holt damit einen
    wegen Neustart verpassten Termin nach, ohne je doppelt zu laufen.
    """
    now = datetime.now()
    db = SessionLocal()
    try:
        # --- Wochen-Job: update_vacation_rates_weekly, faellig Sonntag 02:00 ---
        days_since_sun = (now.weekday() - 6) % 7          # Mo=0..So=6
        last_sun = (now - timedelta(days=days_since_sun)).replace(hour=2, minute=0, second=0, microsecond=0)
        if last_sun > now:
            last_sun -= timedelta(days=7)
        lr = _job_last_run(db, 'update_vacation_rates_weekly')
        if lr is None or lr < last_sun:
            logger.info(f"run_due_catchup_jobs: hole update_vacation_rates_weekly nach (faellig seit {last_sun})")
            update_vacation_rates_weekly()                # eigene Session + commit
            _mark_job_run(db, 'update_vacation_rates_weekly', now)
            db.commit()

        # --- Monats-Job: auto_fill_monthly_revenues, faellig 1. des Monats 06:00 ---
        first_this = now.replace(day=1, hour=6, minute=0, second=0, microsecond=0)
        if first_this > now:
            last_first = (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=6, minute=0, second=0, microsecond=0)
        else:
            last_first = first_this
        lr2 = _job_last_run(db, 'auto_fill_monthly_revenues')
        if lr2 is None or lr2 < last_first:
            logger.info(f"run_due_catchup_jobs: hole auto_fill_monthly_revenues nach (faellig seit {last_first})")
            auto_fill_monthly_revenues()
            _mark_job_run(db, 'auto_fill_monthly_revenues', now)
            db.commit()
    except Exception as ex:
        logger.error(f"run_due_catchup_jobs Fehler: {ex}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def notify_pending_approvals():
    """Job 10: Telegram-Benachrichtigung an Admin bei offenen Genehmigungen."""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        count = db.execute(text(
            "SELECT COUNT(*) FROM pending_bookings WHERE status = 'offen'"
        )).scalar()

        if count and count > 0:
            from app.services.telegram_bot import notify_admin
            notify_admin(
                f"Du hast {count} offene Genehmigung{'en' if count > 1 else ''}.\n"
                f"Bitte in der Admin-App unter Mehr > Genehmigungen pruefen."
            )
            logger.info(f"notify_pending_approvals: {count} offene Genehmigungen, Admin benachrichtigt")
        else:
            logger.info("notify_pending_approvals: Keine offenen Genehmigungen")
    except Exception as e:
        logger.error(f"Fehler in notify_pending_approvals: {e}", exc_info=True)
    finally:
        db.close()


def get_scheduled_end_for_entry(employee_id: int, check_in: datetime, db) -> datetime:
    """Ermittelt Schichtende aus Dienstplan. Fallback: check_in + 8h."""
    from app.models.models import Schedule
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.date == check_in.date(),
        Schedule.end_time != None,
    ).first()
    if schedule:
        scheduled_end = datetime.combine(check_in.date(), schedule.end_time)
        if schedule.start_time and schedule.end_time < schedule.start_time:
            scheduled_end += timedelta(days=1)
        return scheduled_end
    return check_in + timedelta(hours=8)


def check_overdue_entries():
    """
    Job 11: Alle 15 Min - Prueft offene Stempel gegen Schichtende.
    60+ Min ueberfaellig → Telegram an Admin (einmalig).
    """
    # Faellige Urlaubstage bewerten (idempotent, eigene Session, nur hourly_rate < 0).
    # Haengt hier, damit KEIN eigener APScheduler-Job noetig ist (MemoryJobStore verliert
    # Jobs bei Neustart). Fehler duerfen die Ueberfaelligkeitspruefung nicht blockieren.
    try:
        finalize_due_vacation_rates()
    except Exception as _e:
        logger.error(f"finalize_due_vacation_rates (Hook) Fehler: {_e}", exc_info=True)

    # Verpasste enge Cron-Jobs nachholen (Wochen-/Monats-Job). Idempotent via job_runs,
    # kein eigener APScheduler-Job. Fehler duerfen die Ueberfaelligkeitspruefung nicht blockieren.
    try:
        run_due_catchup_jobs()
    except Exception as _e:
        logger.error(f"run_due_catchup_jobs (Hook) Fehler: {_e}", exc_info=True)

    db = SessionLocal()
    try:
        now = datetime.now()
        # Alle offenen Eintraege die noch nicht benachrichtigt wurden
        open_entries = db.query(TimeEntry).join(
            Employee, TimeEntry.employee_id == Employee.id
        ).filter(
            TimeEntry.check_out == None,
            TimeEntry.overdue_notified == False,
            Employee.is_active == True,
        ).all()

        notified_count = 0
        for entry in open_entries:
            scheduled_end = get_scheduled_end_for_entry(entry.employee_id, entry.check_in, db)
            overdue_minutes = (now - scheduled_end).total_seconds() / 60

            if overdue_minutes >= 60:
                employee = db.query(Employee).get(entry.employee_id)
                emp_name = f"{employee.first_name} {employee.last_name}" if employee else f"ID {entry.employee_id}"
                personal_nr = employee.personal_nr if employee else "?"

                # --- Admin-Benachrichtigung ---
                admin_msg = (f"⚠️ Ueberfaellig: {emp_name} ({personal_nr}) ist seit "
                             f"{entry.check_in.strftime('%d.%m. %H:%M')} eingestempelt. "
                             f"Schichtende war {scheduled_end.strftime('%H:%M')}. Bitte pruefen.")
                pn_status_admin = 'sent'
                pn_error_admin = None
                try:
                    from app.services.telegram_bot import notify_admin
                    notify_admin(admin_msg)
                    notified_count += 1
                except Exception as tg_err:
                    logger.error(f"check_overdue_entries: Telegram-Fehler fuer {emp_name}: {tg_err}")
                    pn_status_admin = 'failed'
                    pn_error_admin = str(tg_err)[:500]

                pn_admin = PushNotification(
                    employee_id=entry.employee_id,
                    notification_type='overdue_admin',
                    title='Ueberfaellige Stempelung (Admin)',
                    body=admin_msg,
                    channel='telegram',
                    status=pn_status_admin,
                    response_data=pn_error_admin,
                    sent_at=now if pn_status_admin == 'sent' else None,
                )
                db.add(pn_admin)

                # --- MA-Benachrichtigung ---
                ma_msg = (f"Hallo {employee.first_name if employee else ''}, du bist seit "
                          f"{entry.check_in.strftime('%H:%M')} eingestempelt, "
                          f"deine Schicht war bis {scheduled_end.strftime('%H:%M')} geplant. "
                          f"Falls du schon gegangen bist: kurz die App oeffnen, "
                          f"dann wird deine Zeit uebertragen. https://app.seda.de")
                pn_status_ma = 'no_chat_id'
                pn_error_ma = None
                if employee and getattr(employee, 'telegram_chat_id', None):
                    try:
                        from app.services.telegram_bot import send_message_sync
                        send_message_sync(employee.telegram_chat_id, ma_msg)
                        pn_status_ma = 'sent'
                    except Exception as tg_err:
                        pn_status_ma = 'failed'
                        pn_error_ma = str(tg_err)[:500]

                pn_ma = PushNotification(
                    employee_id=entry.employee_id,
                    notification_type='overdue_ma',
                    title='Ueberfaellige Stempelung',
                    body=ma_msg,
                    channel='telegram',
                    status=pn_status_ma,
                    response_data=pn_error_ma,
                    sent_at=now if pn_status_ma == 'sent' else None,
                )
                db.add(pn_ma)

                entry.overdue_notified = True

        if notified_count > 0:
            db.commit()
            logger.info(f"check_overdue_entries: {notified_count} Ueberfaellige gemeldet")
        else:
            db.commit()

    except Exception as e:
        logger.error(f"Fehler in check_overdue_entries: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def check_missing_stamps():
    """
    Job 12: Alle 15 Min - Prueft ob Kat-C-Mitarbeiter laut Dienstplan eingeteilt sind,
    aber noch keine Stempelung vorliegt.
    30 Min nach Schichtbeginn: MA per Telegram benachrichtigen (einmalig).
    60 Min nach Schichtbeginn: Admin per Telegram benachrichtigen (einmalig).
    Nachtruhe: 21:00-06:00.
    """
    from sqlalchemy import text
    db = SessionLocal()
    try:
        now = datetime.now()
        if not (6 <= now.hour < 21):
            return

        today = now.date()
        changed = False

        # Gemeinsame Bedingungen (ohne Zeitfenster und ohne notified-Flag)
        base_sql = """
            FROM schedules s
            JOIN employees e ON e.id = s.employee_id AND e.is_active = TRUE
            JOIN objects o ON o.id = s.object_id
            JOIN employee_object_assignments eoa
                 ON eoa.employee_id = s.employee_id
                 AND eoa.object_id = s.object_id
                 AND eoa.is_active = TRUE
                 AND eoa.tracking_category = 'C'
            WHERE s.date = :today
              AND s.object_id = 20
              AND s.start_time IS NOT NULL
              AND s.status NOT IN ('krankheit', 'urlaub', 'abwesend')
              AND NOT EXISTS (
                  SELECT 1 FROM time_entries te
                  WHERE te.employee_id = s.employee_id
                    AND te.object_id = s.object_id
                    AND DATE(te.check_in) = s.date
              )
              AND NOT EXISTS (
                  SELECT 1 FROM vacation_requests vr
                  WHERE vr.employee_id = s.employee_id
                    AND vr.status = 'approved'
                    AND :today BETWEEN vr.start_date AND vr.end_date
              )
              AND NOT EXISTS (
                  SELECT 1 FROM sick_notes sn
                  WHERE sn.employee_id = s.employee_id
                    AND sn.status = 'confirmed'
                    AND :today BETWEEN sn.start_date AND sn.end_date
              )
        """

        # --- Durchlauf 1: MA-Benachrichtigung (30 Min nach Schichtbeginn) ---
        ma_rows = db.execute(text("""
            SELECT s.id, s.employee_id, s.object_id, s.start_time, s.end_time,
                   e.first_name, e.last_name, e.personal_nr,
                   o.name as object_name, e.telegram_chat_id
        """ + base_sql + """
              AND s.no_stamp_ma_notified = FALSE
              AND (CAST(:today AS TIMESTAMP) + s.start_time + INTERVAL '30 minutes') <= :now_ts
        """), {"today": today, "now_ts": now}).fetchall()

        for row in ma_rows:
            von = row.start_time.strftime('%H:%M') if row.start_time else '?'
            msg_body = (f"Hallo {row.first_name}, laut Plan hast du heute um {von} "
                        f"bei {row.object_name} angefangen - bei uns ist aber noch kein "
                        f"Kommen angekommen. Falls du schon da bist: kurz die App "
                        f"oeffnen und stempeln. https://app.seda.de")
            pn_status = 'no_chat_id'
            pn_error = None
            if getattr(row, 'telegram_chat_id', None):
                try:
                    from app.services.telegram_bot import send_message_sync
                    send_message_sync(row.telegram_chat_id, msg_body)
                    pn_status = 'sent'
                except Exception as tg_err:
                    logger.error(f"check_missing_stamps: MA-Telegram-Fehler: {tg_err}")
                    pn_status = 'failed'
                    pn_error = str(tg_err)[:500]

            pn = PushNotification(
                employee_id=row.employee_id,
                notification_type='missing_stamp_ma',
                title='Fehlende Stempelung',
                body=msg_body,
                channel='telegram',
                status=pn_status,
                response_data=pn_error,
                schedule_id=row.id,
                sent_at=now if pn_status == 'sent' else None,
            )
            db.add(pn)

            db.execute(text("UPDATE schedules SET no_stamp_ma_notified = TRUE WHERE id = :sid"),
                       {"sid": row.id})
            changed = True

        if ma_rows:
            logger.info(f"check_missing_stamps: {len(ma_rows)} MA-Benachrichtigungen gesendet (30 Min)")

        # --- Durchlauf 2: Admin-Benachrichtigung (60 Min nach Schichtbeginn) ---
        admin_rows = db.execute(text("""
            SELECT s.id, s.employee_id, s.object_id, s.start_time, s.end_time,
                   e.first_name, e.last_name, e.personal_nr,
                   o.name as object_name
        """ + base_sql + """
              AND s.no_stamp_notified = FALSE
              AND (CAST(:today AS TIMESTAMP) + s.start_time + INTERVAL '1 hour') <= :now_ts
        """), {"today": today, "now_ts": now}).fetchall()

        for row in admin_rows:
            von = row.start_time.strftime('%H:%M') if row.start_time else '?'
            bis = row.end_time.strftime('%H:%M') if row.end_time else '?'
            msg_body = (f"Fuer {row.first_name} {row.last_name} ({row.personal_nr}) "
                        f"liegt heute noch keine Stempelung vor "
                        f"(geplant {von}-{bis}, {row.object_name}). "
                        f"Moeglicherweise offline gestempelt und noch nicht uebertragen.")
            pn_status = 'sent'
            pn_error = None
            try:
                from app.services.telegram_bot import notify_admin
                notify_admin(msg_body)
            except Exception as tg_err:
                logger.error(f"check_missing_stamps: Admin-Telegram-Fehler: {tg_err}")
                pn_status = 'failed'
                pn_error = str(tg_err)[:500]

            pn = PushNotification(
                employee_id=row.employee_id,
                notification_type='missing_stamp_admin',
                title='Fehlende Stempelung (Admin)',
                body=msg_body,
                channel='telegram',
                status=pn_status,
                response_data=pn_error,
                schedule_id=row.id,
                sent_at=now if pn_status == 'sent' else None,
            )
            db.add(pn)

            db.execute(text("UPDATE schedules SET no_stamp_notified = TRUE WHERE id = :sid"),
                       {"sid": row.id})
            changed = True

        if admin_rows:
            logger.info(f"check_missing_stamps: {len(admin_rows)} Admin-Benachrichtigungen gesendet (60 Min)")

        if changed:
            db.commit()

    except Exception as e:
        logger.error(f"Fehler in check_missing_stamps: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
