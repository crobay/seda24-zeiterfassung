"""Admin-Cockpit (Prototyp): Heute, Dienstplan, Mitarbeiter-Akte, Objekte, Zeiten.

Admin und Objektleitung haben dieselben Rechte; einzige Ausnahme: Kunden-Umsaetze nur Admin
(ol_scope.can_see_revenue). Aktionen (Genehmigen, Ablehnen, ...) rufen die bestehende Logik auf.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.v1.endpoints.admin import verify_admin_or_objektleiter
from app.services import ol_scope
from app.services.booking_service import log_audit

router = APIRouter()

OBJ_URLAUB, OBJ_KRANK = 999, 19
LATE_MIN = 10  # ab so vielen Minuten nach Schichtbeginn ohne Stempel gilt "fehlt"
WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _q(db, sql, **p):
    return db.execute(text(sql), p).mappings().all()


def _hm(t):
    return t.strftime("%H:%M") if t else None


def _scope(db, user):
    obj = ol_scope.scope_object_ids(db, user)
    emp = ol_scope.scope_employee_ids(db, user, obj)
    return obj, emp


def _flt(col, ids):
    """SQL-Bedingung fuer den Sichtbereich (None = alles)."""
    if ids is None:
        return "TRUE"
    return f"{col} = ANY(:{col.replace('.', '_')})"


def _params(obj, emp, **extra):
    p = dict(extra)
    if obj is not None:
        for k in ("s_object_id", "t_object_id", "p_object_id", "o_id", "a_object_id", "k_object_id"):
            p[k] = list(obj)
    if emp is not None:
        for k in ("e_id", "m_sender_employee_id", "v_employee_id", "r_employee_id", "a_employee_id",
                  "t_employee_id", "s_employee_id"):
            p[k] = list(emp)
    return p


def _net_hours(ci, co, billed, brk_sec):
    if billed is not None and billed >= 0:
        return float(billed)
    if ci and co and co > ci:
        return max(0.0, ((co - ci).total_seconds() - (brk_sec or 0)) / 3600)
    return 0.0


@router.get("/me")
def me(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, _ = _scope(db, user)
    objs = _q(db, f"SELECT id, name FROM objects o WHERE {_flt('o.id', obj)} AND NOT coalesce(is_test,false) "
                  f"AND coalesce(is_active,true) AND id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) ORDER BY name", **_params(obj, None))
    emp = _q(db, "SELECT first_name, last_name FROM employees WHERE user_id = :u", u=user.id)
    name = f"{emp[0]['first_name']} {emp[0]['last_name']}" if emp else user.email
    return {"role": ol_scope.role_of(user), "name": name, "objekte": [dict(o) for o in objs],
            "alle_objekte": obj is None, "rechte": ol_scope.rights(user)}


@router.get("/heute")
def heute(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, emp = _scope(db, user)
    now = datetime.now()
    today = now.date()
    p = _params(obj, emp, d=today, y=today - timedelta(days=1))

    shifts = _q(db, f"""
        SELECT s.id, s.employee_id, s.object_id, s.start_time, s.end_time, s.status, o.name AS objekt,
               e.first_name || ' ' || e.last_name AS name, e.personal_nr,
               coalesce(a.tracking_category, u.category, 'C') AS kat
          FROM schedules s
          JOIN employees e ON e.id = s.employee_id JOIN users u ON u.id = e.user_id
          LEFT JOIN objects o ON o.id = s.object_id
          LEFT JOIN employee_object_assignments a ON a.employee_id = s.employee_id AND a.object_id = s.object_id
               AND coalesce(a.is_active, true)
         WHERE s.date = :d AND s.status IN ('normal','vertretung') AND NOT coalesce(e.is_test,false)
           AND coalesce(s.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('s.object_id', obj)}
         ORDER BY s.start_time, name""", **p)

    entries = _q(db, f"""
        SELECT t.id, t.employee_id, t.object_id, t.check_in, t.check_out, o.name AS objekt,
               e.first_name || ' ' || e.last_name AS name, e.personal_nr
          FROM time_entries t JOIN employees e ON e.id = t.employee_id LEFT JOIN objects o ON o.id = t.object_id
         WHERE (t.check_in::date = :d OR (t.check_out IS NULL AND t.check_in::date >= :y))
           AND NOT coalesce(e.is_test,false) AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
           AND {_flt('t.object_id', obj)}
         ORDER BY t.check_in""", **p)

    by_emp = {}
    for t in entries:
        by_emp.setdefault(t["employee_id"], []).append(t)
    used = set()
    rows = []
    for s in shifts:
        cand = [t for t in by_emp.get(s["employee_id"], []) if t["id"] not in used
                and (t["object_id"] == s["object_id"] or t["object_id"] is None)]
        t = cand[0] if cand else None
        if t:
            used.add(t["id"])
        start = datetime.combine(today, s["start_time"]) if s["start_time"] else None
        end = datetime.combine(today, s["end_time"]) if s["end_time"] else None
        kat = (s["kat"] or "C").upper()
        if t and t["check_out"] is None:
            status, text_ = "da", f"Da seit {_hm(t['check_in'])}"
        elif t:
            status, text_ = "fertig", f"Fertig {_hm(t['check_in'])}–{_hm(t['check_out'])}"
        elif kat == "A":
            status, text_ = ("auto", "Auto-Buchung nach Schichtende") if not end or now < end else \
                ("fehlt", "Auto-Buchung fehlt")
        elif kat == "B":
            status, text_ = ("geplant", "Bestätigt nach Schicht (Telegram)") if not end or now < end else \
                ("offen", "Bestätigung fehlt")
        elif end and now > end:
            status, text_ = "fehlt", "Fehlt – nicht gestempelt"
        elif start and now >= start + timedelta(minutes=LATE_MIN):
            mins = int((now - start).total_seconds() // 60)
            status, text_ = "fehlt", f"Fehlt – seit {mins // 60} h {mins % 60:02d} min" if mins >= 60 \
                else f"Fehlt – seit {mins} min"
        else:
            status, text_ = "kommt", f"Kommt um {_hm(s['start_time'])}"
        rows.append({"schicht_id": s["id"], "employee_id": s["employee_id"], "name": s["name"],
                     "personal_nr": s["personal_nr"], "objekt": s["objekt"], "object_id": s["object_id"],
                     "beginn": _hm(s["start_time"]), "ende": _hm(s["end_time"]), "kategorie": kat,
                     "status": status, "status_text": text_, "eintrag_id": t["id"] if t else None})

    ohne_schicht = [{"employee_id": t["employee_id"], "name": t["name"], "personal_nr": t["personal_nr"],
                     "objekt": t["objekt"], "seit": _hm(t["check_in"]), "eintrag_id": t["id"],
                     "status": "da" if t["check_out"] is None else "fertig"}
                    for t in entries if t["id"] not in used and t["check_in"].date() == today]

    abwesend = _q(db, f"""
        SELECT DISTINCT e.id AS employee_id, e.first_name || ' ' || e.last_name AS name,
               CASE WHEN x.art = 'K' THEN 'Krank' ELSE 'Urlaub' END AS grund
          FROM (SELECT employee_id, CASE WHEN object_id = {OBJ_KRANK} THEN 'K' ELSE 'U' END AS art FROM schedules
                 WHERE date = :d AND object_id IN ({OBJ_URLAUB},{OBJ_KRANK})
                UNION SELECT employee_id, 'U' FROM vacation_requests WHERE status = 'approved' AND :d BETWEEN start_date AND end_date
                UNION SELECT employee_id, 'K' FROM sick_notes WHERE coalesce(status,'') <> 'rejected' AND :d BETWEEN start_date AND end_date) x
          JOIN employees e ON e.id = x.employee_id
         WHERE NOT coalesce(e.is_test,false) AND {_flt('e.id', emp)} ORDER BY name""", **p)

    m0, m1 = _month_bounds(today)
    mon = _q(db, f"""
        SELECT t.check_in, t.check_out, t.billed_hours,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
          FROM time_entries t JOIN employees e ON e.id = t.employee_id
         WHERE t.check_in::date BETWEEN :a AND :b AND NOT coalesce(e.is_test,false)
           AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('t.object_id', obj)}""",
              **_params(obj, emp, a=m0, b=m1))
    offen = _offene_punkte(db, obj, emp)
    kennzahlen = {
        "anwesend": sum(1 for r in rows if r["status"] == "da") + sum(1 for r in ohne_schicht if r["status"] == "da"),
        "geplant": len(rows),
        "fehlt": sum(1 for r in rows if r["status"] in ("fehlt", "offen")),
        "zu_genehmigen": len(offen),
        "stunden_monat": round(sum(_net_hours(t["check_in"], t["check_out"], t["billed_hours"], t["brk"]) for t in mon), 1),
        "einsaetze_monat": len(mon),
    }
    return {"datum": today.isoformat(), "uhrzeit": now.strftime("%H:%M"), "kennzahlen": kennzahlen, "schichten": rows,
            "ohne_schicht": ohne_schicht, "abwesend": [dict(a) for a in abwesend],
            "offen": offen}


def _offene_punkte(db, obj, emp):
    p = _params(obj, emp)
    items = []
    for r in _q(db, f"""
        SELECT p.id, p.employee_id, p.date, p.start_time, p.end_time, p.requested_hours, p.catch_up_type, p.reason,
               p.notes, o.name AS objekt, e.first_name || ' ' || e.last_name AS name, p.created_at
          FROM pending_bookings p JOIN employees e ON e.id = p.employee_id LEFT JOIN objects o ON o.id = p.object_id
         WHERE p.status = 'offen' AND {_flt('p.object_id', obj)} ORDER BY p.created_at""", **p):
        items.append({"typ": "nachtrag" if r["catch_up_type"] or r["reason"] else "genehmigung", "id": r["id"],
                      "titel": "Nachtrag" if r["catch_up_type"] or r["reason"] else "Selbstbuchung",
                      "name": r["name"], "employee_id": r["employee_id"],
                      "text": f"{r['date']:%d.%m.} {_hm(r['start_time'])}–{_hm(r['end_time'])}, {r['objekt'] or '-'}, "
                              f"{float(r['requested_hours'] or 0):.2f} h".replace(".", ",", 1) if r["date"] else (r["notes"] or ""),
                      "notiz": r["notes"], "seit": r["created_at"].isoformat() if r["created_at"] else None,
                      "aktionen": ["genehmigen", "ablehnen"]})
    for r in _q(db, f"""
        SELECT v.id, v.employee_id, v.start_date, v.end_date, v.working_days, v.type, v.requested_at,
               e.first_name || ' ' || e.last_name AS name
          FROM vacation_requests v JOIN employees e ON e.id = v.employee_id
         WHERE v.status = 'pending' AND {_flt('v.employee_id', emp)} ORDER BY v.requested_at""", **p):
        items.append({"typ": "urlaub", "id": r["id"], "titel": "Urlaubsantrag", "name": r["name"],
                      "employee_id": r["employee_id"],
                      "text": f"{r['start_date']:%d.%m.}–{r['end_date']:%d.%m.%Y}, {r['working_days'] or 0:g} Arbeitstage",
                      "seit": r["requested_at"].isoformat() if r["requested_at"] else None,
                      "aktionen": ["genehmigen", "ablehnen"]})
    for r in _q(db, f"""
        SELECT r.id, r.employee_id, r.request_type, r.requested_date, r.reason, r.created_at,
               e.first_name || ' ' || e.last_name AS name
          FROM shift_change_requests r JOIN employees e ON e.id = r.employee_id
         WHERE r.status = 'pending' AND {_flt('r.employee_id', emp)} ORDER BY r.created_at""", **p):
        items.append({"typ": "schichtwunsch", "id": r["id"], "titel": "Schichtänderung", "name": r["name"],
                      "employee_id": r["employee_id"],
                      "text": f"{r['request_type'] or ''} {r['requested_date'] or ''} {r['reason'] or ''}".strip(),
                      "seit": r["created_at"].isoformat() if r["created_at"] else None,
                      "aktionen": ["genehmigen", "ablehnen"]})
    for r in _q(db, f"""
        SELECT m.id, m.sender_employee_id AS employee_id, m.subject, m.body, m.category, m.created_at,
               e.first_name || ' ' || e.last_name AS name
          FROM messages m JOIN employees e ON e.id = m.sender_employee_id
         WHERE m.parent_id IS NULL AND m.status = 'neu' AND {_flt('m.sender_employee_id', emp)}
         ORDER BY m.created_at""", **p):
        items.append({"typ": "nachricht", "id": r["id"], "titel": "Nachricht", "name": r["name"],
                      "employee_id": r["employee_id"],
                      "text": (r["subject"] or r["category"] or "") + (": " if r["subject"] else "") + (r["body"] or "")[:160],
                      "seit": r["created_at"].isoformat() if r["created_at"] else None,
                      "aktionen": ["antworten", "gelesen"]})
    return items


@router.post("/aktion/{typ}/{item_id}")
def aktion(typ: str, item_id: int, data: dict = None, db: Session = Depends(get_db),
           user=Depends(verify_admin_or_objektleiter)):
    """Aktionsknopf aus der Heute-Liste. Prueft den Sichtbereich, dann bestehende Logik."""
    data = data or {}
    akt = data.get("aktion")
    if typ in ("genehmigung", "nachtrag"):
        row = _q(db, "SELECT employee_id, object_id FROM pending_bookings WHERE id = :i", i=item_id)
        if not row:
            raise HTTPException(404, "Antrag nicht gefunden")
        ol_scope.require_object(db, user, row[0]["object_id"])
        from app.services.pending_booking_service import approve_pending_booking, reject_pending_booking, \
            PendingBookingError
        try:
            if akt == "genehmigen":
                return approve_pending_booking(db, item_id, {}, user.id)
            if akt == "ablehnen":
                return reject_pending_booking(db, item_id, {"admin_notes": data.get("text", "")}, user.id)
        except PendingBookingError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)
    elif typ == "urlaub":
        row = _q(db, "SELECT employee_id FROM vacation_requests WHERE id = :i", i=item_id)
        if not row:
            raise HTTPException(404, "Antrag nicht gefunden")
        ol_scope.require_employee(db, user, row[0]["employee_id"])
        from app.api.v1.endpoints.vacation import process_vacation_request
        if akt in ("genehmigen", "ablehnen"):
            return process_vacation_request(item_id, {"status": "approved" if akt == "genehmigen" else "rejected"},
                                            db=db, admin=user)
    elif typ == "schichtwunsch":
        row = _q(db, "SELECT employee_id FROM shift_change_requests WHERE id = :i", i=item_id)
        if not row:
            raise HTTPException(404, "Anfrage nicht gefunden")
        ol_scope.require_employee(db, user, row[0]["employee_id"])
        from app.api.v1.endpoints.admin import process_shift_request
        if akt in ("genehmigen", "ablehnen"):
            return process_shift_request(item_id, {"status": "approved" if akt == "genehmigen" else "rejected",
                                                   "admin_response": data.get("text", "")}, db=db, admin=user)
    elif typ == "nachricht":
        row = _q(db, "SELECT sender_employee_id AS employee_id, status FROM messages WHERE id = :i", i=item_id)
        if not row:
            raise HTTPException(404, "Nachricht nicht gefunden")
        ol_scope.require_employee(db, user, row[0]["employee_id"])
        if akt == "gelesen":
            db.execute(text("UPDATE messages SET status = 'gelesen' WHERE id = :i AND status = 'neu'"), {"i": item_id})
            log_audit(db, user.id, row[0]["employee_id"], "message_status_changed", entity_type="message",
                      entity_id=item_id, old_value={"status": row[0]["status"]}, new_value={"status": "gelesen"},
                      details=f"Nachricht {item_id} im Cockpit als gelesen markiert")
            db.commit()
            return {"status": "gelesen"}
        if akt == "ungelesen":
            db.execute(text("UPDATE messages SET status = 'neu' WHERE id = :i AND status = 'gelesen'"), {"i": item_id})
            log_audit(db, user.id, row[0]["employee_id"], "message_status_changed", entity_type="message",
                      entity_id=item_id, old_value={"status": "gelesen"}, new_value={"status": "neu"},
                      details=f"Nachricht {item_id} im Cockpit wieder auf ungelesen (Rueckgaengig)")
            db.commit()
            return {"status": "neu"}
        if akt == "antworten":
            from app.api.v1.endpoints.messages import reply_to_message
            return reply_to_message(item_id, {"body": data.get("text", "")}, db=db, admin=user)
    raise HTTPException(400, "Unbekannte Aktion")


@router.get("/dienstplan")
def dienstplan(start: str = Query(None), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, emp = _scope(db, user)
    d0 = date.fromisoformat(start) if start else date.today()
    d0 = d0 - timedelta(days=d0.weekday())
    rows = _q(db, f"""
        SELECT s.id, s.date, s.start_time, s.end_time, s.status, s.is_driver, s.object_id, o.name AS objekt,
               s.employee_id, e.first_name || ' ' || e.last_name AS name, e.personal_nr
          FROM schedules s JOIN employees e ON e.id = s.employee_id LEFT JOIN objects o ON o.id = s.object_id
         WHERE s.date BETWEEN :a AND :b AND NOT coalesce(e.is_test,false) AND {_flt('s.object_id', obj)}
         ORDER BY s.date, s.start_time, name""", **_params(obj, emp, a=d0, b=d0 + timedelta(days=6)))
    tage = [{"datum": (d0 + timedelta(days=i)).isoformat(), "tag": WOCHENTAG[i],
             "schichten": []} for i in range(7)]
    for r in rows:
        tage[(r["date"] - d0).days]["schichten"].append({
            "id": r["id"], "name": r["name"], "personal_nr": r["personal_nr"], "employee_id": r["employee_id"],
            "objekt": "Urlaub" if r["object_id"] == OBJ_URLAUB else ("Krank" if r["object_id"] == OBJ_KRANK else r["objekt"]),
            "beginn": _hm(r["start_time"]), "ende": _hm(r["end_time"]), "status": r["status"],
            "fahrer": bool(r["is_driver"]), "object_id": r["object_id"]})
    return {"start": d0.isoformat(), "tage": tage}


@router.get("/mitarbeiter")
def mitarbeiter(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, emp = _scope(db, user)
    rows = _q(db, f"""
        SELECT e.id, e.personal_nr, e.first_name, e.last_name, e.is_active, u.category,
               (SELECT string_agg(o.name, ', ' ORDER BY o.name) FROM employee_object_assignments a
                  JOIN objects o ON o.id = a.object_id
                 WHERE a.employee_id = e.id AND coalesce(a.is_active,true) AND {_flt('a.object_id', obj)}) AS objekte
          FROM employees e JOIN users u ON u.id = e.user_id
         WHERE NOT coalesce(e.is_test,false) AND u.role = 'MITARBEITER' AND {_flt('e.id', emp)}
         ORDER BY e.is_active DESC, e.last_name, e.first_name""", **_params(obj, emp))
    return [dict(r) for r in rows]


def _month_bounds(today):
    first = today.replace(day=1)
    return first, today.replace(day=monthrange(today.year, today.month)[1])


@router.get("/mitarbeiter/{employee_id}")
def akte(employee_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    ol_scope.require_employee(db, user, employee_id)
    obj, _ = _scope(db, user)
    e = _q(db, """SELECT e.*, u.email, u.category, u.is_active AS login_aktiv FROM employees e
                  JOIN users u ON u.id = e.user_id WHERE e.id = :i""", i=employee_id)
    if not e:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    e = e[0]
    today = date.today()
    m0, m1 = _month_bounds(today)
    p = _params(obj, None, i=employee_id, a=m0, b=m1, d=today, y=today.year)
    stamm = {"id": e["id"], "personal_nr": e["personal_nr"], "name": f"{e['first_name']} {e['last_name']}",
             "email": e["email"], "adresse": e["address"], "kategorie": e["category"],
             "stempelart": {"A": "Automatisch", "B": "Knopf", "C": "Auto-Stempel"}.get(e["tracking_mode"], e["tracking_mode"]),
             "aktiv": bool(e["is_active"]), "beschaeftigung": e["employment_type"],
             "telegram": bool(e["telegram_chat_id"]), "seit": e["created_at"].date().isoformat() if e["created_at"] else None}
    if ol_scope.is_manager(user):
        stamm["stundenlohn"] = e["hourly_rate"]
    objekte = _q(db, f"""
        SELECT a.id, a.object_id, o.name, a.tracking_category, a.is_driver, a.is_active, k.distance_km
          FROM employee_object_assignments a JOIN objects o ON o.id = a.object_id
          LEFT JOIN km_distances k ON k.employee_id = a.employee_id AND k.object_id = a.object_id
         WHERE a.employee_id = :i AND coalesce(a.is_active,true) AND {_flt('a.object_id', obj)}
         ORDER BY o.name""", **p)
    plan = _q(db, f"""
        SELECT s.id, s.date, s.start_time, s.end_time, s.status, s.object_id, o.name AS objekt
          FROM schedules s LEFT JOIN objects o ON o.id = s.object_id
         WHERE s.employee_id = :i AND s.date BETWEEN :d AND :d + 13
           AND (s.object_id IN ({OBJ_URLAUB},{OBJ_KRANK}) OR {_flt('s.object_id', obj)})
         ORDER BY s.date, s.start_time""", **p)
    te = _q(db, f"""
        SELECT t.check_in, t.check_out, t.billed_hours, t.object_id,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
          FROM time_entries t
         WHERE t.employee_id = :i AND t.check_in::date BETWEEN :a AND :b
           AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('t.object_id', obj)}""", **p)
    km = _q(db, f"""
        SELECT coalesce(sum(distance_km),0) AS km, coalesce(sum(amount),0) AS betrag, count(*) AS fahrten
          FROM km_daily_entries k
         WHERE k.employee_id = :i AND k.date BETWEEN :a AND :b AND k.is_longest_trip AND k.is_billable
           AND {_flt('k.object_id', obj)}""", **_params(obj, None, i=employee_id, a=m0, b=m1))[0]
    url = _q(db, "SELECT days_entitled, days_taken, days_remaining FROM vacation_entitlements WHERE employee_id = :i AND year = :y", **p)
    antraege = _q(db, """SELECT id, start_date, end_date, working_days, status FROM vacation_requests
                         WHERE employee_id = :i AND (end_date >= :d - 60) ORDER BY start_date DESC LIMIT 8""", **p)
    return {
        "stamm": stamm,
        "objekte": [{**dict(o), "distance_km": float(o["distance_km"]) if o["distance_km"] is not None else None,
                     "km_fehlt": o["distance_km"] is None} for o in objekte],
        "plan": [{"id": s["id"], "datum": s["date"].isoformat(), "tag": WOCHENTAG[s["date"].weekday()],
                  "beginn": _hm(s["start_time"]), "ende": _hm(s["end_time"]),
                  "objekt": "Urlaub" if s["object_id"] == OBJ_URLAUB else ("Krank" if s["object_id"] == OBJ_KRANK else s["objekt"])}
                 for s in plan],
        "monat": {"von": m0.isoformat(), "bis": m1.isoformat(), "einsaetze": len(te),
                  "stunden": round(sum(_net_hours(t["check_in"], t["check_out"], t["billed_hours"], t["brk"]) for t in te), 2),
                  "km": float(km["km"]), "km_betrag": float(km["betrag"]) if ol_scope.is_manager(user) else None,
                  "fahrten": km["fahrten"]},
        "urlaub": {"jahr": today.year, **({k: float(v or 0) for k, v in url[0].items()} if url else
                                          {"days_entitled": 0, "days_taken": 0, "days_remaining": 0}),
                   "antraege": [{"id": a["id"], "von": a["start_date"].isoformat(), "bis": a["end_date"].isoformat(),
                                 "tage": a["working_days"], "status": a["status"]} for a in antraege]},
    }


@router.post("/mitarbeiter/{employee_id}/objekte")
def objekt_zuteilen(employee_id: int, data: dict, db: Session = Depends(get_db),
                    user=Depends(verify_admin_or_objektleiter)):
    """Objekt zuteilen. Fehlt die KM-Strecke MA->Objekt, antwortet 409 (km_fehlt), bis distance_km mitkommt."""
    ol_scope.require_employee(db, user, employee_id)
    object_id = data.get("object_id")
    ol_scope.require_object(db, user, object_id)
    if not _q(db, "SELECT 1 FROM objects WHERE id = :o", o=object_id):
        raise HTTPException(404, "Objekt nicht gefunden")
    kat = (data.get("tracking_category") or "B").upper()
    if kat not in ("A", "B", "C"):
        raise HTTPException(400, "Kategorie A, B oder C")
    exists = _q(db, """SELECT id, coalesce(is_active,true) AS aktiv FROM employee_object_assignments
                       WHERE employee_id = :e AND object_id = :o""", e=employee_id, o=object_id)
    if exists and exists[0]["aktiv"]:
        raise HTTPException(409, detail={"code": "schon_zugeteilt", "text": "Objekt ist bereits zugeteilt"})
    km = _q(db, "SELECT distance_km FROM km_distances WHERE employee_id = :e AND object_id = :o", e=employee_id, o=object_id)
    neu_km = None
    if not km:
        dist = data.get("distance_km")
        if dist in (None, ""):
            raise HTTPException(409, detail={"code": "km_fehlt",
                                             "text": "Für dieses Objekt ist keine KM-Strecke hinterlegt"})
        try:
            dist = round(float(str(dist).replace(",", ".")), 1)
        except ValueError:
            raise HTTPException(400, "KM-Strecke ist keine Zahl")
        if dist < 0 or dist > 300:
            raise HTTPException(400, "KM-Strecke muss zwischen 0 und 300 liegen")
        neu_km = db.execute(text("""INSERT INTO km_distances (employee_id, object_id, distance_km, rate_per_km, created_at)
                                    VALUES (:e, :o, :k, 0.30, now()) RETURNING id"""),
                            {"e": employee_id, "o": object_id, "k": dist}).scalar()
        log_audit(db, user.id, employee_id, "km_distance_created", entity_type="km_distance", entity_id=neu_km,
                  new_value={"object_id": object_id, "distance_km": dist},
                  details=f"KM-Strecke {dist} km beim Zuteilen im Cockpit hinterlegt")
    if exists:
        db.execute(text("""UPDATE employee_object_assignments SET is_active = true, tracking_category = :k,
                           is_driver = :d WHERE id = :i"""), {"k": kat, "d": bool(data.get("is_driver", True)), "i": exists[0]["id"]})
        aid = exists[0]["id"]
    else:
        aid = db.execute(text("""INSERT INTO employee_object_assignments
                                 (employee_id, object_id, role, is_driver, is_active, tracking_category, created_at)
                                 VALUES (:e, :o, 'mitarbeiter', :d, true, :k, now()) RETURNING id"""),
                         {"e": employee_id, "o": object_id, "d": bool(data.get("is_driver", True)), "k": kat}).scalar()
    log_audit(db, user.id, employee_id, "assignment_created", entity_type="assignment", entity_id=aid,
              new_value={"object_id": object_id, "tracking_category": kat},
              details=f"Objekt {object_id} im Cockpit zugeteilt")
    db.commit()
    return {"status": "zugeteilt", "assignment_id": aid, "km_distance_id": neu_km}


@router.get("/objekte")
def objekte(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, _ = _scope(db, user)
    today = date.today()
    rows = _q(db, f"""
        SELECT o.id, o.name, o.address, o.is_active, c.name AS kunde,
               (SELECT count(*) FROM employee_object_assignments a WHERE a.object_id = o.id AND coalesce(a.is_active,true)) AS ma,
               (SELECT count(*) FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id
                 WHERE a.object_id = o.id AND coalesce(a.is_active,true) AND coalesce(a.is_driver,false) AND e.is_active
                   AND NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = o.id)) AS ohne_km,
               (SELECT count(*) FROM schedules s WHERE s.object_id = o.id AND s.date = :d
                  AND s.status IN ('normal','vertretung')) AS schichten_heute
          FROM objects o LEFT JOIN customers c ON c.id = o.customer_id
         WHERE NOT coalesce(o.is_test,false) AND o.id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('o.id', obj)}
         ORDER BY o.is_active DESC, o.name""", **_params(obj, None, d=today))
    return [dict(r) for r in rows]


PRUEF_SQL = {
    "gehen_vor_kommen": "t.check_out < t.check_in",
    "negative_stunden": "t.billed_hours < 0",
    "ohne_gehen": "t.check_out IS NULL AND t.check_in < now() - interval '14 hours'",
}
PRUEF_SQL["alle"] = "(" + " OR ".join(f"({v})" for v in PRUEF_SQL.values()) + ")"


def _zeile(r):
    hint = []
    if r["check_out"] is None:
        hint.append("ohne Gehen")
    elif r["check_out"] < r["check_in"]:
        hint.append("Gehen vor Kommen")
    if r["billed_hours"] is not None and r["billed_hours"] < 0:
        hint.append("negative Stunden")
    return {"id": r["id"], "datum": r["check_in"].date().isoformat(), "name": r["name"], "personal_nr": r["personal_nr"],
            "employee_id": r["employee_id"], "object_id": r["object_id"], "objekt": r["objekt"],
            "kommen": _hm(r["check_in"]), "gehen": _hm(r["check_out"]),
            "check_in": r["check_in"].isoformat(), "check_out": r["check_out"].isoformat() if r["check_out"] else None,
            "gehen_datum": r["check_out"].date().isoformat() if r["check_out"] else None,
            "stunden": round(_net_hours(r["check_in"], r["check_out"], r["billed_hours"], r["brk"]), 2),
            "billed_hours": r["billed_hours"], "notes": r["notes"], "service_type": r["service_type"], "schedule_id": r["schedule_id"],
            "weg": (r["notes"] or "").split(" - ")[0][:40] if r["notes"] else ("App" if r["is_manual_entry"] is False else "Manuell"),
            "hinweis": ", ".join(hint)}


_ZEIT_SELECT = f"""
        SELECT t.id, t.check_in, t.check_out, t.billed_hours, t.notes, t.is_manual_entry, t.object_id, t.service_type, t.schedule_id,
               o.name AS objekt, e.first_name || ' ' || e.last_name AS name, e.personal_nr, t.employee_id,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
          FROM time_entries t JOIN employees e ON e.id = t.employee_id LEFT JOIN objects o ON o.id = t.object_id"""


@router.get("/zeiten")
def zeiten(von: str = Query(None), bis: str = Query(None), pruef: str = Query(None), monat: str = Query(None),
           db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    d1 = date.fromisoformat(bis) if bis else date.today()
    d0 = date.fromisoformat(von) if von else d1 - timedelta(days=6)
    if pruef in PRUEF_SQL:  # Pruefpunkte: ganzer Monat (Standard: laufender), Kommen- ODER Gehen-Datum im Monat
        try:
            ref = date.fromisoformat(f"{monat}-01") if monat else date.today()
        except ValueError:
            raise HTTPException(400, "Monat als JJJJ-MM")
        d0, d1 = _month_bounds(ref)
        where = f"(t.check_in::date BETWEEN :a AND :b OR t.check_out::date BETWEEN :a AND :b) AND {PRUEF_SQL[pruef]}"
    else:
        where = "t.check_in::date BETWEEN :a AND :b"
    rows = _q(db, f"""{_ZEIT_SELECT}
         WHERE {where} AND NOT coalesce(e.is_test,false) AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
         ORDER BY t.check_in DESC""", a=d0, b=d1)
    return {"von": d0.isoformat(), "bis": d1.isoformat(), "pruef": pruef, "monat": d0.strftime("%Y-%m"),
            "eintraege": [_zeile(r) for r in rows]}


@router.get("/zeiten/{entry_id}")
def zeit(entry_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    rows = _q(db, f"{_ZEIT_SELECT} WHERE t.id = :i", i=entry_id)
    if not rows:
        raise HTTPException(404, "Buchung nicht gefunden")
    return _zeile(rows[0])


def _pruefe_zeiten(data):
    """Kommen/Gehen aus Datum + Uhrzeiten. Gehen vor Kommen = naechster Tag (Nachtschicht). Max. 16 h."""
    try:
        d = date.fromisoformat(data["datum"])
        ci = datetime.combine(d, datetime.strptime(data["kommen"], "%H:%M").time())
        co = datetime.combine(d, datetime.strptime(data["gehen"], "%H:%M").time())
    except (KeyError, ValueError):
        raise HTTPException(400, "Datum, Kommen und Gehen angeben (TT.MM.JJJJ / HH:MM)")
    if co <= ci:
        co += timedelta(days=1)
    if (co - ci) > timedelta(hours=16):
        raise HTTPException(400, "Mehr als 16 Stunden – bitte Zeiten prüfen")
    if ci > datetime.now() + timedelta(hours=1):
        raise HTTPException(400, "Kommen liegt in der Zukunft")
    return ci, co


@router.put("/zeiten/{entry_id}")
def zeit_aendern(entry_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Buchung bearbeiten. Datum gilt fuer Kommen UND Gehen (verhindert Gehen-vor-Kommen)."""
    from app.api.v1.endpoints.admin import update_booking
    ci, co = _pruefe_zeiten(data)
    body = {"check_in": ci.isoformat(), "check_out": co.isoformat()}
    for k in ("object_id", "notes", "employee_id"):
        if k in data and data[k] not in (None, ""):
            body[k] = data[k]
    update_booking(entry_id, body, db=db, admin=user)
    return zeit(entry_id, db=db, user=user)


@router.post("/zeiten")
def zeit_anlegen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import create_manual_booking
    ci, co = _pruefe_zeiten(data)
    if not data.get("employee_id") or not data.get("object_id"):
        raise HTTPException(400, "Mitarbeiter und Objekt angeben")
    r = create_manual_booking({"employee_id": int(data["employee_id"]), "object_id": int(data["object_id"]),
                               "check_in": ci.isoformat(), "check_out": co.isoformat(),
                               "check_in_time": ci.strftime("%H:%M"), "check_out_time": co.strftime("%H:%M"),
                               "service_type": data.get("service_type") or "Unterhaltsreinigung",
                               "notes": data.get("notes") or "Im Cockpit nachgetragen"}, db=db, admin=user)
    if data.get("schedule_id"):
        db.execute(text("UPDATE time_entries SET schedule_id = :s WHERE id = :i AND schedule_id IS NULL"),
                   {"s": int(data["schedule_id"]), "i": r["id"]})
        db.commit()
    return zeit(r["id"], db=db, user=user)


@router.delete("/zeiten/{entry_id}")
def zeit_loeschen(entry_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import delete_booking
    alt = zeit(entry_id, db=db, user=user)
    delete_booking(entry_id, db=db, admin=user)
    return {"status": "geloescht", "alt": alt}


@router.get("/schicht/{schedule_id}")
def schicht(schedule_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    r = _q(db, """SELECT s.id, s.date, s.start_time, s.end_time, s.employee_id, s.object_id, s.status, s.is_driver, s.notes,
                         o.name AS objekt, e.first_name || ' ' || e.last_name AS name
                    FROM schedules s JOIN employees e ON e.id = s.employee_id LEFT JOIN objects o ON o.id = s.object_id
                   WHERE s.id = :i""", i=schedule_id)
    if not r:
        raise HTTPException(404, "Schicht nicht gefunden")
    r = r[0]
    return {"id": r["id"], "datum": r["date"].isoformat(), "beginn": _hm(r["start_time"]), "ende": _hm(r["end_time"]),
            "employee_id": r["employee_id"], "object_id": r["object_id"], "status": r["status"], "fahrer": bool(r["is_driver"]),
            "notes": r["notes"], "objekt": r["objekt"], "name": r["name"]}


def _pruefe_schicht(data):
    try:
        date.fromisoformat(data["datum"])
        b = datetime.strptime(data["beginn"], "%H:%M")
        e = datetime.strptime(data["ende"], "%H:%M")
    except (KeyError, ValueError):
        raise HTTPException(400, "Datum, Beginn und Ende angeben")
    if e <= b:
        raise HTTPException(400, "Ende muss nach Beginn liegen")
    if not data.get("employee_id") or not data.get("object_id"):
        raise HTTPException(400, "Mitarbeiter und Objekt angeben")


@router.post("/dienstplan")
def schicht_anlegen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import create_schedule
    _pruefe_schicht(data)
    r = create_schedule({"employee_id": int(data["employee_id"]), "object_id": int(data["object_id"]), "date": data["datum"],
                         "start_time": data["beginn"], "end_time": data["ende"], "is_driver": bool(data.get("fahrer", True)),
                         "status": data.get("status") or "normal"}, db=db, admin=user)
    return schicht(r["id"], db=db, user=user)


@router.put("/dienstplan/{schedule_id}")
def schicht_aendern(schedule_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import update_schedule
    _pruefe_schicht(data)
    update_schedule(schedule_id, {"employee_id": int(data["employee_id"]), "object_id": int(data["object_id"]), "date": data["datum"],
                                  "start_time": data["beginn"], "end_time": data["ende"], "is_driver": bool(data.get("fahrer", True))},
                    db=db, admin=user)
    return schicht(schedule_id, db=db, user=user)


@router.delete("/dienstplan/{schedule_id}")
def schicht_loeschen(schedule_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import delete_schedule
    alt = schicht(schedule_id, db=db, user=user)
    delete_schedule(schedule_id, db=db, admin=user)
    return {"status": "geloescht", "alt": alt}


@router.get("/auswahl")
def auswahl(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Listen fuer Auswahlfelder (aktive MA, aktive Objekte)."""
    ma = _q(db, """SELECT e.id, e.first_name || ' ' || e.last_name AS name, e.personal_nr FROM employees e JOIN users u ON u.id = e.user_id
                   WHERE e.is_active AND NOT coalesce(e.is_test,false) AND u.role <> 'ADMIN' ORDER BY e.last_name, e.first_name""")
    ob = _q(db, f"""SELECT id, name FROM objects WHERE coalesce(is_active,true) AND NOT coalesce(is_test,false)
                    AND id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) ORDER BY name""")
    return {"mitarbeiter": [dict(x) for x in ma], "objekte": [dict(x) for x in ob]}


# --- Objekt-Detail -----------------------------------------------------------------------------
OBJ_EDIT = ("name", "address", "contact_person", "phone", "email", "emergency_phone", "key_location", "alarm_code",
            "special_instructions", "cleaning_days", "cleaning_interval", "notes", "is_active")
OBJ_UMSATZ = ("monthly_amount", "monthly_amount_netto", "monthly_amount_brutto", "vat_rate", "payment_terms", "invoice_day", "invoice_type")


@router.get("/objekte/{object_id}")
def objekt(object_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    o = _q(db, """SELECT o.*, c.name AS kunde, c.id AS kunde_id FROM objects o LEFT JOIN customers c ON c.id = o.customer_id
                  WHERE o.id = :i""", i=object_id)
    if not o:
        raise HTTPException(404, "Objekt nicht gefunden")
    o = o[0]
    today = date.today()
    m0, m1 = _month_bounds(today)
    stamm = {k: o[k] for k in OBJ_EDIT}
    stamm.update({"id": o["id"], "kunde": o["kunde"], "start_time": _hm(o["start_time"]), "end_time": _hm(o["end_time"]),
                  "planned_hours": float(o["planned_hours"]) if o["planned_hours"] is not None else None,
                  "radius_m": o["radius_m"] or o["radius_meters"], "gps": bool(o["gps_lat"] and o["gps_lng"]),
                  "contract_start": o["contract_start"].isoformat() if o["contract_start"] else None,
                  "contract_end": o["contract_end"].isoformat() if o["contract_end"] else None})
    if ol_scope.can_see_revenue(user):
        stamm["umsatz"] = {k: (float(o[k]) if isinstance(o[k], (int, float)) or hasattr(o[k], "is_finite") else o[k]) for k in OBJ_UMSATZ}
    ma = _q(db, """SELECT a.id, a.employee_id, e.first_name || ' ' || e.last_name AS name, a.tracking_category, a.is_driver,
                          k.id AS km_id, k.distance_km
                     FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id
                     LEFT JOIN km_distances k ON k.employee_id = a.employee_id AND k.object_id = a.object_id
                    WHERE a.object_id = :i AND coalesce(a.is_active,true) AND e.is_active ORDER BY e.last_name""", i=object_id)
    plan = _q(db, """SELECT s.id, s.date, s.start_time, s.end_time, s.employee_id, e.first_name || ' ' || e.last_name AS name
                       FROM schedules s JOIN employees e ON e.id = s.employee_id
                      WHERE s.object_id = :i AND s.date BETWEEN :d AND :d + 13 AND s.status IN ('normal','vertretung')
                      ORDER BY s.date, s.start_time""", i=object_id, d=today)
    te = _q(db, """SELECT t.check_in, t.check_out, t.billed_hours,
                          (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                            WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
                     FROM time_entries t WHERE t.object_id = :i AND t.check_in::date BETWEEN :a AND :b""", i=object_id, a=m0, b=m1)
    soll = _q(db, """SELECT coalesce(sum(planned_hours),0) AS h FROM schedules WHERE object_id = :i AND date BETWEEN :a AND :b
                     AND status IN ('normal','vertretung')""", i=object_id, a=m0, b=m1)[0]["h"]
    return {"stamm": stamm,
            "mitarbeiter": [{**dict(m), "distance_km": float(m["distance_km"]) if m["distance_km"] is not None else None} for m in ma],
            "plan": [{"id": s["id"], "datum": s["date"].isoformat(), "tag": WOCHENTAG[s["date"].weekday()], "beginn": _hm(s["start_time"]),
                      "ende": _hm(s["end_time"]), "employee_id": s["employee_id"], "name": s["name"]} for s in plan],
            "monat": {"ist": round(sum(_net_hours(t["check_in"], t["check_out"], t["billed_hours"], t["brk"]) for t in te), 1),
                      "soll": round(float(soll), 1), "einsaetze": len(te)}}


@router.put("/objekte/{object_id}")
def objekt_aendern(object_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    alt = _q(db, f"SELECT {', '.join(OBJ_EDIT)} FROM objects WHERE id = :i", i=object_id)
    if not alt:
        raise HTTPException(404, "Objekt nicht gefunden")
    neu = {k: data[k] for k in OBJ_EDIT if k in data}
    if not neu:
        raise HTTPException(400, "Keine Änderung")
    if "name" in neu and not str(neu["name"]).strip():
        raise HTTPException(400, "Name darf nicht leer sein")
    db.execute(text(f"UPDATE objects SET {', '.join(f'{k} = :{k}' for k in neu)} WHERE id = :id"), {**neu, "id": object_id})
    log_audit(db, user.id, None, "object_updated", entity_type="object", entity_id=object_id,
              old_value={k: alt[0][k] for k in neu}, new_value=neu, details=f"Objekt {object_id} im Cockpit geaendert")
    db.commit()
    return {"status": "ok", "alt": {k: alt[0][k] for k in neu}}


# --- KM-Strecken -------------------------------------------------------------------------------
@router.get("/km-strecken")
def km_strecken(fehlend: bool = Query(False), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Alle Zuweisungen MA->Objekt mit hinterlegter (oder fehlender) KM-Strecke."""
    rows = _q(db, f"""
        SELECT a.employee_id, e.first_name || ' ' || e.last_name AS name, e.personal_nr, a.object_id, o.name AS objekt,
               coalesce(a.is_driver,false) AS fahrer, k.id AS km_id, k.distance_km
          FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id JOIN objects o ON o.id = a.object_id
          LEFT JOIN km_distances k ON k.employee_id = a.employee_id AND k.object_id = a.object_id
         WHERE coalesce(a.is_active,true) AND e.is_active AND NOT coalesce(e.is_test,false) AND coalesce(o.is_active,true)
           AND a.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) {"AND k.id IS NULL AND coalesce(a.is_driver,false)" if fehlend else ""}
         ORDER BY e.last_name, o.name""")
    return [{**dict(r), "distance_km": float(r["distance_km"]) if r["distance_km"] is not None else None} for r in rows]


@router.put("/km-strecken")
def km_strecke_setzen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        emp, obj = int(data["employee_id"]), int(data["object_id"])
        dist = round(float(str(data["distance_km"]).replace(",", ".")), 1)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "Mitarbeiter, Objekt und KM angeben")
    if dist < 0 or dist > 300:
        raise HTTPException(400, "KM-Strecke muss zwischen 0 und 300 liegen")
    alt = _q(db, "SELECT id, distance_km FROM km_distances WHERE employee_id = :e AND object_id = :o", e=emp, o=obj)
    if alt:
        db.execute(text("UPDATE km_distances SET distance_km = :k, updated_at = now() WHERE id = :i"), {"k": dist, "i": alt[0]["id"]})
        kid, action, old = alt[0]["id"], "km_distance_changed", {"distance_km": float(alt[0]["distance_km"])}
    else:
        kid = db.execute(text("""INSERT INTO km_distances (employee_id, object_id, distance_km, rate_per_km, created_at)
                                 VALUES (:e, :o, :k, 0.30, now()) RETURNING id"""), {"e": emp, "o": obj, "k": dist}).scalar()
        action, old = "km_distance_created", None
    log_audit(db, user.id, emp, action, entity_type="km_distance", entity_id=kid, old_value=old,
              new_value={"object_id": obj, "distance_km": dist}, details=f"KM-Strecke im Cockpit: {dist} km")
    db.commit()
    return {"id": kid, "distance_km": dist, "alt": old}


# --- Abrechnung --------------------------------------------------------------------------------
@router.get("/abrechnung")
def abrechnung(year: int = Query(...), month: int = Query(...), db: Session = Depends(get_db),
               user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import get_lohn_uebersicht
    from app.services.export_termine import exporttag
    rows = get_lohn_uebersicht(year, month, db=db, current_user=user)
    conf = {r["employee_id"]: r["status"] for r in _q(db, "SELECT employee_id, status FROM monthly_confirmations WHERE year = :y AND month = :m",
                                                       y=year, m=month)}
    m0 = date(year, month, 1)
    m1 = date(year, month, monthrange(year, month)[1])
    pruef = {r["employee_id"]: r["n"] for r in _q(db, """SELECT employee_id, count(*) AS n FROM time_entries
        WHERE (check_in::date BETWEEN :a AND :b OR check_out::date BETWEEN :a AND :b)
          AND (check_out < check_in OR billed_hours < 0 OR (check_out IS NULL AND check_in < now() - interval '14 hours'))
        GROUP BY 1""", a=m0, b=m1)}
    out = [{**r, "bestaetigung": conf.get(r["employee_id"]), "pruefpunkte": pruef.get(r["employee_id"], 0)} for r in rows]
    return {"monat": f"{year}-{month:02d}", "exporttag": exporttag(f"{year}-{month:02d}").isoformat(), "zeilen": out,
            "summe": {k: round(sum((r.get(k) or 0) for r in rows), 2) for k in
                      ("normal_hours", "sonder_hours", "sonntag_hours", "feiertag_hours", "urlaub_hours", "km_amount", "gesamt")}}


@router.delete("/mitarbeiter/{employee_id}/objekte/{assignment_id}")
def objekt_entziehen(employee_id: int, assignment_id: int, db: Session = Depends(get_db),
                     user=Depends(verify_admin_or_objektleiter)):
    """Zuteilung beenden (auch Rueckgaengig nach dem Zuteilen). KM-Strecke bleibt hinterlegt."""
    ol_scope.require_employee(db, user, employee_id)
    row = _q(db, "SELECT object_id FROM employee_object_assignments WHERE id = :i AND employee_id = :e",
             i=assignment_id, e=employee_id)
    if not row:
        raise HTTPException(404, "Zuteilung nicht gefunden")
    ol_scope.require_object(db, user, row[0]["object_id"])
    db.execute(text("UPDATE employee_object_assignments SET is_active = false WHERE id = :i"), {"i": assignment_id})
    log_audit(db, user.id, employee_id, "assignment_deactivated", entity_type="assignment", entity_id=assignment_id,
              old_value={"is_active": True}, new_value={"is_active": False},
              details=f"Zuteilung Objekt {row[0]['object_id']} im Cockpit beendet")
    db.commit()
    return {"status": "beendet"}


# --- Branding (Produktfaehigkeit: Name, Logo, Farben, Schriften aus einer Einstellung) ---------
# Neutrale Vorgaben (stampo24); der Firmen-Look steht nur in der Einstellung, nicht im Code.
#   akzent      Hauptfarbe (Links, aktive Navigation, Kennzahlen)
#   cta         Aktionsfarbe fuer Haupt-Knoepfe, cta_text = Schrift darauf
#   leiste      Hintergrund Seitenleiste / Handy-Kopfzeile, leiste_text = Schrift darauf
#   schrift_css lokale Schriftdatei (nur Pfad auf diesem Server), schrift_titel / schrift_text = Familiennamen
BRANDING_DEFAULT = {"firma": "SEDA24", "produkt": "stampo24", "logo_url": "", "akzent": "#2563eb", "sprache": "de",
                    "cta": "", "cta_text": "", "leiste": "", "leiste_text": "",
                    "schrift_css": "", "schrift_titel": "", "schrift_text": ""}
BRANDING_FARBEN = ("akzent", "cta", "cta_text", "leiste", "leiste_text")


def _settings_table(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS app_settings (key varchar(50) PRIMARY KEY, value text NOT NULL,
                       updated_at timestamp DEFAULT now(), updated_by integer)"""))


@router.get("/branding")
def branding(db: Session = Depends(get_db)):
    import json
    _settings_table(db)
    row = db.execute(text("SELECT value FROM app_settings WHERE key = 'branding'")).fetchone()
    db.commit()
    return {**BRANDING_DEFAULT, **(json.loads(row[0]) if row else {})}


@router.put("/branding")
def branding_speichern(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    import json, re
    if not ol_scope.is_manager(user):
        raise HTTPException(403, "Kein Zugriff")
    neu = {k: str(data[k]).strip()[:120] for k in BRANDING_DEFAULT if k in data}
    if "akzent" in neu and not re.fullmatch(r"#[0-9a-fA-F]{6}", neu["akzent"]):
        raise HTTPException(400, "Akzentfarbe als #RRGGBB")
    for k in BRANDING_FARBEN[1:]:
        if neu.get(k) and not re.fullmatch(r"#[0-9a-fA-F]{6}", neu[k]):
            raise HTTPException(400, f"Farbe '{k}' als #RRGGBB oder leer")
    if neu.get("schrift_css") and not re.fullmatch(r"/[A-Za-z0-9_./-]+\.css", neu["schrift_css"]):
        raise HTTPException(400, "Schriftdatei nur als lokaler Pfad, z. B. /brand/firma/fonts/fonts.css")
    for k in ("schrift_titel", "schrift_text"):
        if neu.get(k) and not re.fullmatch(r"[A-Za-z0-9 -]{1,60}", neu[k]):
            raise HTTPException(400, f"Schriftname '{k}' nur Buchstaben, Ziffern, Leerzeichen")
    if neu.get("logo_url") and not re.fullmatch(r"(/|https://)[^\s\"'<>()]+", neu["logo_url"]):
        raise HTTPException(400, "Logo als lokaler Pfad (/...) oder https-Adresse")
    _settings_table(db)
    alt = db.execute(text("SELECT value FROM app_settings WHERE key = 'branding'")).fetchone()
    wert = {**BRANDING_DEFAULT, **(json.loads(alt[0]) if alt else {}), **neu}
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES ('branding', :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"v": json.dumps(wert), "u": user.id})
    log_audit(db, user.id, None, "branding_updated", entity_type="setting", old_value=json.loads(alt[0]) if alt else None,
              new_value=wert, details="Branding im Cockpit geaendert")
    db.commit()
    return wert


# --- Leitstelle: alles auf einen Blick -----------------------------------------------------------
WT_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _abwesend_map(db, d0, d1):
    """{(employee_id, datum): 'Urlaub'|'Krank'} fuer den Zeitraum."""
    rows = _q(db, f"""
        SELECT employee_id, date AS d, CASE WHEN object_id = {OBJ_KRANK} THEN 'Krank' ELSE 'Urlaub' END AS grund
          FROM schedules WHERE date BETWEEN :a AND :b AND object_id IN ({OBJ_URLAUB},{OBJ_KRANK})
        UNION
        SELECT v.employee_id, g::date, 'Urlaub' FROM vacation_requests v,
               generate_series(greatest(v.start_date, :a), least(v.end_date, :b), interval '1 day') g
         WHERE v.status = 'approved' AND v.end_date >= :a AND v.start_date <= :b
        UNION
        SELECT s.employee_id, g::date, 'Krank' FROM sick_notes s,
               generate_series(greatest(s.start_date, :a), least(s.end_date, :b), interval '1 day') g
         WHERE coalesce(s.status,'') <> 'rejected' AND s.end_date >= :a AND s.start_date <= :b""", a=d0, b=d1)
    out = {}
    for r in rows:
        if out.get((r["employee_id"], r["d"])) != "Krank":
            out[(r["employee_id"], r["d"])] = r["grund"]
    return out


@router.get("/leitstelle")
def leitstelle(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.services.export_termine import exporttag
    today = date.today()
    now = datetime.now()
    m0, m1 = _month_bounds(today)
    names = {r["id"]: r["name"] for r in _q(db, """SELECT id, first_name || ' ' || last_name AS name FROM employees""")}

    # 2) Woche: Schichten, Luecken, Urlaub/Krank
    w1 = today + timedelta(days=6)
    abw = _abwesend_map(db, today, w1)
    sched = _q(db, f"""SELECT s.id, s.date, s.employee_id, s.object_id, s.start_time, o.name AS objekt FROM schedules s
                       JOIN employees e ON e.id = s.employee_id LEFT JOIN objects o ON o.id = s.object_id
                       WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND NOT coalesce(e.is_test,false)
                         AND coalesce(s.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})""", a=today, b=w1)
    # Ueblicher Rhythmus: Objekt war in den letzten 8 Wochen an diesem Wochentag mind. 3x besetzt
    rhythmus = _q(db, f"""SELECT s.object_id, extract(isodow FROM s.date)::int - 1 AS wd, o.name, count(DISTINCT s.date) AS n
                          FROM schedules s JOIN objects o ON o.id = s.object_id
                          WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND coalesce(o.is_active,true)
                            AND NOT coalesce(o.is_test,false) AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                          GROUP BY 1, 2, 3 HAVING count(DISTINCT s.date) >= 3""", a=today - timedelta(days=56), b=today - timedelta(days=1))
    woche = []
    for i in range(7):
        d = today + timedelta(days=i)
        day_s = [s for s in sched if s["date"] == d]
        besetzt = {s["object_id"] for s in day_s}
        luecken = [{"typ": "unbesetzt", "object_id": r["object_id"], "objekt": r["name"],
                    "text": f"{r['name']}: keine Schicht (sonst {WT_KURZ[d.weekday()]} besetzt)"}
                   for r in rhythmus if r["wd"] == d.weekday() and r["object_id"] not in besetzt]
        luecken += [{"typ": "abwesend", "object_id": s["object_id"], "schicht_id": s["id"], "employee_id": s["employee_id"],
                     "objekt": s["objekt"], "text": f"{s['objekt']}: {names.get(s['employee_id'])} hat {abw[(s['employee_id'], d)]}"}
                    for s in day_s if (s["employee_id"], d) in abw]
        weg = [{"employee_id": k[0], "name": names.get(k[0]), "grund": v} for k, v in abw.items() if k[1] == d]
        woche.append({"datum": d.isoformat(), "tag": WT_KURZ[d.weekday()], "schichten": len(day_s), "luecken": luecken,
                      "urlaub": [x for x in weg if x["grund"] == "Urlaub"], "krank": [x for x in weg if x["grund"] == "Krank"]})

    # 3) Monatsabschluss
    monat = today.strftime("%Y-%m")
    ex = exporttag(monat)
    aktive_ma = _q(db, f"""SELECT DISTINCT s.employee_id FROM schedules s JOIN employees e ON e.id = s.employee_id
                           WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND NOT coalesce(e.is_test,false)
                             AND coalesce(s.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})""", a=m0, b=m1)
    bestaetigt = _q(db, "SELECT count(*) AS n FROM monthly_confirmations WHERE year = :y AND month = :m AND status = 'confirmed'",
                    y=today.year, m=today.month)[0]["n"]
    te_mon = """FROM time_entries t JOIN employees e ON e.id = t.employee_id
                WHERE NOT coalesce(e.is_test,false) AND (t.check_in::date BETWEEN :a AND :b OR t.check_out::date BETWEEN :a AND :b)"""
    p_gvk = _q(db, f"SELECT count(*) AS n {te_mon} AND t.check_out < t.check_in", a=m0, b=m1)[0]["n"]
    p_neg = _q(db, f"SELECT count(*) AS n {te_mon} AND t.billed_hours < 0", a=m0, b=m1)[0]["n"]
    p_ohne = _q(db, f"SELECT count(*) AS n {te_mon} AND t.check_out IS NULL AND t.check_in < now() - interval '14 hours'", a=m0, b=m1)[0]["n"]
    p_km = _q(db, """SELECT count(*) AS n FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id
                     WHERE coalesce(a.is_active,true) AND coalesce(a.is_driver,false) AND e.is_active AND NOT coalesce(e.is_test,false)
                       AND a.object_id NOT IN (19, 999)
                       AND NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = a.object_id)""")[0]["n"]
    p_nach = _q(db, "SELECT count(*) AS n FROM pending_bookings WHERE status = 'offen'")[0]["n"]
    pruef = [
        {"key": "gehen_vor_kommen", "n": p_gvk, "link": "/cockpit/zeiten?pruef=gehen_vor_kommen"},
        {"key": "negative_stunden", "n": p_neg, "link": "/cockpit/zeiten?pruef=negative_stunden"},
        {"key": "ohne_gehen", "n": p_ohne, "link": "/cockpit/zeiten?pruef=ohne_gehen"},
        {"key": "km_fehlt", "n": p_km, "link": "/cockpit/objekte?pruef=km_fehlt"},
        {"key": "nachtraege", "n": p_nach, "link": "/cockpit#todo"},
    ]
    abschluss = {"monat": monat, "exporttag": ex.isoformat(), "tage_bis_export": (ex - today).days,
                 "ma_gesamt": len(aktive_ma), "ma_bestaetigt": bestaetigt, "pruefpunkte": pruef,
                 "offen_gesamt": sum(x["n"] for x in pruef)}

    # 4) Stunden je MA: Soll (Plan ganzer Monat / bis heute) und Ist
    plan = _q(db, f"""SELECT s.employee_id, s.date, s.start_time, s.end_time, s.planned_hours FROM schedules s
                      JOIN employees e ON e.id = s.employee_id
                      WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND NOT coalesce(e.is_test,false)
                        AND coalesce(s.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})""", a=m0, b=m1)
    ist = _q(db, f"""SELECT t.employee_id, t.check_in, t.check_out, t.billed_hours,
                       (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                         WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
                     FROM time_entries t JOIN employees e ON e.id = t.employee_id
                     WHERE t.check_in::date BETWEEN :a AND :b AND NOT coalesce(e.is_test,false)
                       AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})""", a=m0, b=m1)
    st = {}

    def ph(s):
        if s["planned_hours"]:
            return float(s["planned_hours"])
        if s["start_time"] and s["end_time"]:
            return max(0.0, (datetime.combine(today, s["end_time"]) - datetime.combine(today, s["start_time"])).total_seconds() / 3600)
        return 0.0
    for s in plan:
        x = st.setdefault(s["employee_id"], {"soll": 0.0, "soll_bis_heute": 0.0, "ist": 0.0})
        x["soll"] += ph(s)
        if s["date"] < today or (s["date"] == today and s["end_time"] and s["end_time"] <= now.time()):
            x["soll_bis_heute"] += ph(s)
    for tt in ist:
        x = st.setdefault(tt["employee_id"], {"soll": 0.0, "soll_bis_heute": 0.0, "ist": 0.0})
        x["ist"] += _net_hours(tt["check_in"], tt["check_out"], tt["billed_hours"], tt["brk"])
    stunden = sorted([{"employee_id": k, "name": names.get(k), **{a: round(b, 1) for a, b in v.items()}} for k, v in st.items()],
                     key=lambda r: -max(r["soll"], r["ist"]))

    # KM gesamt mit Trend (gleicher Zeitraum Vormonat)
    pm1 = m0 - timedelta(days=1)
    pm0 = pm1.replace(day=1)
    pm_bis = min(pm0 + timedelta(days=today.day - 1), pm1)
    km_q = """SELECT coalesce(sum(distance_km),0) AS km, coalesce(sum(amount),0) AS eur FROM km_daily_entries
              WHERE date BETWEEN :a AND :b AND is_longest_trip AND is_billable"""
    km_now = _q(db, km_q, a=m0, b=today)[0]
    km_prev = _q(db, km_q, a=pm0, b=pm_bis)[0]
    km_prev_full = _q(db, km_q, a=pm0, b=pm1)[0]
    km = {"km": float(km_now["km"]), "eur": float(km_now["eur"]), "vormonat_gleicher_zeitraum": float(km_prev["km"]),
          "vormonat_gesamt": float(km_prev_full["km"]),
          "trend_prozent": round((float(km_now["km"]) / float(km_prev["km"]) - 1) * 100) if km_prev["km"] else None}

    # 5) Live-Aktivitaet: Stempel + Aenderungen
    feed = []
    for r in _q(db, f"""SELECT t.id, t.employee_id, t.check_in, t.check_out, o.name AS objekt, t.is_manual_entry, t.notes
                        FROM time_entries t JOIN employees e ON e.id = t.employee_id LEFT JOIN objects o ON o.id = t.object_id
                        WHERE NOT coalesce(e.is_test,false) AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                          AND t.check_in <= now() AND (t.check_in > now() - interval '2 days' OR t.check_out > now() - interval '2 days')"""):
        auto = (r["notes"] or "").startswith(("Auto-Booking", "Automatische Buchung", "Push-Bestaetigung", "War anwesend"))
        if r["check_in"] and r["check_in"] > now - timedelta(days=2) and not auto:
            feed.append({"zeit": r["check_in"].isoformat(), "art": "kommen", "employee_id": r["employee_id"], "name": names.get(r["employee_id"]),
                         "text": r["objekt"] or "", "link": f"/cockpit/zeiten?eintrag={r['id']}"})
        if r["check_out"] and now - timedelta(days=2) < r["check_out"] <= now:
            feed.append({"zeit": r["check_out"].isoformat(), "art": "auto" if auto else "gehen", "employee_id": r["employee_id"],
                         "name": names.get(r["employee_id"]), "text": r["objekt"] or "", "link": f"/cockpit/zeiten?eintrag={r['id']}"})
    for r in _q(db, """SELECT a.id, a.created_at, a.action, a.employee_id, a.details, u.email,
                              ue.first_name || ' ' || ue.last_name AS wer
                         FROM audit_log a LEFT JOIN users u ON u.id = a.user_id LEFT JOIN employees ue ON ue.user_id = u.id
                        WHERE a.created_at > now() - interval '3 days' AND a.action NOT IN ('export_abruf', 'export_abruf_abgelehnt')
                        ORDER BY a.created_at DESC LIMIT 20"""):
        feed.append({"zeit": r["created_at"].isoformat(), "art": "aenderung", "employee_id": r["employee_id"],
                     "name": names.get(r["employee_id"]) if r["employee_id"] else None, "wer": r["wer"] or r["email"],
                     "aktion": r["action"], "text": (r["details"] or "")[:140],
                     "link": f"/cockpit/mitarbeiter/{r['employee_id']}" if r["employee_id"] else "/cockpit/einstellungen"})
    feed.sort(key=lambda x: x["zeit"], reverse=True)

    return {"woche": woche, "abschluss": abschluss, "stunden": stunden, "km": km, "feed": feed[:25]}
