"""Dienstplan aus Vorlage (Stamm-Dienstplan): Soll-Schichten einer Woche, offene Luecken,
Status "Plan naechste Woche" und Freitags-Erinnerung an die Objektleitung.

Vorlage = Tabelle master_schedule_entries (je MA, Objekt, Wochentag eine Zeit, Rhythmus).
Eine Luecke ist ein Vorlage-Eintrag, fuer den an dem Tag niemand am Objekt zu der Zeit eingeplant ist
(z. B. weil die Person Urlaub hat, krank ist oder abgesagt hat). Luecken werden nicht gespeichert,
sondern immer aus Vorlage + Dienstplan berechnet: wird jemand eingeplant, ist die Luecke weg.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

OBJ_URLAUB, OBJ_KRANK = 999, 19
WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
RHYTHMEN = ("weekly", "biweekly_even", "biweekly_odd", "monthly")
FERTIG_KEY = "dienstplan_fertig"     # app_settings: {montag: {"user_id", "von", "am"}}
FIXUM_KEY = "dienstplan_fixum"       # app_settings: {montag: {"kopie_id", "am", "angelegt", "luecken"}}
FIXUM_TAG, FIXUM_UHR = 3, "18:00"    # Donnerstag 18:00: Folgewoche als Entwurf aus der Vorlage
ABGABE_TAG, ABGABE_UHR = 4, "12:00"  # Freitag 12:00 vor der Woche


def montag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _q(db, sql, **p):
    return db.execute(text(sql), p).mappings().all()


def rhythmus_passt(rhythm, month_week, weekday, d: date) -> bool:
    """Gleiche Regeln wie die Monats-Erzeugung im Stamm-Dienstplan (admin.generate_month_schedule)."""
    if d.weekday() != weekday:
        return False
    rhythm = rhythm or "weekly"
    if rhythm == "biweekly_even":
        return d.isocalendar()[1] % 2 == 0
    if rhythm == "biweekly_odd":
        return d.isocalendar()[1] % 2 == 1
    if rhythm == "monthly":
        wk = month_week or 1
        if wk == -1:
            return (d + timedelta(days=7)).month != d.month
        return (d.day - 1) // 7 + 1 == wk
    return True


def vorlage(db, obj_ids=None):
    """Aktive Vorlage-Eintraege mit Namen (ohne Test-MA)."""
    flt = "TRUE" if obj_ids is None else "m.object_id = ANY(:o)"
    return _q(db, f"""
        SELECT m.id, m.employee_id, m.object_id, m.weekday, m.start_time, m.end_time, m.planned_hours, m.is_driver,
               coalesce(m.rhythm, 'weekly') AS rhythm, m.month_week,
               e.first_name || ' ' || e.last_name AS name, e.personal_nr, e.is_active AS ma_aktiv, o.name AS objekt
          FROM master_schedule_entries m JOIN employees e ON e.id = m.employee_id JOIN objects o ON o.id = m.object_id
         WHERE coalesce(m.is_active, true) AND NOT coalesce(e.is_test, false) AND {flt}
         ORDER BY m.weekday, m.start_time, e.last_name""", o=list(obj_ids or []))


def soll(db, d0: date, d1: date, obj_ids=None):
    """[(vorlage_row, datum)] fuer den Zeitraum. Sonntage D0002 ab 2027 legt die Sonntagsautomatik an."""
    from app.services import sonntag_d0002 as so
    out = []
    rows = vorlage(db, obj_ids)
    d = d0
    while d <= d1:
        for m in rows:
            if rhythmus_passt(m["rhythm"], m["month_week"], m["weekday"], d) and not so.applies(m["employee_id"], d):
                out.append((m, d))
        d += timedelta(days=1)
    return out


def absagen(db, d0: date, d1: date):
    """{(employee_id, datum): 'Absage'}: abgesagte (stornierte) Schichten und nicht abgelehnte
    Aenderungs-/Absage-Antraege (ausser Tausch) fuer den Tag."""
    rows = _q(db, """
        SELECT employee_id, date AS d FROM schedules WHERE date BETWEEN :a AND :b AND status IN ('storniert', 'abgesagt')
        UNION
        SELECT r.employee_id, coalesce(r.requested_date, s.date) FROM shift_change_requests r
          LEFT JOIN schedules s ON s.id = r.schedule_id
         WHERE r.request_type <> 'swap' AND coalesce(r.status, '') NOT IN ('rejected', 'abgelehnt')
           AND coalesce(r.requested_date, s.date) BETWEEN :a AND :b""", a=d0, b=d1)
    return {(r["employee_id"], r["d"]): "Absage" for r in rows if r["d"]}


def _min(t):
    return t.hour * 60 + t.minute


def _ueberlappt(a0, a1, b0, b1):
    a1 = a1 if a1 > a0 else a1 + 1440
    b1 = b1 if b1 > b0 else b1 + 1440
    return a0 < b1 and b0 < a1


def luecken(db, d0: date, d1: date, obj_ids=None, ab_heute=True):
    """Offene Luecken: Vorlage-Eintraege, fuer die niemand am Objekt zu der Zeit eingeplant ist."""
    from app.api.v1.endpoints.cockpit import _abwesend_map
    if ab_heute:
        d0 = max(d0, date.today())
    if d1 < d0:
        return []
    sollliste = soll(db, d0, d1, obj_ids)
    if not sollliste:
        return []
    besetzt = {}
    for r in _q(db, f"""SELECT id, employee_id, object_id, date, start_time, end_time FROM schedules
                        WHERE date BETWEEN :a AND :b AND status IN ('normal', 'vertretung')
                          AND start_time IS NOT NULL AND end_time IS NOT NULL
                          AND object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})""", a=d0, b=d1):
        besetzt.setdefault((r["object_id"], r["date"]), []).append(r)
    abw = _abwesend_map(db, d0, d1)
    ab = absagen(db, d0, d1)

    # Eins-zu-eins zuordnen (mehrere Personen gleichzeitig im Objekt): erst die eigene Schicht der Person aus der
    # Vorlage, dann jede andere Schicht am Objekt zu der Zeit als Vertretung. Was uebrig bleibt, ist eine Luecke.
    def passt(m, b):
        return _ueberlappt(_min(m["start_time"]), _min(m["end_time"]), _min(b["start_time"]), _min(b["end_time"]))
    benutzt, offen = set(), []
    for m, d in sollliste:
        eigen = next((b for b in besetzt.get((m["object_id"], d), [])
                      if b["employee_id"] == m["employee_id"] and b["id"] not in benutzt and passt(m, b)), None)
        if eigen:
            benutzt.add(eigen["id"])
        else:
            offen.append((m, d))
    out = []
    for m, d in offen:
        vertretung = next((b for b in besetzt.get((m["object_id"], d), []) if b["id"] not in benutzt and passt(m, b)), None)
        if vertretung:
            benutzt.add(vertretung["id"])
            continue
        key = (m["employee_id"], d)
        grund = abw.get(key) or ab.get(key) or ("nicht aktiv" if not m["ma_aktiv"] else "nicht eingeplant")
        out.append({"vorlage_id": m["id"], "datum": d.isoformat(), "tag": WT[d.weekday()], "employee_id": m["employee_id"],
                    "name": m["name"], "object_id": m["object_id"], "objekt": m["objekt"],
                    "beginn": m["start_time"].strftime("%H:%M"), "ende": m["end_time"].strftime("%H:%M"),
                    "fahrer": bool(m["is_driver"]), "grund": grund})
    return out


def _fertig_map(db, key=FERTIG_KEY):
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key}).fetchone()
    try:
        return json.loads(r[0]) if r else {}
    except (TypeError, ValueError):
        return {}


def fertig_setzen(db, mo: date, user, fertig: bool):
    """Woche als fertig melden (oder wieder oeffnen). Die letzten 30 Wochen bleiben gespeichert."""
    from app.services.booking_service import log_audit
    m = _fertig_map(db)
    if fertig:
        wer = db.execute(text("""SELECT coalesce(e.first_name || ' ' || e.last_name, u.email) FROM users u
                                 LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = :i"""), {"i": user.id}).scalar()
        m[mo.isoformat()] = {"user_id": user.id, "von": wer, "am": datetime.now().isoformat(timespec="minutes")}
    else:
        m.pop(mo.isoformat(), None)
    m = dict(sorted(m.items())[-30:])
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": FERTIG_KEY, "v": json.dumps(m), "u": user.id})
    log_audit(db, user.id, None, "dienstplan_fertig" if fertig else "dienstplan_wieder_offen", entity_type="woche",
              entity_id=int(mo.strftime("%Y%m%d")),
              details=f"Dienstplan Woche {mo.strftime('%d.%m.')}–{(mo + timedelta(days=6)).strftime('%d.%m.%Y')} "
                      + ("als fertig gemeldet" if fertig else "wieder geöffnet"))
    db.commit()
    return wochen_status(db, mo)


def wochen_status(db, mo: date, obj_ids=None):
    """Status einer Planwoche: fertig gemeldet?, offene Luecken, Schichten, Abgabe (Freitag 12:00 davor)."""
    mo = montag(mo)
    so_ = mo + timedelta(days=6)
    f = _fertig_map(db).get(mo.isoformat())
    lu = luecken(db, mo, so_, obj_ids)
    soll_n = len(soll(db, max(mo, date.today()), so_, obj_ids)) if so_ >= date.today() else 0
    n = db.execute(text(f"""SELECT count(*) FROM schedules s JOIN employees e ON e.id = s.employee_id
                            WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal', 'vertretung') AND NOT coalesce(e.is_test, false)
                              AND s.object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})"""), {"a": mo, "b": so_}).scalar()
    abgabe = mo - timedelta(days=7 - ABGABE_TAG)
    return {"woche": mo.isoformat(), "bis": so_.isoformat(), "fertig": bool(f), "gemeldet_von": f and f.get("von"),
            "gemeldet_am": f and f.get("am"), "luecken": len(lu), "schichten": n, "vorlage": bool(vorlage(db, obj_ids)),
            "soll": soll_n, "ungeplant": bool(soll_n) and len(lu) == soll_n,   # noch nichts aus der Vorlage eingeplant
            "abgabe": f"{abgabe.isoformat()}T{ABGABE_UHR}", "fixum": _fertig_map(db, FIXUM_KEY).get(mo.isoformat())}


# ---------------------------------------------------------------- Fixum: Donnerstag 18:00 Entwurf aus der Vorlage

def fixum_entwurf(db, now=None):
    """Donnerstag 18:00: Folgewoche automatisch als Entwurf aus der Vorlage anlegen.
    Nur Vorlage-Schichten (feste Leute), die noch niemand abdeckt; Urlaub/Krank/Absage bleiben offene Luecke;
    nichts doppelt, nichts Vorhandenes wird ueberschrieben. Einmal je Woche, nicht wenn die Woche schon fertig gemeldet ist.
    Ganzer Vorgang ueber die Kopie-ID rueckgaengig zu machen (wie 'Woche aus Vorlage')."""
    from types import SimpleNamespace
    from app.api.v1.endpoints.cockpit import _pruefe_neue, _anlegen
    now = now or datetime.now()
    mo = montag(now.date()) + timedelta(days=7)
    so_ = mo + timedelta(days=6)
    fx = _fertig_map(db, FIXUM_KEY)
    if mo.isoformat() in fx:
        return {"status": "bereits_erstellt", "woche": mo.isoformat()}
    if _fertig_map(db).get(mo.isoformat()):
        return {"status": "fertig", "woche": mo.isoformat()}
    vl = {m["id"]: m for m in vorlage(db)}
    if not vl:
        return {"status": "keine_vorlage", "woche": mo.isoformat()}
    lu = luecken(db, mo, so_, ab_heute=False)
    neu = [{"vorlage_id": l["vorlage_id"], "employee_id": l["employee_id"], "object_id": l["object_id"],
            "datum": date.fromisoformat(l["datum"]), "start": vl[l["vorlage_id"]]["start_time"],
            "ende": vl[l["vorlage_id"]]["end_time"], "fahrer": l["fahrer"]}
           for l in lu if l["grund"] == "nicht eingeplant"]
    r = {"angelegt": 0, "kopie_id": None}
    if neu:
        plan = _pruefe_neue(db, neu, mo, so_)
        r = _anlegen(db, SimpleNamespace(id=1), plan, "Fixum-Entwurf aus Vorlage")
    rest = len(luecken(db, mo, so_, ab_heute=False))
    fx[mo.isoformat()] = {"kopie_id": r["kopie_id"], "am": now.isoformat(timespec="minutes"), "angelegt": r["angelegt"], "luecken": rest}
    fx = dict(sorted(fx.items())[-30:])
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), 1)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = 1"""),
               {"k": FIXUM_KEY, "v": json.dumps(fx)})
    from app.services.booking_service import log_audit
    log_audit(db, 1, None, "fixum_entwurf", entity_type="woche", entity_id=int(mo.strftime("%Y%m%d")),
              details=f"Fixum: Woche {mo.strftime('%d.%m.')}–{so_.strftime('%d.%m.%Y')} als Entwurf aus der Vorlage, "
                      f"{r['angelegt']} Schichten angelegt, {rest} offene Lücken" + (f" [Kopie {r['kopie_id']}]" if r["kopie_id"] else ""))
    db.commit()
    return {"status": "erstellt", "woche": mo.isoformat(), "angelegt": r["angelegt"], "luecken": rest, "kopie_id": r["kopie_id"]}


# ---------------------------------------------------------------- Freitags-Erinnerung

def _send(chat_id, text_, knopf=None):
    if os.getenv("DISABLE_TELEGRAM"):          # DEV: nie senden, nur protokollieren
        logger.info(f"Telegram aus (DISABLE_TELEGRAM): {text_[:80]}")
        return False
    from app.services.telegram_bot import send_message_sync
    return send_message_sync(int(chat_id), text_, knopf)


SEND = _send   # austauschbar fuer Tests

MAX_LUECKEN_TEXT = 8


def luecken_text(lu):
    """'Mi Lidl Neu Bie2 13:00, Do ...' (nach Datum/Zeit, hoechstens 8, Rest als '+ N weitere')."""
    lu = sorted(lu, key=lambda l: (l["datum"], l["beginn"], l["objekt"]))
    t = ", ".join(f"{l['tag']} {l['objekt']} {l['beginn']}" for l in lu[:MAX_LUECKEN_TEXT])
    return t + (f", + {len(lu) - MAX_LUECKEN_TEXT} weitere" if len(lu) > MAX_LUECKEN_TEXT else "")


def plan_knopf(url):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("Plan öffnen", url=url)]])


def erinnerung_freitag(db, now=None):
    """Freitag 9 Uhr: Meldung 'Plan naechste Woche: X Luecken (Mi Lidl Neu Bie2 13:00, ...)' mit Knopf 'Plan oeffnen'
    (direkt auf die Luecken) an die Objektleitung UND Drazen (Admin-Chat). Nur wenn der Plan noch offen ist oder
    Luecken hat; einmal je Woche (Audit plan_erinnerung). Gibt eine kurze Auswertung zurueck."""
    import html
    from app.services.booking_service import log_audit
    from app.services.telegram_recipients import admin_chat_id
    now = now or datetime.now()
    mo = montag(now.date()) + timedelta(days=7)
    st = wochen_status(db, mo)
    lu = luecken(db, mo, mo + timedelta(days=6), ab_heute=False)
    if st["fertig"] and not lu:
        return {"status": "fertig", "woche": st["woche"]}
    key = int(mo.strftime("%Y%m%d"))
    if db.execute(text("SELECT 1 FROM audit_log WHERE action = 'plan_erinnerung' AND entity_id = :k LIMIT 1"), {"k": key}).fetchone():
        return {"status": "bereits_erinnert", "woche": st["woche"]}
    empf = [r.telegram_chat_id for r in db.execute(text("""SELECT e.telegram_chat_id FROM users u JOIN employees e ON e.user_id = u.id
                              WHERE u.role = 'OBJEKTLEITER' AND coalesce(u.is_active, true) AND e.is_active
                                AND NOT coalesce(e.is_test, false) AND e.telegram_chat_id IS NOT NULL""")).fetchall()]
    if admin_chat_id() and admin_chat_id() not in [str(c) for c in empf]:
        empf.append(admin_chat_id())
    url = (os.getenv("FRONTEND_URL") or "https://app.seda.de").rstrip("/") + f"/cockpit/dienstplan?start={mo.isoformat()}&luecken=1"
    n = len(lu)
    kopf = f"\U0001f4cb <b>Plan nächste Woche</b> ({mo.strftime('%d.%m.')}–{(mo + timedelta(days=6)).strftime('%d.%m.')}): "
    txt = kopf + (f"{n} Lücke{'n' if n != 1 else ''} ({html.escape(luecken_text(lu))})" if n else "keine Lücken")
    txt += f"\n{st['schichten']} Schichten, " + ("fertig gemeldet." if st["fertig"] else f"noch nicht fertig gemeldet – Abgabe heute {ABGABE_UHR} Uhr.")
    gesendet = sum(1 for c in empf if SEND(c, txt, plan_knopf(url)))
    log_audit(db, 1, None, "plan_erinnerung", entity_type="woche", entity_id=key,
              details=f"Plan nächste Woche {mo.strftime('%d.%m.%Y')}: {n} Lücken, an {gesendet} von {len(empf)} Empfänger(n)")
    db.commit()
    return {"status": "erinnert", "woche": st["woche"], "empfaenger": len(empf), "gesendet": gesendet, "luecken": n,
            "text": txt, "url": url}
