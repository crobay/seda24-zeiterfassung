"""
Sonntagsregel D0002 (Ruzica Sertic) ab 01.01.2027 - Variante B (Automatik).

- Sonntage werden weiter automatisch aus dem Dienstplan gebucht,
  aber hoechstens MAX_SUNDAYS pro Kalendermonat. Ab dem 4. keine Buchung,
  stattdessen einmal Hinweis an den Admin-Chat.
- Planzeit 8,5 Std inkl. 30 Min Pause: Pause wird als break_entry angelegt
  (sichtbar in der Buchung), gebucht wird Planspanne minus Pause (8,0 Std).
- Monatsbestaetigung der Sonntage per Telegram an Ruzica (Bestaetigt / Stimmt nicht),
  Erinnerung am naechsten Morgen 9 Uhr, Hinweis an Admin-Chat am Monatsersten 9 Uhr.

Wird von scripts/auto_booking_category_a.py (Cron) und vom App-Scheduler benutzt.
Telegram wird direkt per HTTP gesendet, damit es auch im Cron-Prozess
(ohne Bot-Event-Loop) funktioniert. Der Token wird nie geloggt.
"""
import json
import logging
import os
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

RULE_EMPLOYEE_ID = 4            # D0002 Ruzica Sertic
RULE_START = date(2027, 1, 1)
MAX_SUNDAYS = 3
BREAK_MINUTES = 30
BREAK_FROM_HOURS = 6.0          # Pause erst bei Planspanne ueber 6 Std
BREAK_TYPE = "auto_sonntag"
SYSTEM_USER_ID = 1              # Audit fuer Automatik (Admin A0001)

MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


# ---------------------------------------------------------------- Telegram

def _env(name):
    val = os.getenv(name)
    if not val:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
        except Exception:
            pass
        val = os.getenv(name, "")
    return val


def _telegram_send(chat_id, text_, buttons=None):
    """Sendet per Bot-API. Gibt message_id oder None zurueck. Token wird nie ausgegeben."""
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        logger.error("Sonntag D0002: Telegram nicht moeglich (Token oder Chat-ID fehlt)")
        return None
    payload = {"chat_id": str(chat_id), "text": text_, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        import httpx
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=15)
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        logger.error(f"Sonntag D0002: Telegram-Fehler an {chat_id}: {data.get('description')}")
    except Exception as e:
        logger.error(f"Sonntag D0002: Telegram-Versand an {chat_id} fehlgeschlagen: {type(e).__name__}")
    return None


# Austauschbar fuer Trockentests
SEND = _telegram_send


def _admin_chat():
    return _env("TELEGRAM_ADMIN_CHAT_ID")


def _employee_chat(db):
    row = db.execute(text("SELECT telegram_chat_id FROM employees WHERE id = :id"),
                     {"id": RULE_EMPLOYEE_ID}).fetchone()
    return row.telegram_chat_id if row else None


def _audit(db, action, entity_type, entity_id, details, new_value=None, user_id=SYSTEM_USER_ID):
    from app.services.booking_service import log_audit
    log_audit(db, user_id, RULE_EMPLOYEE_ID, action, entity_type=entity_type,
              entity_id=entity_id, new_value=new_value, details=details)


# ---------------------------------------------------------------- Regeln

def applies(employee_id, day) -> bool:
    """Gilt die Sonntagsregel fuer diesen MA an diesem Tag?"""
    return employee_id == RULE_EMPLOYEE_ID and day >= RULE_START and day.weekday() == 6


def _month_bounds(year, month):
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt


def booked_sundays(db, year, month):
    """Gebuchte Sonntags-Eintraege von D0002 im Monat (ohne Urlaub 999)."""
    first, nxt = _month_bounds(year, month)
    return db.execute(text("""
        SELECT te.id, te.check_in, te.check_out, te.billed_hours,
               b.start_time AS b_start, b.end_time AS b_end
        FROM time_entries te
        LEFT JOIN break_entries b ON b.time_entry_id = te.id AND b.break_type = :bt
        WHERE te.employee_id = :emp
          AND te.check_in >= :first AND te.check_in < :nxt
          AND EXTRACT(DOW FROM te.check_in) = 0
          AND te.check_out IS NOT NULL
          AND COALESCE(te.object_id, 0) <> 999
        ORDER BY te.check_in
    """), {"emp": RULE_EMPLOYEE_ID, "first": first, "nxt": nxt, "bt": BREAK_TYPE}).fetchall()


def _distinct_days(rows):
    return sorted({r.check_in.date() for r in rows})


def last_sunday_of_month(year, month):
    first, nxt = _month_bounds(year, month)
    d = nxt - timedelta(days=1)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def book_sunday(db, sched, rate, service_type, now=None):
    """Bucht eine Sonntagsschicht von D0002 nach Variante B.
    Gibt 'booked', 'skipped' oder 'exists' zurueck. Commit macht diese Funktion selbst."""
    now = now or datetime.now()
    day = sched.date
    rows = booked_sundays(db, day.year, day.month)
    days = _distinct_days(rows)

    if day in days:
        return "exists"

    if len(days) >= MAX_SUNDAYS:
        already = db.execute(text("""
            SELECT 1 FROM audit_log WHERE action = 'sunday_booking_skipped'
              AND entity_type = 'schedule' AND entity_id = :sid LIMIT 1
        """), {"sid": sched.id}).fetchone()
        if not already:
            datum = day.strftime("%d.%m.%Y")
            liste = ", ".join(d.strftime("%d.%m.") for d in days)
            _audit(db, "sunday_booking_skipped", "schedule", sched.id,
                   f"Sonntag {datum} nicht gebucht: bereits {len(days)} Sonntage im Monat ({liste})",
                   new_value={"datum": str(day), "gebuchte_sonntage": [str(d) for d in days]})
            db.commit()
            SEND(_admin_chat(),
                 f"⚠️ <b>Sonntag nicht gebucht</b>\n"
                 f"Ruzica Sertic (D0002), {datum}, "
                 f"{sched.start_time.strftime('%H:%M')}-{sched.end_time.strftime('%H:%M')}\n"
                 f"Grund: bereits {len(days)} Sonntage im {MONATE[day.month]} gebucht ({liste}).\n"
                 f"Hoechstens {MAX_SUNDAYS} Sonntage pro Monat.")
        return "skipped"

    start_dt = datetime.combine(day, sched.start_time)
    end_dt = datetime.combine(day, sched.end_time)
    span_h = (end_dt - start_dt).total_seconds() / 3600

    check_in = start_dt + timedelta(minutes=random.randint(-3, 3))
    check_out = end_dt + timedelta(minutes=random.randint(0, 2))

    with_break = span_h > BREAK_FROM_HOURS
    billed = round(span_h - BREAK_MINUTES / 60, 2) if with_break else round(span_h, 2)
    note = "Auto-Booking Kategorie A (Sonntag"
    note += f", Pause {BREAK_MINUTES} Min)" if with_break else ")"

    te_id = db.execute(text("""
        INSERT INTO time_entries (employee_id, object_id, check_in, check_out, hourly_rate,
                                  billed_hours, is_manual_entry, service_type, notes)
        VALUES (:emp, :obj, :ci, :co, :rate, :bh, true, :svc, :notes)
        RETURNING id
    """), {"emp": RULE_EMPLOYEE_ID, "obj": sched.object_id, "ci": check_in, "co": check_out,
           "rate": rate, "bh": billed, "svc": service_type, "notes": note}).scalar()

    if with_break:
        # Pause in der Mitte der Planspanne, auf 5 Min gerundet
        mid = start_dt + (end_dt - start_dt) / 2 - timedelta(minutes=BREAK_MINUTES / 2)
        mid = mid.replace(minute=(mid.minute // 5) * 5, second=0, microsecond=0)
        db.execute(text("""
            INSERT INTO break_entries (time_entry_id, start_time, end_time, is_paid, break_type)
            VALUES (:te, :bs, :be, false, :bt)
        """), {"te": te_id, "bs": mid, "be": mid + timedelta(minutes=BREAK_MINUTES), "bt": BREAK_TYPE})

    _audit(db, "booking_created", "time_entry", te_id,
           f"Sonntag automatisch gebucht: Ruzica Sertic, {day.strftime('%d.%m.%Y')}, "
           f"{check_in.strftime('%H:%M')}-{check_out.strftime('%H:%M')}, {billed}h"
           + (f", Pause {BREAK_MINUTES} Min" if with_break else ""),
           new_value={"datum": str(day), "stunden": billed, "pause_min": BREAK_MINUTES if with_break else 0})
    db.commit()

    # Letzter gebuchter Sonntag des Monats? (3. Sonntag oder letzter Sonntag im Monat)
    n = len(days) + 1
    if n >= MAX_SUNDAYS or day >= last_sunday_of_month(day.year, day.month):
        send_confirmation(db, day.year, day.month, now=now)
    return "booked"


# ---------------------------------------------------------------- Bestaetigung

def _format_list(rows):
    lines, total = [], 0.0
    for r in rows:
        h = float(r.billed_hours or 0)
        total += h
        line = (f"So {r.check_in.strftime('%d.%m.')} {r.check_in.strftime('%H:%M')}-"
                f"{r.check_out.strftime('%H:%M')}")
        if r.b_start and r.b_end:
            line += f", Pause {r.b_start.strftime('%H:%M')}-{r.b_end.strftime('%H:%M')}"
        line += f", {h:.1f} Std".replace(".", ",")
        lines.append(line)
    return lines, round(total, 2)


def confirmation_buttons(conf_id):
    return [[{"text": "✅ Bestätigt", "callback_data": f"sun_ok:{conf_id}"},
             {"text": "❌ Stimmt nicht", "callback_data": f"sun_no:{conf_id}"}]]


def send_confirmation(db, year, month, now=None):
    """Sendet Ruzica die Sonntagsliste des Monats (einmal pro Monat)."""
    now = now or datetime.now()
    rows = booked_sundays(db, year, month)
    if not rows:
        return None
    existing = db.execute(text("""
        SELECT id, sent_at FROM sunday_confirmations
        WHERE employee_id = :emp AND year = :y AND month = :m
    """), {"emp": RULE_EMPLOYEE_ID, "y": year, "m": month}).fetchone()
    if existing and existing.sent_at:
        return existing.id

    lines, total = _format_list(rows)
    if existing:
        conf_id = existing.id
        db.execute(text("UPDATE sunday_confirmations SET sunday_list = :l, total_hours = :t WHERE id = :id"),
                   {"l": "\n".join(lines), "t": total, "id": conf_id})
    else:
        conf_id = db.execute(text("""
            INSERT INTO sunday_confirmations (employee_id, year, month, status, sunday_list, total_hours)
            VALUES (:emp, :y, :m, 'offen', :l, :t) RETURNING id
        """), {"emp": RULE_EMPLOYEE_ID, "y": year, "m": month, "l": "\n".join(lines), "t": total}).scalar()
    db.commit()

    msg = (f"<b>Deine Sonntage im {MONATE[month]} {year}</b>\n\n" + "\n".join(lines) +
           f"\n\nSumme: {total:.1f} Std".replace(".", ",") +
           "\n\nBitte bestätigen, ob das stimmt.")
    mid = SEND(_employee_chat(db), msg, confirmation_buttons(conf_id))
    if mid:
        db.execute(text("UPDATE sunday_confirmations SET sent_at = :now, telegram_message_id = :mid WHERE id = :id"),
                   {"now": now, "mid": mid, "id": conf_id})
        _audit(db, "sunday_confirmation_sent", "sunday_confirmation", conf_id,
               f"Sonntagsliste {MONATE[month]} {year} an Ruzica gesendet ({len(lines)} Sonntage, {total} Std)")
        db.commit()
    else:
        logger.error(f"Sonntag D0002: Bestaetigung {month}/{year} konnte nicht gesendet werden")
    return conf_id


def decide(db, conf_id, chat_id, confirmed: bool, now=None):
    """Knopf 'Bestaetigt' / 'Stimmt nicht'. Gibt (ok, text_fuer_nachricht) zurueck."""
    now = now or datetime.now()
    emp = db.execute(text("SELECT user_id, telegram_chat_id FROM employees WHERE id = :id"),
                     {"id": RULE_EMPLOYEE_ID}).fetchone()
    if not emp or str(emp.telegram_chat_id or "") != str(chat_id):
        return False, None
    conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id FOR UPDATE"),
                      {"id": conf_id}).fetchone()
    if not conf or conf.employee_id != RULE_EMPLOYEE_ID:
        return False, None
    monat = f"{MONATE[conf.month]} {conf.year}"
    if conf.status != "offen":
        label = "bestätigt" if conf.status == "bestaetigt" else "als falsch gemeldet"
        return True, f"Sonntage {monat} wurden bereits {label}."

    status = "bestaetigt" if confirmed else "abgelehnt"
    db.execute(text("UPDATE sunday_confirmations SET status = :s, decided_at = :now WHERE id = :id"),
               {"s": status, "now": now, "id": conf_id})
    _audit(db, "sunday_month_confirmed" if confirmed else "sunday_month_disputed",
           "sunday_confirmation", conf_id,
           f"Sonntage {monat} " + ("von Ruzica bestätigt" if confirmed else "von Ruzica als falsch gemeldet")
           + f" ({conf.total_hours} Std)",
           new_value={"status": status, "liste": conf.sunday_list}, user_id=emp.user_id)
    db.commit()

    zeit = now.strftime("%d.%m. %H:%M")
    if confirmed:
        return True, (f"<b>Deine Sonntage im {monat}</b>\n\n{conf.sunday_list}\n\n"
                      f"✅ Bestätigt am {zeit}. Danke!")
    SEND(_admin_chat(),
         f"⚠️ <b>Sonntage stimmen nicht</b>\n"
         f"Ruzica Sertic (D0002) hat die Sonntage {monat} als falsch gemeldet:\n\n"
         f"{conf.sunday_list}\n\nBitte mit ihr klären und in der App korrigieren.")
    return True, (f"<b>Deine Sonntage im {monat}</b>\n\n{conf.sunday_list}\n\n"
                  f"❌ Als falsch gemeldet am {zeit}. Die Leitung ist informiert.")


def daily_followup(db, now=None):
    """Taeglich 09:00 (App-Scheduler):
    1. Liste nachsenden, wenn der letzte Sonntag des Monats vorbei ist und noch nichts gesendet wurde.
    2. Einmal Erinnerung an Ruzica, wenn seit dem Versand ein 9-Uhr-Termin vergangen ist.
    3. Am Monatsersten einmal Hinweis an den Admin-Chat fuer den Vormonat, wenn noch offen."""
    now = now or datetime.now()
    today = now.date()

    # 1. Nachsenden (Monat dieses oder letzten Sonntags)
    for y, m in {(today.year, today.month),
                 ((today - timedelta(days=today.day)).year, (today - timedelta(days=today.day)).month)}:
        if date(y, m, 1) < RULE_START:
            continue
        if today > last_sunday_of_month(y, m):
            send_confirmation(db, y, m, now=now)

    # 2. Erinnerung
    nine = datetime.combine(today, time(9, 0))
    for c in db.execute(text("""
        SELECT id, year, month, sunday_list FROM sunday_confirmations
        WHERE employee_id = :emp AND status = 'offen' AND sent_at IS NOT NULL
          AND reminder_sent_at IS NULL AND sent_at < :nine
    """), {"emp": RULE_EMPLOYEE_ID, "nine": nine}).fetchall():
        mid = SEND(_employee_chat(db),
                   f"\U0001F514 <b>Erinnerung: Sonntage {MONATE[c.month]} {c.year}</b>\n\n{c.sunday_list}\n\n"
                   f"Bitte bestätigen, ob das stimmt.", confirmation_buttons(c.id))
        if mid:
            db.execute(text("UPDATE sunday_confirmations SET reminder_sent_at = :now WHERE id = :id"),
                       {"now": now, "id": c.id})
            _audit(db, "sunday_confirmation_reminder", "sunday_confirmation", c.id,
                   f"Erinnerung Sonntage {MONATE[c.month]} {c.year} an Ruzica gesendet")
            db.commit()

    # 3. Monatserster: Hinweis an Admin-Chat fuer den Vormonat
    if today.day == 1:
        prev = today - timedelta(days=1)
        c = db.execute(text("""
            SELECT id, year, month, sunday_list, sent_at FROM sunday_confirmations
            WHERE employee_id = :emp AND year = :y AND month = :m
              AND status = 'offen' AND admin_notified_at IS NULL
        """), {"emp": RULE_EMPLOYEE_ID, "y": prev.year, "m": prev.month}).fetchone()
        if c:
            ok = SEND(_admin_chat(),
                      f"⚠️ <b>Sonntage nicht bestätigt</b>\n"
                      f"Ruzica Sertic (D0002) hat die Sonntage {MONATE[c.month]} {c.year} "
                      f"bis heute 9 Uhr nicht bestätigt"
                      + ("" if c.sent_at else " (Liste konnte nicht zugestellt werden)") +
                      f":\n\n{c.sunday_list}")
            if ok:
                db.execute(text("UPDATE sunday_confirmations SET admin_notified_at = :now WHERE id = :id"),
                           {"now": now, "id": c.id})
                _audit(db, "sunday_confirmation_overdue", "sunday_confirmation", c.id,
                       f"Sonntage {MONATE[c.month]} {c.year} nicht bestätigt, Admin-Chat informiert")
                db.commit()


def lexware_intervals(entry, breaks):
    """Lexware-Bloecke fuer eine Sonntagsbuchung mit Automatik-Pause: an der Pause teilen."""
    auto = [b for b in breaks if b.break_type == BREAK_TYPE and b.end_time and not b.is_paid]
    if not auto:
        return [(entry.check_in, entry.check_out)]
    b = auto[0]
    return [(entry.check_in, b.start_time), (b.end_time, entry.check_out)]
