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
YEAR_WARN_FROM = 34             # ab dem 34. Arbeitssonntag im Jahr Warnung
YEAR_BLOCK_FROM = 38            # ab dem 38. keine Buchung
MAX_SUNDAY_HOURS = 10.0         # Sonntag ueber 10 Std: keine Buchung
REST_WINDOW_DAYS = 14           # Ersatzruhetag innerhalb von 14 Tagen
SUNDAY_SHARE_MAX = 0.35         # Sonntagsstunden ueber 35 % der Monatsstunden: Hinweis

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


def year_sundays(db, year, until=None):
    """Gearbeitete (gebuchte) Sonntage von D0002 im Kalenderjahr, optional bis einschl. until."""
    rows = db.execute(text("""
        SELECT DISTINCT CAST(check_in AS DATE) AS d FROM time_entries
        WHERE employee_id = :emp AND check_out IS NOT NULL
          AND check_in >= :f AND check_in < :n
          AND EXTRACT(DOW FROM check_in) = 0
          AND COALESCE(object_id, 0) <> 999
        ORDER BY 1
    """), {"emp": RULE_EMPLOYEE_ID, "f": date(year, 1, 1),
           "n": (until + timedelta(days=1)) if until else date(year + 1, 1, 1)}).fetchall()
    return [r.d for r in rows]


def _block(db, sched, reason, detail):
    """Sonntag nicht buchen (Sperre): einmal Audit + Hinweis an den Admin-Chat je Schicht und Grund."""
    already = db.execute(text("""
        SELECT 1 FROM audit_log WHERE action = 'sunday_booking_skipped'
          AND entity_type = 'schedule' AND entity_id = :sid AND details LIKE :r LIMIT 1
    """), {"sid": sched.id, "r": f"%{reason}%"}).fetchone()
    if already:
        return
    datum = sched.date.strftime("%d.%m.%Y")
    _audit(db, "sunday_booking_skipped", "schedule", sched.id,
           f"Sonntag {datum} nicht gebucht: {reason} ({detail})",
           new_value={"datum": str(sched.date), "grund": reason, "detail": detail})
    db.commit()
    SEND(_admin_chat(),
         f"⛔ <b>Sonntag nicht gebucht (Sperre)</b>\n"
         f"Ruzica Sertic (D0002), {datum}, "
         f"{sched.start_time.strftime('%H:%M')}-{sched.end_time.strftime('%H:%M')}\n"
         f"Grund: {reason} ({detail}).")


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

    # Sperren: Sonntag ueber 10 Std, 38. Arbeitssonntag im Jahr
    billed_plan = round(span_h - BREAK_MINUTES / 60, 2) if span_h > BREAK_FROM_HOURS else round(span_h, 2)
    if billed_plan > MAX_SUNDAY_HOURS:
        _block(db, sched, "Sonntag über 10 Std", f"{billed_plan:g} Std geplant")
        return "skipped"
    n_year = len([d for d in year_sundays(db, day.year) if d != day]) + 1
    if n_year >= YEAR_BLOCK_FROM:
        _block(db, sched, f"{YEAR_BLOCK_FROM}. Arbeitssonntag im Jahr", f"wäre der {n_year}. Sonntag {day.year}")
        return "skipped"

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

ACTIVITIES = {
    "mops": "Mops waschen/trocknen",
    "material": "Material für Montag",
    "kontrolle": "Objektkontrolle",
    "sonstiges": "Sonstiges",
}


def activities(db, year, month):
    """Gewaehlte Taetigkeiten je Sonntag: {date: code}."""
    first, nxt = _month_bounds(year, month)
    return {r.date: r.activity for r in db.execute(text("""
        SELECT date, activity FROM sunday_activities
        WHERE employee_id = :emp AND date >= :f AND date < :n
    """), {"emp": RULE_EMPLOYEE_ID, "f": first, "n": nxt}).fetchall()}


def _format_list(rows, acts=None):
    lines, total = [], 0.0
    for r in rows:
        h = float(r.billed_hours or 0)
        total += h
        line = (f"So {r.check_in.strftime('%d.%m.')} {r.check_in.strftime('%H:%M')}-"
                f"{r.check_out.strftime('%H:%M')}")
        if r.b_start and r.b_end:
            line += f", Pause {r.b_start.strftime('%H:%M')}-{r.b_end.strftime('%H:%M')}"
        line += f", {h:.1f} Std".replace(".", ",")
        if acts is not None:
            code = acts.get(r.check_in.date())
            line += f"\n   Tätigkeit: {ACTIVITIES[code]}" if code else "\n   Tätigkeit: – bitte wählen"
        lines.append(line)
    return lines, round(total, 2)


def confirmation_buttons(conf_id, days=()):
    """Je Sonntag ein Knopf 'Taetigkeit', darunter Bestaetigt / Stimmt nicht."""
    rows = [[{"text": f"📝 Tätigkeit So {d.strftime('%d.%m.')}",
              "callback_data": f"sun_act:{conf_id}:{d.strftime('%Y%m%d')}"}] for d in days]
    rows.append([{"text": "✅ Bestätigt", "callback_data": f"sun_ok:{conf_id}"},
                 {"text": "❌ Stimmt nicht", "callback_data": f"sun_no:{conf_id}"}])
    return rows


def render_confirmation(db, conf, erinnerung=False):
    """Text + Knoepfe der Sonntagsliste mit aktuellen Taetigkeiten."""
    rows = booked_sundays(db, conf.year, conf.month)
    lines, total = _format_list(rows, activities(db, conf.year, conf.month))
    kopf = (f"\U0001F514 <b>Erinnerung: Sonntage {MONATE[conf.month]} {conf.year}</b>" if erinnerung
            else f"<b>Deine Sonntage im {MONATE[conf.month]} {conf.year}</b>")
    msg = (kopf + "\n\n" + "\n".join(lines) +
           f"\n\nSumme: {total:.1f} Std".replace(".", ",") +
           "\n\nBitte je Sonntag die Tätigkeit wählen und bestätigen, ob das stimmt.")
    return msg, confirmation_buttons(conf.id, _distinct_days(rows))


def _check_chat(db, chat_id):
    emp = db.execute(text("SELECT user_id, telegram_chat_id FROM employees WHERE id = :id"),
                     {"id": RULE_EMPLOYEE_ID}).fetchone()
    if not emp or str(emp.telegram_chat_id or "") != str(chat_id):
        return None
    return emp


def activity_menu(db, conf_id, chat_id, day):
    """Knopf 'Taetigkeit So dd.mm.': Auswahl anzeigen. Gibt (ok, text, buttons) zurueck."""
    if not _check_chat(db, chat_id):
        return False, None, None
    conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id"), {"id": conf_id}).fetchone()
    if not conf or conf.employee_id != RULE_EMPLOYEE_ID:
        return False, None, None
    if conf.status != "offen":
        return True, f"Sonntage {MONATE[conf.month]} {conf.year} sind bereits abgeschlossen.", None
    key = day.strftime("%Y%m%d")
    buttons = [[{"text": label, "callback_data": f"sun_set:{conf_id}:{key}:{code}"}]
               for code, label in ACTIVITIES.items()]
    buttons.append([{"text": "↩ Zurück", "callback_data": f"sun_back:{conf_id}"}])
    return True, f"<b>Tätigkeit am Sonntag {day.strftime('%d.%m.%Y')}</b>\n\nBitte auswählen:", buttons


def back_to_list(db, conf_id, chat_id):
    if not _check_chat(db, chat_id):
        return False, None, None
    conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id"), {"id": conf_id}).fetchone()
    if not conf or conf.employee_id != RULE_EMPLOYEE_ID:
        return False, None, None
    if conf.status != "offen":
        return True, f"Sonntage {MONATE[conf.month]} {conf.year} sind bereits abgeschlossen.", None
    msg, buttons = render_confirmation(db, conf)
    return True, msg, buttons


def set_activity(db, conf_id, chat_id, day, code, now=None):
    """Taetigkeit fuer einen Sonntag speichern (mit Audit), danach wieder die Liste."""
    now = now or datetime.now()
    emp = _check_chat(db, chat_id)
    if not emp or code not in ACTIVITIES:
        return False, None, None
    conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id FOR UPDATE"),
                      {"id": conf_id}).fetchone()
    if not conf or conf.employee_id != RULE_EMPLOYEE_ID:
        return False, None, None
    if conf.status != "offen":
        return True, f"Sonntage {MONATE[conf.month]} {conf.year} sind bereits abgeschlossen.", None
    if day not in _distinct_days(booked_sundays(db, conf.year, conf.month)):
        return False, None, None
    old = db.execute(text("SELECT activity FROM sunday_activities WHERE employee_id = :e AND date = :d"),
                     {"e": RULE_EMPLOYEE_ID, "d": day}).fetchone()
    if not old or old.activity != code:
        db.execute(text("""
            INSERT INTO sunday_activities (employee_id, date, activity, chosen_at)
            VALUES (:e, :d, :a, :now)
            ON CONFLICT (employee_id, date) DO UPDATE SET activity = EXCLUDED.activity, chosen_at = EXCLUDED.chosen_at
        """), {"e": RULE_EMPLOYEE_ID, "d": day, "a": code, "now": now})
        _audit(db, "sunday_activity_set", "sunday_confirmation", conf_id,
               f"Tätigkeit Sonntag {day.strftime('%d.%m.%Y')} von Ruzica gewählt: {ACTIVITIES[code]}"
               + (f" (vorher {ACTIVITIES.get(old.activity, old.activity)})" if old else ""),
               new_value={"datum": str(day), "taetigkeit": code,
                          "vorher": old.activity if old else None}, user_id=emp.user_id)
        db.commit()
    msg, buttons = render_confirmation(db, conf)
    return True, msg, buttons


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

    conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id"), {"id": conf_id}).fetchone()
    msg, buttons = render_confirmation(db, conf)
    mid = SEND(_employee_chat(db), msg, buttons)
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
    # Liste mit den gewaehlten Taetigkeiten festschreiben
    lines, total = _format_list(booked_sundays(db, conf.year, conf.month), activities(db, conf.year, conf.month))
    if lines:
        db.execute(text("UPDATE sunday_confirmations SET sunday_list = :l, total_hours = :t WHERE id = :id"),
                   {"l": "\n".join(lines), "t": total, "id": conf_id})
        conf = db.execute(text("SELECT * FROM sunday_confirmations WHERE id = :id"), {"id": conf_id}).fetchone()
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
        SELECT * FROM sunday_confirmations
        WHERE employee_id = :emp AND status = 'offen' AND sent_at IS NOT NULL
          AND reminder_sent_at IS NULL AND sent_at < :nine
    """), {"emp": RULE_EMPLOYEE_ID, "nine": nine}).fetchall():
        msg, buttons = render_confirmation(db, c, erinnerung=True)
        mid = SEND(_employee_chat(db), msg, buttons)
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


def warnungen(db, year, month, today=None):
    """Warnungen/Hinweise/Sperren fuer D0002 im Monat (fuer Offene Punkte und Lohnuebersicht).
    Liste von dicts: level (warnung|sperre|hinweis), datum, text."""
    first, nxt = _month_bounds(year, month)
    if first < RULE_START:
        return []
    out = []
    month_end = nxt - timedelta(days=1)
    yr = year_sundays(db, year, until=month_end)
    # 1. ab 34. Arbeitssonntag im Jahr
    if len(yr) >= YEAR_WARN_FROM:
        out.append({"level": "warnung", "datum": str(yr[YEAR_WARN_FROM - 1]),
                    "text": f"{len(yr)} Arbeitssonntage in {year} (Warnung ab {YEAR_WARN_FROM}, "
                            f"ab dem {YEAR_BLOCK_FROM}. keine Buchung)"})
    # 2. Sperren aus der Automatik (38. Sonntag, ueber 10 Std)
    for r in db.execute(text("""
        SELECT details, CAST(new_value AS json)->>'datum' AS datum FROM audit_log
        WHERE action = 'sunday_booking_skipped' AND employee_id = :emp
          AND new_value LIKE :g
          AND CAST(new_value AS json)->>'datum' >= :f AND CAST(new_value AS json)->>'datum' < :n
        ORDER BY 2
    """), {"emp": RULE_EMPLOYEE_ID, "f": str(first), "n": str(nxt), "g": '%"grund"%'}).fetchall():
        out.append({"level": "sperre", "datum": r.datum, "text": r.details})
    rows = booked_sundays(db, year, month)
    # 3. gebuchte Sonntage ueber 10 Std (z. B. manuell)
    for r in rows:
        h = float(r.billed_hours) if r.billed_hours is not None else (r.check_out - r.check_in).total_seconds() / 3600
        if h > MAX_SUNDAY_HOURS:
            out.append({"level": "sperre", "datum": str(r.check_in.date()),
                        "text": f"Sonntag {r.check_in.strftime('%d.%m.%Y')} mit {h:.2f} Std gebucht "
                                f"(über {MAX_SUNDAY_HOURS:g} Std nicht zulässig) – bitte korrigieren"})
    # 4. Ersatzruhetag: dienstplanfreier Werktag (Mo-Sa) in den 14 Tagen nach dem Sonntag
    for d in _distinct_days(rows):
        frei = db.execute(text("""
            SELECT COUNT(*) FROM generate_series(CAST(:a AS date), CAST(:b AS date), INTERVAL '1 day') g(t)
            WHERE EXTRACT(DOW FROM g.t) <> 0
              AND NOT EXISTS (SELECT 1 FROM schedules s WHERE s.employee_id = :emp
                              AND s.date = CAST(g.t AS date) AND s.status IN ('normal', 'vertretung'))
        """), {"a": d + timedelta(days=1), "b": d + timedelta(days=REST_WINDOW_DAYS),
               "emp": RULE_EMPLOYEE_ID}).scalar()
        if not frei:
            out.append({"level": "hinweis", "datum": str(d),
                        "text": f"Kein dienstplanfreier Werktag in den {REST_WINDOW_DAYS} Tagen nach "
                                f"Sonntag {d.strftime('%d.%m.%Y')} (Ersatzruhetag fehlt)"})
    # 5. Sonntagsanteil ueber 35 % der Monatsstunden (Festgehalt)
    from app.services import festgehalt
    fg = festgehalt.active_in_month(db, RULE_EMPLOYEE_ID, year, month)
    if fg and rows:
        sum_h = sum(float(r.billed_hours or 0) for r in rows)
        share = sum_h / float(fg.monatsstunden)
        if share > SUNDAY_SHARE_MAX:
            out.append({"level": "hinweis", "datum": str(first),
                        "text": f"Sonntagsstunden {MONATE[month]} {year}: {sum_h:.1f} Std = "
                                f"{share * 100:.0f} % der {float(fg.monatsstunden):g} Monatsstunden "
                                f"(über {SUNDAY_SHARE_MAX * 100:.0f} %)"})
    return out


def lexware_intervals(entry, breaks):
    """Lexware-Bloecke fuer eine Sonntagsbuchung mit Automatik-Pause: an der Pause teilen."""
    auto = [b for b in breaks if b.break_type == BREAK_TYPE and b.end_time and not b.is_paid]
    if not auto:
        return [(entry.check_in, entry.check_out)]
    b = auto[0]
    return [(entry.check_in, b.start_time), (b.end_time, entry.check_out)]


# ---------------------------------------------------------------- Dienstplan fuellen

FILL_START = time(10, 30)
FILL_END = time(19, 0)
FILL_DAY = 20                   # am 20. des Vormonats
FALLBACK_OBJECT_ID = 1          # SEDA24 Zentrale


def sunday_object_id(db, ref_day):
    """Bisheriges Sonntags-Objekt: haeufigstes Objekt ihrer Sonntagsschichten der letzten 120 Tage."""
    row = db.execute(text("""
        SELECT s.object_id FROM schedules s JOIN objects o ON o.id = s.object_id
        WHERE s.employee_id = :emp AND EXTRACT(DOW FROM s.date) = 0
          AND s.date BETWEEN :von AND :bis AND o.is_active = true
          AND s.status IN ('normal', 'vertretung')
        GROUP BY s.object_id ORDER BY COUNT(*) DESC, MAX(s.date) DESC LIMIT 1
    """), {"emp": RULE_EMPLOYEE_ID, "von": ref_day - timedelta(days=120), "bis": ref_day}).fetchone()
    return row.object_id if row else FALLBACK_OBJECT_ID


def fill_sunday_schedules(db, year, month, now=None, force=False):
    """Legt die ersten 3 Sonntage des Monats 10:30-19:00 fuer D0002 an (normale Dienstplan-Logik).
    Vorhandene Schichten werden nicht ueberschrieben, nie mehr als 3 Sonntagsschichten im Monat.
    Laeuft pro Zielmonat nur einmal (Audit sunday_schedule_fill), ausser force=True."""
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api.v1.endpoints.admin import create_schedule

    now = now or datetime.now()
    first, nxt = _month_bounds(year, month)
    if first < RULE_START:
        return {"status": "vor_regelstart"}
    key = year * 100 + month
    done = db.execute(text("""
        SELECT 1 FROM audit_log WHERE action = 'sunday_schedule_fill'
          AND entity_type = 'month' AND entity_id = :k LIMIT 1
    """), {"k": key}).fetchone()
    if done and not force:
        return {"status": "bereits_gelaufen"}

    sundays = []
    d = first
    while d < nxt:
        if d.weekday() == 6:
            sundays.append(d)
        d += timedelta(days=1)
    target = sundays[:MAX_SUNDAYS]

    existing_sun = db.execute(text("""
        SELECT date FROM schedules WHERE employee_id = :emp AND date >= :f AND date < :n
          AND EXTRACT(DOW FROM date) = 0 AND status IN ('normal', 'vertretung')
    """), {"emp": RULE_EMPLOYEE_ID, "f": first, "n": nxt}).fetchall()
    active_count = len({r.date for r in existing_sun})

    obj_id = sunday_object_id(db, now.date())
    admin = SimpleNamespace(id=SYSTEM_USER_ID)
    result = {"status": "ok", "objekt": obj_id, "angelegt": [], "uebersprungen": []}
    for day in target:
        has = db.execute(text("""
            SELECT id, start_time, end_time, status FROM schedules
            WHERE employee_id = :emp AND date = :d ORDER BY start_time LIMIT 1
        """), {"emp": RULE_EMPLOYEE_ID, "d": day}).fetchone()
        if has:
            result["uebersprungen"].append((str(day), f"Schicht vorhanden ({has.status})"))
            continue
        if active_count >= MAX_SUNDAYS:
            result["uebersprungen"].append((str(day), f"bereits {active_count} Sonntage im Monat"))
            continue
        try:
            r = create_schedule({"employee_id": RULE_EMPLOYEE_ID, "object_id": obj_id, "date": str(day),
                                 "start_time": FILL_START.strftime("%H:%M"), "end_time": FILL_END.strftime("%H:%M"),
                                 "status": "normal"}, db=db, admin=admin)
            result["angelegt"].append((str(day), r["id"]))
            active_count += 1
        except HTTPException as e:
            db.rollback()
            result["uebersprungen"].append((str(day), f"Konflikt: {e.detail}"))

    _audit(db, "sunday_schedule_fill", "month", key,
           f"Sonntage {MONATE[month]} {year} fuer Ruzica geplant: "
           f"{len(result['angelegt'])} angelegt, {len(result['uebersprungen'])} uebersprungen",
           new_value={"angelegt": result["angelegt"], "uebersprungen": result["uebersprungen"], "objekt": obj_id})
    db.commit()
    return result


def fill_next_month(db, now=None):
    """Scheduler: ab dem 20. eines Monats den Folgemonat fuellen (einmal pro Zielmonat;
    die Tage 21-31 fangen einen verpassten Lauf nach Ausfall auf)."""
    now = now or datetime.now()
    if now.day < FILL_DAY:
        return None
    nxt = (now.date().replace(day=1) + timedelta(days=32)).replace(day=1)
    return fill_sunday_schedules(db, nxt.year, nxt.month, now=now)
