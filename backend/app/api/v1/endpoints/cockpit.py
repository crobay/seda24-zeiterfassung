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
            "fahrer": bool(r["is_driver"])})
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
               (SELECT count(*) FROM employee_object_assignments a WHERE a.object_id = o.id AND coalesce(a.is_active,true)
                  AND NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = o.id)) AS ohne_km,
               (SELECT count(*) FROM schedules s WHERE s.object_id = o.id AND s.date = :d
                  AND s.status IN ('normal','vertretung')) AS schichten_heute
          FROM objects o LEFT JOIN customers c ON c.id = o.customer_id
         WHERE NOT coalesce(o.is_test,false) AND o.id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('o.id', obj)}
         ORDER BY o.is_active DESC, o.name""", **_params(obj, None, d=today))
    return [dict(r) for r in rows]


@router.get("/zeiten")
def zeiten(von: str = Query(None), bis: str = Query(None), db: Session = Depends(get_db),
           user=Depends(verify_admin_or_objektleiter)):
    obj, _ = _scope(db, user)
    d1 = date.fromisoformat(bis) if bis else date.today()
    d0 = date.fromisoformat(von) if von else d1 - timedelta(days=6)
    rows = _q(db, f"""
        SELECT t.id, t.check_in, t.check_out, t.billed_hours, t.notes, t.is_manual_entry, o.name AS objekt,
               e.first_name || ' ' || e.last_name AS name, e.personal_nr, t.employee_id,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
          FROM time_entries t JOIN employees e ON e.id = t.employee_id LEFT JOIN objects o ON o.id = t.object_id
         WHERE t.check_in::date BETWEEN :a AND :b AND NOT coalesce(e.is_test,false)
           AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('t.object_id', obj)}
         ORDER BY t.check_in DESC""", **_params(obj, None, a=d0, b=d1))
    out = []
    for r in rows:
        hint = []
        if r["check_out"] is None:
            hint.append("ohne Gehen")
        elif r["check_out"] < r["check_in"]:
            hint.append("Gehen vor Kommen")
        if r["billed_hours"] is not None and r["billed_hours"] < 0:
            hint.append("negative Stunden")
        out.append({"id": r["id"], "datum": r["check_in"].date().isoformat(), "name": r["name"],
                    "personal_nr": r["personal_nr"], "employee_id": r["employee_id"], "objekt": r["objekt"],
                    "kommen": _hm(r["check_in"]), "gehen": _hm(r["check_out"]),
                    "stunden": round(_net_hours(r["check_in"], r["check_out"], r["billed_hours"], r["brk"]), 2),
                    "weg": (r["notes"] or "").split(" - ")[0][:40] if r["notes"] else ("App" if r["is_manual_entry"] is False else "Manuell"),
                    "hinweis": ", ".join(hint)})
    return {"von": d0.isoformat(), "bis": d1.isoformat(), "eintraege": out}


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


# --- Branding (Produktfaehigkeit: Name, Logo, Akzentfarbe aus einer Einstellung) ---------------
BRANDING_DEFAULT = {"firma": "SEDA24", "produkt": "stampo24", "logo_url": "", "akzent": "#2563eb", "sprache": "de"}


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
