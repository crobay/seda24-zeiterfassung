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
from app.services import ol_scope, verspaetet, buchung_art
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


# Lohnfortzahlung (Krank) und Urlaub sind als Zeiteintrag am Objekt gebucht - in "Heute"/"Stunden je MA" kein Stempel
_KEIN_STEMPEL = "'Krank', 'Urlaub', 'Abwesenheit'"


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
           AND coalesce(t.service_type, '') NOT IN ({_KEIN_STEMPEL})
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
    # Offene Urlaubsantraege nur als eine Sammelzeile mit Link zur Antragsliste (Drazen 25.11.2026 20:25)
    u = _q(db, f"""
        SELECT count(*) AS n, min(v.requested_at) AS seit
          FROM vacation_requests v JOIN employees e ON e.id = v.employee_id
         WHERE v.status = 'pending' AND {_flt('v.employee_id', emp)}""", **p)[0]
    if u["n"]:
        items.append({"typ": "urlaub_sammel", "id": 0, "titel": f"Urlaubsanträge ({u['n']})", "anzahl": u["n"],
                      "name": f"Urlaubsanträge ({u['n']})", "employee_id": None,
                      "text": "1 offener Antrag" if u["n"] == 1 else f"{u['n']} offene Anträge",
                      "link": "/cockpit/einstellungen?tab=urlaub&status=pending",
                      "seit": u["seit"].isoformat() if u["seit"] else None, "aktionen": []})
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
    # Doppelt nachgereichte Offline-Stempel (nicht übernommen, services/stempel_doppelt.py)
    from app.services import stempel_doppelt as sd
    for r in sd.offene(db, emp):
        was = "Kommen" if r["art"] == "kommen" else "Gehen"
        items.append({"typ": "doppelt", "id": r["id"], "titel": "Doppelt nachgereicht", "name": r["name"],
                      "employee_id": r["employee_id"],
                      "text": f"{was} {r['stempel_zeit']:%d.%m. %H:%M} offline, übertragen {r['empfangen_am']:%d.%m. %H:%M} – "
                              f"nicht übernommen, überschneidet sich mit {r['buchung_text']}",
                      "buchung_id": r["buchung_id"],
                      "seit": r["empfangen_am"].isoformat(), "aktionen": ["erledigt"]})
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
    elif typ == "doppelt":
        from app.services import stempel_doppelt as sd
        row = _q(db, "SELECT employee_id FROM stempel_verworfen WHERE id = :i", i=item_id)
        if not row:
            raise HTTPException(404, "Hinweis nicht gefunden")
        ol_scope.require_employee(db, user, row[0]["employee_id"])
        if akt in ("erledigt", "offen"):
            return sd.erledigen(db, item_id, user.id, zurueck=akt == "offen")
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
    from app.services import plan_vorlage as pv
    vl = [dict(m) for m in pv.vorlage(db)]
    for r in rows:
        tage[(r["date"] - d0).days]["schichten"].append({
            "id": r["id"], "name": r["name"], "personal_nr": r["personal_nr"], "employee_id": r["employee_id"],
            "objekt": "Urlaub" if r["object_id"] == OBJ_URLAUB else ("Krank" if r["object_id"] == OBJ_KRANK else r["objekt"]),
            "beginn": _hm(r["start_time"]), "ende": _hm(r["end_time"]), "status": r["status"],
            "fahrer": bool(r["is_driver"]), "object_id": r["object_id"], **_fix_info(r, vl)})
    for lu in pv.luecken(db, d0, d0 + timedelta(days=6), obj):
        tage[(date.fromisoformat(lu["datum"]) - d0).days].setdefault("luecken", []).append(lu)
    return {"start": d0.isoformat(), "tage": tage, "plan": pv.wochen_status(db, d0, obj)}


# Wer nicht die Rolle Mitarbeiter hat (z. B. Objektleitung), erscheint in der Mitarbeiter-Liste, sobald er/sie
# eingesetzt wird: Schicht oder Stempelung in den letzten 12 Monaten oder kuenftig geplant (alte Admin-Testbuchungen nicht).
_EINGESETZT = """(EXISTS (SELECT 1 FROM schedules s WHERE s.employee_id = e.id AND s.date >= current_date - 365)
                 OR EXISTS (SELECT 1 FROM time_entries t WHERE t.employee_id = e.id AND t.check_in >= current_date - 365))"""


@router.get("/mitarbeiter")
def mitarbeiter(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    obj, emp = _scope(db, user)
    rows = _q(db, f"""
        SELECT e.id, e.personal_nr, e.first_name, e.last_name, e.is_active, u.category, lower(u.role::text) AS rolle,
               (SELECT string_agg(o.name, ', ' ORDER BY o.name) FROM employee_object_assignments a
                  JOIN objects o ON o.id = a.object_id
                 WHERE a.employee_id = e.id AND coalesce(a.is_active,true) AND {_flt('a.object_id', obj)}) AS objekte
          FROM employees e JOIN users u ON u.id = e.user_id
         WHERE NOT coalesce(e.is_test,false) AND {_flt('e.id', emp)}
           AND (u.role = 'MITARBEITER' OR {_EINGESETZT})
         ORDER BY e.is_active DESC, e.last_name, e.first_name""", **_params(obj, emp))
    return [dict(r) for r in rows]


def _month_bounds(today):
    first = today.replace(day=1)
    return first, today.replace(day=monthrange(today.year, today.month)[1])


@router.get("/mitarbeiter/{employee_id}")
def akte(employee_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    ol_scope.require_employee(db, user, employee_id)
    obj, _ = _scope(db, user)
    e = _q(db, """SELECT e.*, u.email, u.category, u.is_active AS login_aktiv, lower(u.role::text) AS rolle FROM employees e
                  JOIN users u ON u.id = e.user_id WHERE e.id = :i""", i=employee_id)
    if not e:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    e = e[0]
    today = date.today()
    m0, m1 = _month_bounds(today)
    p = _params(obj, None, i=employee_id, a=m0, b=m1, d=today, y=today.year)
    stamm = {"id": e["id"], "personal_nr": e["personal_nr"], "name": f"{e['first_name']} {e['last_name']}",
             "email": e["email"], "adresse": e["address"], "kategorie": e["category"], "rolle": e["rolle"],
             "stempelart": {"A": "Automatisch", "B": "Knopf", "C": "Auto-Stempel"}.get(e["tracking_mode"], e["tracking_mode"]),
             "aktiv": bool(e["is_active"]), "beschaeftigung": e["employment_type"],
             "telegram": bool(e["telegram_chat_id"]), "seit": e["created_at"].date().isoformat() if e["created_at"] else None}
    if ol_scope.is_manager(user):
        stamm["stundenlohn"] = e["hourly_rate"]
        stamm["sondersatz"] = float(e["hourly_rate_basic"]) if e["hourly_rate_basic"] is not None else buchung_art.SONDERSATZ_STANDARD
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


@router.put("/mitarbeiter/{employee_id}/sondersatz")
def sondersatz_setzen(employee_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Sondersatz (employees.hourly_rate_basic) fuer Grund-/Sonder-/Fensterreinigung (Drazen 25.11.2026).
    Gilt nur fuer kuenftig angelegte Buchungen bzw. bei Art-Wechsel - bestehende Buchungen bleiben unveraendert."""
    ol_scope.require_employee(db, user, employee_id)
    if not ol_scope.is_manager(user):
        raise HTTPException(403, "Nur Administration oder Objektleitung")
    try:
        neu = buchung_art.satz_pruefen(data.get("sondersatz"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    alt = _q(db, "SELECT hourly_rate_basic FROM employees WHERE id = :i", i=employee_id)
    if not alt:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    alt = float(alt[0]["hourly_rate_basic"]) if alt[0]["hourly_rate_basic"] is not None else None
    if alt != neu:
        db.execute(text("UPDATE employees SET hourly_rate_basic = :s WHERE id = :i"), {"s": neu, "i": employee_id})
        log_audit(db, user.id, employee_id, "employee_updated", entity_type="employee", entity_id=employee_id,
                  old_value={"sondersatz": alt}, new_value={"sondersatz": neu},
                  details=f"Sondersatz {alt if alt is not None else '-'} -> {neu:.2f} € im Cockpit geaendert")
        db.commit()
    return {"sondersatz": neu}


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


def ohne_stempel(db, d0, d1):
    """Geplante Schichten (bis gestern), fuer die es keinen Zeiteintrag gibt und die Person nicht abwesend ist.
    Damit faellt beim Monatsabschluss auf, wer gar nicht gestempelt hat (die Leitstelle zeigt 'fehlt' sonst nur heute)."""
    d1 = min(d1, date.today() - timedelta(days=1))
    if d1 < d0:
        return []
    rows = _q(db, f"""SELECT s.id, s.employee_id, s.object_id, s.date, s.start_time, s.end_time, o.name AS objekt,
                             e.first_name || ' ' || e.last_name AS name, e.personal_nr
                        FROM schedules s JOIN employees e ON e.id = s.employee_id LEFT JOIN objects o ON o.id = s.object_id
                       WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal', 'vertretung') AND NOT coalesce(e.is_test, false)
                         AND s.start_time IS NOT NULL AND s.object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})
                         AND NOT EXISTS (SELECT 1 FROM time_entries t WHERE t.employee_id = s.employee_id AND t.check_in::date = s.date
                                           AND (t.schedule_id = s.id OR t.object_id = s.object_id))
                       ORDER BY s.date, s.start_time""", a=d0, b=d1)
    abw = _abwesend_map(db, d0, d1)
    return [{"id": f"s{r['id']}", "fehlt": True, "schicht_id": r["id"], "datum": r["date"].isoformat(), "name": r["name"],
             "personal_nr": r["personal_nr"], "employee_id": r["employee_id"], "object_id": r["object_id"], "objekt": r["objekt"],
             "kommen": _hm(r["start_time"]), "gehen": _hm(r["end_time"]), "check_in": f"{r['date'].isoformat()}T{_hm(r['start_time'])}",
             "check_out": None, "gehen_datum": r["date"].isoformat(), "stunden": 0.0, "weg": "", "notes": "",
             "hinweis": "geplant, nicht gestempelt"} for r in rows if (r["employee_id"], r["date"]) not in abw]


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
            "weg": "Terminal" if r.get("quelle") == "terminal" else
                   (r["notes"] or "").split(" - ")[0][:40] if r["notes"] else ("App" if r["is_manual_entry"] is False else "Manuell"),
            "quelle": r.get("quelle"),
            "verspaetet": verspaetet.hinweise(r),
            "hourly_rate": float(r["hourly_rate"]) if r.get("hourly_rate") is not None else None,
            "fahrt": r.get("km") is not None, "km": float(r["km"]) if r.get("km") is not None else None,
            "hinweis": ", ".join(hint)}


_ZEIT_SELECT = f"""
        SELECT t.id, t.check_in, t.check_out, t.billed_hours, t.notes, t.is_manual_entry, t.object_id, t.service_type, t.schedule_id,
               t.quelle, t.kommen_handy, t.kommen_eingang, t.gehen_handy, t.gehen_eingang, t.hourly_rate,
               (SELECT k.distance_km FROM km_daily_entries k WHERE k.time_entry_id = t.id ORDER BY k.id LIMIT 1) AS km, o.name AS objekt, e.first_name || ' ' || e.last_name AS name, e.personal_nr, t.employee_id,
               (SELECT coalesce(sum(extract(epoch FROM b.end_time - b.start_time)),0) FROM break_entries b
                 WHERE b.time_entry_id = t.id AND b.end_time IS NOT NULL) AS brk
          FROM time_entries t JOIN employees e ON e.id = t.employee_id LEFT JOIN objects o ON o.id = t.object_id"""


@router.get("/zeiten")
def zeiten(von: str = Query(None), bis: str = Query(None), pruef: str = Query(None), monat: str = Query(None),
           db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    d1 = date.fromisoformat(bis) if bis else date.today()
    d0 = date.fromisoformat(von) if von else d1 - timedelta(days=6)
    if pruef == "ohne_stempel":
        try:
            ref = date.fromisoformat(f"{monat}-01") if monat else date.today()
        except ValueError:
            raise HTTPException(400, "Monat als JJJJ-MM")
        d0, d1 = _month_bounds(ref)
        return {"von": d0.isoformat(), "bis": d1.isoformat(), "pruef": pruef, "monat": d0.strftime("%Y-%m"),
                "eintraege": ohne_stempel(db, d0, d1)}
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
    zu = _gesperrte_monate(db)
    eintraege = [_zeile(r) for r in rows]
    for e in eintraege:             # Monatssperre (Monatsabschluss): Bearbeiten erst nach "Wieder öffnen"
        e["gesperrt"] = e["datum"][:7] in zu or (e["gehen_datum"] or "")[:7] in zu
    return {"von": d0.isoformat(), "bis": d1.isoformat(), "pruef": pruef, "monat": d0.strftime("%Y-%m"),
            "gesperrte_monate": sorted(zu), "eintraege": eintraege}


def _gesperrte_monate(db):
    if not db.execute(text("SELECT to_regclass('monatsabschluss') IS NOT NULL")).scalar():
        return set()
    return {r[0] for r in db.execute(text("SELECT monat FROM monatsabschluss WHERE status = 'abgeschlossen'")).fetchall()}


@router.get("/zeiten/{entry_id}")
def zeit(entry_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    rows = _q(db, f"{_ZEIT_SELECT} WHERE t.id = :i", i=entry_id)
    if not rows:
        raise HTTPException(404, "Buchung nicht gefunden")
    z = _zeile(rows[0])
    zu = _gesperrte_monate(db)
    z["gesperrt"] = z["datum"][:7] in zu or (z["gehen_datum"] or "")[:7] in zu
    return z


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
    alt = _q(db, "SELECT employee_id, object_id, service_type FROM time_entries WHERE id = :i", i=entry_id)
    if not alt:
        raise HTTPException(404, "Buchung nicht gefunden")
    alt = alt[0]
    # Art + Satz (Drazen 25.11.2026 12:20): Satz je Art vorbelegt, aber ueberschreibbar ("stundensatz").
    # Ohne eigenen Satz nur bei Art-Wechsel neu vorbelegen - ein frueher gesetzter Satz bleibt sonst stehen.
    art = data.get("art")
    if art and art != alt["service_type"]:
        if art not in buchung_art.ARTEN:
            raise HTTPException(400, buchung_art.ART_FEHLER)
        body["service_type"] = art
        body["hourly_rate"] = buchung_art.satz(db, int(body.get("employee_id") or alt["employee_id"]),
                                               int(body.get("object_id") or alt["object_id"] or 0) or None, art)
    if data.get("stundensatz") not in (None, ""):
        try:
            body["hourly_rate"] = buchung_art.satz_pruefen(data["stundensatz"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    update_booking(entry_id, body, db=db, admin=user)   # protokolliert alt/neu inkl. Art und Satz
    if "fahrt" in data:
        try:
            buchung_art.km_setzen(db, entry_id, bool(data["fahrt"]), user.id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    return zeit(entry_id, db=db, user=user)


@router.get("/zeiten-satz")
def zeiten_satz(employee_id: int, object_id: int = None, art: str = buchung_art.UNTERHALT, schedule_id: int = None,
                datum: str = None, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Anzeige im Dialog: Stundensatz + Lohnart zur Art, Vorbelegung Kommen/Gehen (mit datum) und "Fahrt mit KM"
    (an fuer alle mit KM-Geld, D0002 aus), Entfernung."""
    try:
        tag = date.fromisoformat(datum) if datum else None
    except ValueError:
        raise HTTPException(400, "Datum ungültig")
    try:
        sz = buchung_art.satz(db, employee_id, object_id, art)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"satz": sz, "lohnart": buchung_art.lohnart(db, art), "sonder": buchung_art.ist_sonder(art),
            "fahrer": buchung_art.fahrer_standard(db, employee_id, object_id, schedule_id),
            "km_berechtigt": buchung_art.km_berechtigt(db, employee_id),
            "zeit": buchung_art.standardzeit(db, employee_id, object_id, tag),
            "km": buchung_art.km_distanz(db, employee_id, object_id)}


@router.post("/zeiten")
def zeit_anlegen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import create_manual_booking
    ci, co = _pruefe_zeiten(data)
    if not data.get("employee_id") or not data.get("object_id"):
        raise HTTPException(400, "Mitarbeiter und Objekt angeben")
    art = data.get("art") or data.get("service_type") or buchung_art.UNTERHALT
    if art not in buchung_art.ARTEN:
        raise HTTPException(400, buchung_art.ART_FEHLER)
    try:
        satz = (buchung_art.satz_pruefen(data["stundensatz"]) if data.get("stundensatz") not in (None, "")
                else buchung_art.satz(db, int(data["employee_id"]), int(data["object_id"]), art))
    except ValueError as e:
        raise HTTPException(400, str(e))
    r = create_manual_booking({"employee_id": int(data["employee_id"]), "object_id": int(data["object_id"]),
                               "check_in": ci.isoformat(), "check_out": co.isoformat(),
                               "check_in_time": ci.strftime("%H:%M"), "check_out_time": co.strftime("%H:%M"),
                               "service_type": art, "hourly_rate": satz,
                               "notes": data.get("notes") or "Im Cockpit nachgetragen"}, db=db, admin=user)
    if data.get("schedule_id"):
        db.execute(text("UPDATE time_entries SET schedule_id = :s WHERE id = :i AND schedule_id IS NULL"),
                   {"s": int(data["schedule_id"]), "i": r["id"]})
        db.commit()
    # KM-Geld wie beim Stempeln (gleiche Berechnung wie die App). Haken "Fahrt mit KM" im Dialog; ohne Angabe
    # an fuer alle mit KM-Geld (Drazen 25.11.2026 15:09, D0002 ohne KM)
    eid, oid = int(data["employee_id"]), int(data["object_id"])
    fahrt = data["fahrt"] if "fahrt" in data else buchung_art.km_berechtigt(db, eid)
    if fahrt:
        from app.api.v1.endpoints.time_entries import calculate_and_save_km
        calculate_and_save_km(eid, oid, ci.date(), r["id"], db)
        db.commit()
    return zeit(r["id"], db=db, user=user)


@router.delete("/zeiten/{entry_id}")
def zeit_loeschen(entry_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    from app.api.v1.endpoints.admin import delete_booking
    alt = zeit(entry_id, db=db, user=user)
    delete_booking(entry_id, db=db, admin=user)
    return {"status": "geloescht", "alt": alt}


def _fix_info(r, vl):
    """Haekchen "fix": Schicht ist durch einen Vorlage-Eintrag abgedeckt (plan_vorlage.fix_eintrag)."""
    from app.services import plan_vorlage as pv
    m = pv.fix_eintrag({"date": r["date"], "employee_id": r["employee_id"], "object_id": r["object_id"],
                        "start_time": r["start_time"], "end_time": r["end_time"]}, vl)
    return {"fix": bool(m), "fix_14": bool(m) and m["rhythm"] != "weekly"}


@router.put("/dienstplan/{schedule_id}/fix")
def schicht_fix(schedule_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Haken "fix" = Schicht gehoert zur Vorlage (Fixum). {"fix": bool, "alle_2_wochen": bool}"""
    from app.services import plan_vorlage as pv
    try:
        return pv.fix_setzen(db, schedule_id, bool(data.get("fix")), bool(data.get("alle_2_wochen")), user.id)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/schicht/{schedule_id}")
def schicht(schedule_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    r = _q(db, """SELECT s.id, s.date, s.start_time, s.end_time, s.employee_id, s.object_id, s.status, s.is_driver, s.notes,
                         o.name AS objekt, e.first_name || ' ' || e.last_name AS name
                    FROM schedules s JOIN employees e ON e.id = s.employee_id LEFT JOIN objects o ON o.id = s.object_id
                   WHERE s.id = :i""", i=schedule_id)
    if not r:
        raise HTTPException(404, "Schicht nicht gefunden")
    r = r[0]
    from app.services import plan_vorlage as pv
    return {"id": r["id"], "datum": r["date"].isoformat(), "beginn": _hm(r["start_time"]), "ende": _hm(r["end_time"]),
            "employee_id": r["employee_id"], "object_id": r["object_id"], "status": r["status"], "fahrer": bool(r["is_driver"]),
            "notes": r["notes"], "objekt": r["objekt"], "name": r["name"],
            **_fix_info(r, [dict(m) for m in pv.vorlage(db)])}


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


# --- Dienstplan: Kopieren (Vorschau + Konflikte + Rueckgaengig) und Verschieben -------------------
MAX_KOPIE = 500          # neue Schichten je Kopiervorgang
MAX_ZIEL_TAGE = 92       # Zielzeitraum hoechstens ~3 Monate


def _d(v, feld):
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{feld}: Datum als JJJJ-MM-TT")


def _min(t):
    return t.hour * 60 + t.minute


def _ueberlappt(a0, a1, b0, b1):
    """Zeiten in Minuten; Ende <= Beginn = ueber Mitternacht."""
    a1 = a1 if a1 > a0 else a1 + 1440
    b1 = b1 if b1 > b0 else b1 + 1440
    return a0 < b1 and b0 < a1


def _quellschichten(db, data):
    """Quell-Schichten (nur echte Einsaetze, keine Urlaub/Krank-Eintraege) + Quellzeitraum."""
    ids = [int(x) for x in (data.get("schicht_ids") or [])][:MAX_KOPIE]
    if ids:
        rows = _q(db, f"""SELECT s.* FROM schedules s WHERE s.id = ANY(:ids) AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                          AND coalesce(s.status,'normal') NOT IN ('storniert','urlaub','krank','abwesend') ORDER BY s.date, s.start_time""", ids=ids)
        if not rows:
            raise HTTPException(404, "Schicht nicht gefunden")
        return rows, min(r["date"] for r in rows), max(r["date"] for r in rows)
    von, bis = _d(data.get("quelle_von"), "quelle_von"), _d(data.get("quelle_bis") or data.get("quelle_von"), "quelle_bis")
    if bis < von or (bis - von).days > 30:
        raise HTTPException(400, "Quellzeitraum: 1 bis 31 Tage")
    rows = _q(db, f"""SELECT s.* FROM schedules s JOIN employees e ON e.id = s.employee_id
                      WHERE s.date BETWEEN :a AND :b AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND NOT coalesce(e.is_test,false)
                        AND coalesce(s.status,'normal') NOT IN ('storniert','urlaub','krank','abwesend') ORDER BY s.date, s.start_time""", a=von, b=bis)
    return rows, von, bis


def _kopie_plan(db, data):
    """Was wuerde angelegt? Je neue Schicht: ok oder Grund zum Ueberspringen."""
    rows, q0, q1 = _quellschichten(db, data)
    ziel0 = _d(data.get("ziel_von"), "ziel_von")
    laenge = (q1 - q0).days + 1          # Rhythmus: Quell-Tage (Schicht/Tag = 1, Woche = 7)
    ziel1 = _d(data["ziel_bis"], "ziel_bis") if data.get("ziel_bis") else ziel0 + timedelta(days=laenge - 1)
    if ziel1 < ziel0 or (ziel1 - ziel0).days >= MAX_ZIEL_TAGE:
        raise HTTPException(400, f"Zielzeitraum: 1 bis {MAX_ZIEL_TAGE} Tage")
    if ziel0 <= q1 and q0 <= ziel1 and not data.get("employee_id"):
        raise HTTPException(400, "Ziel ueberschneidet sich mit der Quelle")
    ma = int(data["employee_id"]) if data.get("employee_id") else None

    # Muster wird im Rhythmus der Quelllaenge wiederholt (Woche -> woechentlich, Tag -> taeglich)
    neu = []
    k = 0
    while True:
        basis = ziel0 + timedelta(days=k * laenge)
        if basis > ziel1:
            break
        for r in rows:
            d = basis + (r["date"] - q0)
            if ziel0 <= d <= ziel1:
                neu.append({"quelle_id": r["id"], "employee_id": ma or r["employee_id"], "object_id": r["object_id"], "datum": d,
                            "start": r["start_time"], "ende": r["end_time"], "fahrer": bool(r["is_driver"])})
        k += 1
    return _pruefe_neue(db, neu, ziel0, ziel1)


def _pruefe_neue(db, neu, ziel0, ziel1):
    """Je geplante neue Schicht: ok oder Grund zum Ueberspringen (Vergangenheit, Sonntagsregel, Urlaub/Krank/Absage,
    schon vorhanden, Doppelbelegung). Gemeinsam fuer Kopieren, Woche aus Vorlage und Kontingent verteilen."""
    if len(neu) > MAX_KOPIE:
        raise HTTPException(400, f"Zu viele Schichten ({len(neu)}), hoechstens {MAX_KOPIE} je Vorgang")
    if not neu:
        return {"ziel_von": ziel0.isoformat(), "ziel_bis": ziel1.isoformat(), "eintraege": [], "anzulegen": 0, "uebersprungen": 0}
    from app.services import plan_vorlage as _pv

    emps = {n["employee_id"] for n in neu}
    namen = {r["id"]: r for r in _q(db, """SELECT e.id, e.first_name || ' ' || e.last_name AS name, e.personal_nr, e.is_active
                                              FROM employees e WHERE e.id = ANY(:i)""", i=list(emps))}
    objs = {r["id"]: r["name"] for r in _q(db, "SELECT id, name FROM objects WHERE id = ANY(:i)", i=list({n['object_id'] for n in neu}))}
    abw = {**_pv.absagen(db, ziel0, ziel1), **_abwesend_map(db, ziel0, ziel1)}
    best = {}
    for r in _q(db, f"""SELECT s.employee_id, s.date, s.start_time, s.end_time, s.object_id, o.name AS objekt FROM schedules s
                        LEFT JOIN objects o ON o.id = s.object_id
                        WHERE s.date BETWEEN :a AND :b AND s.employee_id = ANY(:e) AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                          AND s.start_time IS NOT NULL AND s.end_time IS NOT NULL
                          AND coalesce(s.status,'normal') NOT IN ('storniert')""", a=ziel0, b=ziel1, e=list(emps)):
        best.setdefault((r["employee_id"], r["date"]), []).append(r)
    heute = date.today()
    from app.services import sonntag_d0002 as _so   # gleiche Ausnahme wie beim klassischen Wochenkopieren
    out, geplant = [], {}
    for n in sorted(neu, key=lambda x: (x["datum"], x["start"], x["employee_id"])):
        key = (n["employee_id"], n["datum"])
        m = namen.get(n["employee_id"])
        grund = None
        if n["datum"] < heute:
            grund = "liegt in der Vergangenheit"
        elif _so.applies(n["employee_id"], n["datum"]):
            grund = "Sonntag wird automatisch angelegt (Sonntagsregel)"
        elif not m or not m["is_active"]:
            grund = "Mitarbeiter nicht aktiv"
        elif key in abw:
            grund = abw[key]
        else:
            s0, s1 = _min(n["start"]), _min(n["ende"])
            for b in best.get(key, []):
                if b["object_id"] == n["object_id"] and b["start_time"] == n["start"] and b["end_time"] == n["ende"]:
                    grund = "bereits vorhanden"; break
                if _ueberlappt(s0, s1, _min(b["start_time"]), _min(b["end_time"])):
                    grund = f"Doppelbelegung: {b['objekt']} {_hm(b['start_time'])}–{_hm(b['end_time'])}"; break
            if not grund:
                for b in geplant.get(key, []):
                    if _ueberlappt(s0, s1, _min(b["start"]), _min(b["ende"])):
                        grund = "Doppelbelegung innerhalb der Kopie"; break
        if not grund:
            geplant.setdefault(key, []).append(n)
        out.append({"quelle_id": n.get("quelle_id"), "vorlage_id": n.get("vorlage_id"), "datum": n["datum"].isoformat(), "tag": WOCHENTAG[n["datum"].weekday()],
                    "employee_id": n["employee_id"], "name": m["name"] if m else "?", "object_id": n["object_id"],
                    "objekt": objs.get(n["object_id"], "?"), "beginn": _hm(n["start"]), "ende": _hm(n["ende"]), "fahrer": n["fahrer"],
                    "status": "ok" if not grund else ("abwesend" if grund in ("Urlaub", "Krank", "Absage") else "konflikt"), "grund": grund})
    return {"ziel_von": ziel0.isoformat(), "ziel_bis": ziel1.isoformat(), "eintraege": out,
            "anzulegen": sum(1 for o in out if o["status"] == "ok"), "uebersprungen": sum(1 for o in out if o["status"] != "ok")}


@router.post("/dienstplan/kopieren")
def dienstplan_kopieren(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Kopiert Schichten (einzeln, Tag, Woche oder Zeitraum). vorschau=true: nur anzeigen, nichts speichern.
    Ohne Vorschau: alle 'ok'-Eintraege in EINER Transaktion; Konflikte werden uebersprungen. Rueckgabe mit kopie_id."""
    plan = _kopie_plan(db, data)
    if data.get("vorschau", True):
        return {**plan, "vorschau": True}
    return _anlegen(db, user, plan, "Schicht kopiert")


def _anlegen(db, user, plan, was):
    """Alle 'ok'-Eintraege eines Plans in EINER Transaktion anlegen. Audit mit [Kopie id] -> ganzer Vorgang ist
    ueber DELETE /dienstplan/kopie/{id} rueckgaengig zu machen."""
    import uuid
    from app.api.v1.endpoints.admin import check_vacation_conflict, check_and_reset_confirmation
    kopie_id = uuid.uuid4().hex[:12]
    angelegt = []
    try:
        for e in plan["eintraege"]:
            if e["status"] != "ok":
                continue
            d = date.fromisoformat(e["datum"])
            if check_vacation_conflict(db, e["employee_id"], d):      # gleiche Pruefung wie beim Einzel-Anlegen
                e["status"], e["grund"] = "abwesend", "Urlaub"
                continue
            b, en = datetime.strptime(e["beginn"], "%H:%M"), datetime.strptime(e["ende"], "%H:%M")
            std = ((en - b).total_seconds() / 3600) % 24 or 24
            sid = db.execute(text("""INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours,
                                         status, is_driver, created_by, created_at, updated_at)
                                     VALUES (:e, :o, :d, :w, :s, :en, :h, 'normal', :f, :u, now(), now()) RETURNING id"""),
                             {"e": e["employee_id"], "o": e["object_id"], "d": d, "w": d.weekday(), "s": e["beginn"], "en": e["ende"],
                              "h": std, "f": e["fahrer"], "u": user.id}).scalar()
            e["id"] = sid
            angelegt.append(e)
            log_audit(db, user.id, e["employee_id"], "schedule_copied", entity_type="schedule", entity_id=sid,
                      new_value={"datum": e["datum"], "zeit": f"{e['beginn']}-{e['ende']}", "objekt": e["objekt"],
                                 "quelle": e.get("quelle_id"), "vorlage": e.get("vorlage_id")},
                      details=f"{was} [Kopie {kopie_id}]: {e['name']}, {d.strftime('%d.%m.%Y')}, {e['beginn']}-{e['ende']}, {e['objekt']}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    for e in angelegt:
        check_and_reset_confirmation(db, e["employee_id"], date.fromisoformat(e["datum"]))
    return {**plan, "vorschau": False, "kopie_id": kopie_id, "angelegt": len(angelegt),
            "uebersprungen": len(plan["eintraege"]) - len(angelegt), "ids": [e["id"] for e in angelegt]}


@router.delete("/dienstplan/kopie/{kopie_id}")
def kopie_rueckgaengig(kopie_id: str, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Nimmt einen ganzen Kopiervorgang zurueck. Schichten, auf die schon gestempelt wurde, bleiben stehen."""
    import re
    if not re.fullmatch(r"[0-9a-f]{12}", kopie_id):
        raise HTTPException(400, "Ungueltige Kopie")
    ids = [r["entity_id"] for r in _q(db, """SELECT entity_id FROM audit_log WHERE action = 'schedule_copied' AND entity_type = 'schedule'
                                               AND details LIKE :m""", m=f"%[Kopie {kopie_id}]%")]
    if not ids:
        raise HTTPException(404, "Kopiervorgang nicht gefunden")
    gestempelt = {r["schedule_id"] for r in _q(db, "SELECT DISTINCT schedule_id FROM time_entries WHERE schedule_id = ANY(:i)", i=ids)}
    weg = 0
    for sid in ids:
        if sid in gestempelt:
            continue
        r = _q(db, "SELECT employee_id, date FROM schedules WHERE id = :i", i=sid)
        if not r:
            continue
        db.execute(text("UPDATE schedules SET partner_schedule_id = NULL WHERE partner_schedule_id = :i"), {"i": sid})
        db.execute(text("DELETE FROM schedules WHERE id = :i"), {"i": sid})
        log_audit(db, user.id, r[0]["employee_id"], "schedule_deleted", entity_type="schedule", entity_id=sid,
                  details=f"Kopieren rueckgaengig [Kopie {kopie_id}]: Schicht {r[0]['date'].strftime('%d.%m.%Y')} entfernt")
        weg += 1
    from app.services import plan_vorlage as _pv
    _pv.fixum_zurueckgenommen(db, kopie_id)
    db.commit()
    return {"entfernt": weg, "behalten_gestempelt": len(gestempelt)}


@router.post("/dienstplan/{schedule_id}/verschieben")
def schicht_verschieben(schedule_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Drag & Drop: Schicht auf anderen Tag und/oder anderen MA. Prueft Urlaub/Krank, Doppelbelegung und ob schon gestempelt."""
    from app.api.v1.endpoints.admin import update_schedule
    alt = schicht(schedule_id, db=db, user=user)
    if alt["object_id"] in (OBJ_URLAUB, OBJ_KRANK):
        raise HTTPException(400, "Urlaub/Krank-Eintraege werden nicht verschoben")
    if _q(db, "SELECT 1 FROM time_entries WHERE schedule_id = :i LIMIT 1", i=schedule_id):
        raise HTTPException(409, "Auf diese Schicht wurde schon gestempelt – nicht verschiebbar")
    ziel = _d(data.get("datum") or alt["datum"], "datum")
    ma = int(data.get("employee_id") or alt["employee_id"])
    if ziel < date.today():
        raise HTTPException(409, "Ziel liegt in der Vergangenheit")
    grund = _abwesend_map(db, ziel, ziel).get((ma, ziel))
    if grund:
        raise HTTPException(409, f"Am Zieltag {grund}")
    b0, b1 = _min(datetime.strptime(alt["beginn"], "%H:%M")), _min(datetime.strptime(alt["ende"], "%H:%M"))
    for r in _q(db, f"""SELECT s.start_time, s.end_time, o.name FROM schedules s LEFT JOIN objects o ON o.id = s.object_id
                        WHERE s.employee_id = :e AND s.date = :d AND s.id <> :i AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                          AND s.start_time IS NOT NULL AND s.end_time IS NOT NULL AND coalesce(s.status,'normal') <> 'storniert'""", e=ma, d=ziel, i=schedule_id):
        if _ueberlappt(b0, b1, _min(r["start_time"]), _min(r["end_time"])):
            raise HTTPException(409, f"Doppelbelegung: {r['name']} {_hm(r['start_time'])}–{_hm(r['end_time'])}")
    update_schedule(schedule_id, {"employee_id": ma, "object_id": alt["object_id"], "date": ziel.isoformat(),
                                  "start_time": alt["beginn"], "end_time": alt["ende"], "is_driver": alt["fahrer"]}, db=db, admin=user)
    return {"alt": alt, "neu": schicht(schedule_id, db=db, user=user)}


@router.get("/auswahl")
def auswahl(datum: str = Query(None), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Listen fuer Auswahlfelder (aktive MA, aktive Objekte). Mit datum: je MA, was an dem Tag schon ist
    (Urlaub/Krank/Absage oder Schichten) und je MA+Objekt, ob er dort mit eigenem Auto faehrt (Zuweisung)."""
    ma = _q(db, """SELECT e.id, e.first_name || ' ' || e.last_name AS name, e.personal_nr FROM employees e JOIN users u ON u.id = e.user_id
                   WHERE e.is_active AND NOT coalesce(e.is_test,false) AND u.role <> 'ADMIN' ORDER BY e.last_name, e.first_name""")
    ob = _q(db, f"""SELECT id, name FROM objects WHERE coalesce(is_active,true) AND NOT coalesce(is_test,false)
                    AND id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) ORDER BY name""")
    out = {"mitarbeiter": [dict(x) for x in ma], "objekte": [dict(x) for x in ob]}
    out["fahrer"] = {f"{r['employee_id']}|{r['object_id']}": bool(r["is_driver"]) for r in _q(db, """
        SELECT employee_id, object_id, coalesce(is_driver, false) AS is_driver FROM employee_object_assignments WHERE coalesce(is_active, true)""")}
    if datum:
        from app.services import plan_vorlage as _pv
        d = _d(datum, "datum")
        tag = {}
        for r in _q(db, f"""SELECT s.employee_id, s.start_time, s.end_time, o.name FROM schedules s JOIN objects o ON o.id = s.object_id
                            WHERE s.date = :d AND s.status IN ('normal', 'vertretung') AND s.start_time IS NOT NULL
                              AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) ORDER BY s.start_time""", d=d):
            tag.setdefault(r["employee_id"], []).append(f"{_hm(r['start_time'])}–{_hm(r['end_time'])} {r['name']}")
        info = {eid: "arbeitet " + ", ".join(v) for eid, v in tag.items()}
        for (eid, _), grund in {**_pv.absagen(db, d, d), **_abwesend_map(db, d, d)}.items():
            info[eid] = grund
        out["tag"] = {str(k): v for k, v in info.items()}
    return out


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


# --- Objekt-Logo / farbiges Kuerzel (nur interne Anzeige) -----------------------------------------
def _objekt_sichtbar(db, user, object_id):
    obj, _ = _scope(db, user)
    if obj is not None and object_id not in obj:
        raise HTTPException(403, "Kein Zugriff auf dieses Objekt")
    o = _q(db, "SELECT id, name FROM objects WHERE id = :i", i=object_id)
    if not o:
        raise HTTPException(404, "Objekt nicht gefunden")
    return o[0]


def _marke_speichern(db, user, object_id, felder: dict, was: str):
    from app.services import objekt_marke as om
    from app.services import features
    if not features.an("OBJEKT_LOGO"):
        raise HTTPException(404, "Objekt-Logo ist auf diesem Server noch nicht freigeschaltet")
    o = _objekt_sichtbar(db, user, object_id)
    om.tabelle(db)
    alt = om.marken(db, [object_id]).get(object_id)
    sets = ", ".join(f"{k} = :{k}" for k in felder)
    db.execute(text(f"""INSERT INTO objekt_marken (object_id, {", ".join(felder)}, updated_at, updated_by)
                        VALUES (:oid, {", ".join(":" + k for k in felder)}, now(), :uid)
                        ON CONFLICT (object_id) DO UPDATE SET {sets}, updated_at = now(), updated_by = :uid"""),
               {"oid": object_id, "uid": user.id, **felder})
    neu = om.marken(db, [object_id]).get(object_id)
    kurz = lambda m: {"kuerzel": m["kuerzel"], "farbe": m["farbe"], "logo": bool(m["logo"])}  # noqa: E731
    log_audit(db, user.id, None, "objekt_marke_geaendert", entity_type="object", entity_id=object_id,
              old_value=kurz(alt), new_value=kurz(neu), details=f"Objekt {o['name']}: {was}")
    db.commit()
    return {**neu, "object_id": object_id}


@router.get("/objekt-marken")
def objekt_marken(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Logo/Kuerzel/Farbe aller sichtbaren Objekte + Palette (fuer Anzeige ueberall im Cockpit)."""
    from app.services import objekt_marke as om
    obj, _ = _scope(db, user)
    m = om.marken(db, obj)
    db.commit()
    return {"palette": om.PALETTE, "marken": {str(k): v for k, v in m.items()}}


@router.put("/objekte/{object_id}/marke")
def objekt_marke_aendern(object_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Kuerzel (1-3 Zeichen) und Farbe (aus der Palette) aendern; leer = automatisch."""
    import re
    from app.services import objekt_marke as om
    felder = {}
    if "kuerzel" in data:
        k = str(data.get("kuerzel") or "").strip().upper()
        if k and not re.fullmatch(r"[A-Z0-9ÄÖÜ]{1,3}", k):
            raise HTTPException(400, "Kürzel: 1–3 Buchstaben oder Ziffern")
        felder["kuerzel"] = k or None
    if "farbe" in data:
        f = str(data.get("farbe") or "").strip().upper()
        if f and f not in om.PALETTE:
            raise HTTPException(400, "Farbe bitte aus der Palette wählen")
        felder["farbe"] = f or None
    if not felder:
        raise HTTPException(400, "Nichts zu ändern")
    return _marke_speichern(db, user, object_id, felder, "Kürzel/Farbe geändert")


@router.put("/objekte/{object_id}/logo")
def objekt_logo_hochladen(object_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Logo als kleines PNG (im Browser verkleinert) - nur interne Anzeige."""
    from app.services import objekt_marke as om
    try:
        logo = om.pruefe_logo(data.get("logo"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _marke_speichern(db, user, object_id, {"logo": logo}, "Logo hochgeladen")


@router.delete("/objekte/{object_id}/logo")
def objekt_logo_entfernen(object_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    return _marke_speichern(db, user, object_id, {"logo": None}, "Logo entfernt")


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

    # 3) Monatsabschluss: bis einschliesslich Exporttag des Vormonats geht es um den Vormonat (der wird abgeschlossen)
    from app.services.export_termine import vormonat
    monat = vormonat(today) if today <= exporttag(vormonat(today)) else today.strftime("%Y-%m")
    ex = exporttag(monat)
    a0, a1 = _month_bounds(date.fromisoformat(f"{monat}-01"))
    aktive_ma = _q(db, f"""SELECT DISTINCT s.employee_id FROM schedules s JOIN employees e ON e.id = s.employee_id
                           WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND NOT coalesce(e.is_test,false)
                             AND coalesce(s.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})""", a=a0, b=a1)
    bestaetigt = _q(db, "SELECT count(*) AS n FROM monthly_confirmations WHERE year = :y AND month = :m AND status = 'confirmed'",
                    y=a0.year, m=a0.month)[0]["n"]
    te_mon = """FROM time_entries t JOIN employees e ON e.id = t.employee_id
                WHERE NOT coalesce(e.is_test,false) AND (t.check_in::date BETWEEN :a AND :b OR t.check_out::date BETWEEN :a AND :b)"""
    p_gvk = _q(db, f"SELECT count(*) AS n {te_mon} AND t.check_out < t.check_in", a=a0, b=a1)[0]["n"]
    p_neg = _q(db, f"SELECT count(*) AS n {te_mon} AND t.billed_hours < 0", a=a0, b=a1)[0]["n"]
    p_ohne = _q(db, f"SELECT count(*) AS n {te_mon} AND t.check_out IS NULL AND t.check_in < now() - interval '14 hours'", a=a0, b=a1)[0]["n"]
    p_km = _q(db, """SELECT count(*) AS n FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id
                     WHERE coalesce(a.is_active,true) AND coalesce(a.is_driver,false) AND e.is_active AND NOT coalesce(e.is_test,false)
                       AND a.object_id NOT IN (19, 999)
                       AND NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = a.object_id)""")[0]["n"]
    p_nach = _q(db, "SELECT count(*) AS n FROM pending_bookings WHERE status = 'offen'")[0]["n"]
    p_ohne_st = len(ohne_stempel(db, a0, a1))
    pruef = [
        {"key": "gehen_vor_kommen", "n": p_gvk, "link": f"/cockpit/zeiten?pruef=gehen_vor_kommen&monat={monat}"},
        {"key": "negative_stunden", "n": p_neg, "link": f"/cockpit/zeiten?pruef=negative_stunden&monat={monat}"},
        {"key": "ohne_gehen", "n": p_ohne, "link": f"/cockpit/zeiten?pruef=ohne_gehen&monat={monat}"},
        {"key": "ohne_stempel", "n": p_ohne_st, "link": f"/cockpit/zeiten?pruef=ohne_stempel&monat={monat}"},
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
                       AND coalesce(t.object_id,0) NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                       AND coalesce(t.service_type, '') NOT IN ({_KEIN_STEMPEL})""", a=m0, b=m1)
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

    from app.services import plan_vorlage as pv
    plan_nw = pv.wochen_status(db, pv.montag(today) + timedelta(days=7))
    return {"woche": woche, "abschluss": abschluss, "stunden": stunden, "km": km, "feed": feed[:25], "plan_naechste_woche": plan_nw,
            "minijob": _minijob_warnungen(db, user, now), "marge": _marge_warnungen(db, user, now),
            "mehrzeit": _mehrzeit_woche(db, today)}


def _mehrzeit_woche(db, today):
    """Mehrzeit-Antraege je MA in dieser Woche (Mo-So, nach Arbeitstag) + Einstellung "Frage ab ... Min"."""
    from app.services import mehrzeit as mz
    montag = today - timedelta(days=today.weekday())
    return {"montag": montag.isoformat(), "frage_ab_min": mz.frage_ab(db), "fenster_tage": mz.FENSTER_TAGE,
            "personen": [{**r, "name": f"{r['first_name']} {r['last_name']}"} for r in mz.woche(db, montag)]}


@router.put("/einstellungen/mehrzeit")
def mehrzeit_einstellung(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Ab wie vielen Minuten nach Schichtende die App "Hast du laenger gearbeitet?" fragt. Nur Admin."""
    _nur_admin(user)
    from app.services import mehrzeit as mz
    try:
        return mz.frage_ab_speichern(db, (data or {}).get("frage_ab_min"), user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _minijob_warnungen(db, user, now):
    """Minijobber ab Warn-Prozent (Hochrechnung bis Monatsende). Objektleitung sieht nur Prozent/Reststunden, keine Euro."""
    from app.services import minijob as mj
    try:
        rows = [r for r in mj.hochrechnung(db, now.year, now.month, now) if r["stufe"] != "ok" or r["unter_mindestlohn"]]
    except Exception:
        return []
    if not ol_scope.is_admin(user):
        rows = [{k: v for k, v in r.items() if k not in ("ist", "geplant", "hochrechnung", "stundenlohn", "grenze")} for r in rows]
    return rows


def _marge_warnungen(db, user, now):
    if not ol_scope.is_admin(user):          # Objekt-Marge nur fuer Admin
        return None
    from app.services import objekt_marge as om
    try:
        return om.warnungen(db, now)
    except Exception:
        return []


# --- Plan aus Vorlage (Stamm-Dienstplan), Luecken, Kontingent, "Plan naechste Woche" -------------
def _hhmm(v, feld):
    try:
        return datetime.strptime(str(v), "%H:%M").time()
    except (TypeError, ValueError):
        raise HTTPException(400, f"{feld}: Uhrzeit als HH:MM")


def _vorlage_json(m):
    return {"id": m["id"], "employee_id": m["employee_id"], "name": m["name"], "personal_nr": m["personal_nr"],
            "object_id": m["object_id"], "objekt": m["objekt"], "wochentag": m["weekday"], "tag": WOCHENTAG[m["weekday"]],
            "beginn": _hm(m["start_time"]), "ende": _hm(m["end_time"]), "fahrer": bool(m["is_driver"]),
            "rhythmus": m["rhythm"], "monatswoche": m["month_week"], "stunden": round(_vl_std(m["start_time"], m["end_time"]), 2)}


def _vl_std(b, e):
    return ((_min(e) - _min(b)) % 1440 or 1440) / 60


@router.get("/vorlage")
def vorlage_liste(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Vorlage (Stamm-Dienstplan) mit Wochenstunden je MA (woechentliche Eintraege voll, 14-taegl. halb, monatl. 1/4)."""
    from app.services import plan_vorlage as pv
    obj, _ = _scope(db, user)
    rows = [_vorlage_json(m) for m in pv.vorlage(db, obj)]
    faktor = {"weekly": 1, "biweekly_even": 0.5, "biweekly_odd": 0.5, "monthly": 0.25}
    std = {}
    for r in rows:
        std[r["employee_id"]] = round(std.get(r["employee_id"], 0) + r["stunden"] * faktor.get(r["rhythmus"], 1), 2)
    return {"eintraege": rows, "wochenstunden": std}


def _vorlage_daten(db, data, alt=None):
    alt = alt or {}
    v = {"employee_id": int(data.get("employee_id") or alt.get("employee_id") or 0),
         "object_id": int(data.get("object_id") or alt.get("object_id") or 0),
         "weekday": int(data["wochentag"]) if data.get("wochentag") is not None else alt.get("weekday"),
         "start_time": _hhmm(data.get("beginn") or _hm(alt.get("start_time")), "beginn"),
         "end_time": _hhmm(data.get("ende") or _hm(alt.get("end_time")), "ende"),
         "is_driver": bool(data["fahrer"]) if "fahrer" in data else bool(alt.get("is_driver", True)),
         "rhythm": data.get("rhythmus") or alt.get("rhythm") or "weekly",
         "month_week": data.get("monatswoche") if "monatswoche" in data else alt.get("month_week")}
    from app.services.plan_vorlage import RHYTHMEN
    if not v["employee_id"] or not v["object_id"]:
        raise HTTPException(400, "Mitarbeiter und Objekt angeben")
    if v["weekday"] not in range(7):
        raise HTTPException(400, "Wochentag 0 (Mo) bis 6 (So)")
    if v["start_time"] == v["end_time"]:
        raise HTTPException(400, "Ende muss nach Beginn liegen")
    if v["rhythm"] not in RHYTHMEN:
        raise HTTPException(400, "Unbekannter Rhythmus")
    if v["rhythm"] == "monthly" and v["month_week"] not in (1, 2, 3, 4, -1):
        v["month_week"] = 1
    if v["rhythm"] != "monthly":
        v["month_week"] = None
    if not _q(db, "SELECT 1 FROM employees WHERE id = :i AND is_active", i=v["employee_id"]):
        raise HTTPException(400, "Mitarbeiter nicht aktiv")
    if not _q(db, f"SELECT 1 FROM objects WHERE id = :i AND id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})", i=v["object_id"]):
        raise HTTPException(400, "Objekt nicht gefunden")
    # Doppelbelegung in der Vorlage (gleicher MA, gleicher Wochentag, Zeiten ueberschneiden sich)
    for r in _q(db, """SELECT m.id, m.start_time, m.end_time, o.name FROM master_schedule_entries m JOIN objects o ON o.id = m.object_id
                       WHERE m.employee_id = :e AND m.weekday = :w AND coalesce(m.is_active,true) AND m.id <> :i""",
                e=v["employee_id"], w=v["weekday"], i=alt.get("id") or 0):
        if _ueberlappt(_min(v["start_time"]), _min(v["end_time"]), _min(r["start_time"]), _min(r["end_time"])):
            raise HTTPException(409, f"Doppelbelegung in der Vorlage: {r['name']} {_hm(r['start_time'])}–{_hm(r['end_time'])}")
    v["planned_hours"] = round(_vl_std(v["start_time"], v["end_time"]), 2)
    return v


def _vorlage_eintrag(db, vid):
    from app.services import plan_vorlage as pv
    r = [m for m in pv.vorlage(db) if m["id"] == vid]
    if not r:
        raise HTTPException(404, "Vorlage-Eintrag nicht gefunden")
    return r[0]


def _vl_text(v, db):
    n = _q(db, "SELECT first_name || ' ' || last_name AS n FROM employees WHERE id = :i", i=v["employee_id"])[0]["n"]
    o = _q(db, "SELECT name FROM objects WHERE id = :i", i=v["object_id"])[0]["name"]
    return f"{n}, {WOCHENTAG[v['weekday']]} {_hm(v['start_time'])}-{_hm(v['end_time'])}, {o}"


@router.post("/vorlage")
def vorlage_anlegen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    v = _vorlage_daten(db, data)
    if _q(db, """SELECT 1 FROM master_schedule_entries WHERE employee_id = :employee_id AND object_id = :object_id
                 AND weekday = :weekday AND coalesce(rhythm,'weekly') = :rhythm""", **v):
        raise HTTPException(409, "Diesen Eintrag gibt es in der Vorlage schon (gleicher MA, Objekt, Wochentag, Rhythmus)")
    vid = db.execute(text("""INSERT INTO master_schedule_entries (employee_id, object_id, weekday, start_time, end_time, planned_hours,
                                    is_driver, is_active, rhythm, month_week, created_at)
                             VALUES (:employee_id, :object_id, :weekday, :start_time, :end_time, :planned_hours, :is_driver, true,
                                     :rhythm, :month_week, now()) RETURNING id"""), v).scalar()
    log_audit(db, user.id, v["employee_id"], "vorlage_angelegt", entity_type="master_schedule", entity_id=vid,
              details=f"Vorlage: {_vl_text(v, db)}")
    db.commit()
    return _vorlage_json(_vorlage_eintrag(db, vid))


@router.put("/vorlage/{vid}")
def vorlage_aendern(vid: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    alt = _q(db, "SELECT * FROM master_schedule_entries WHERE id = :i", i=vid)
    if not alt:
        raise HTTPException(404, "Vorlage-Eintrag nicht gefunden")
    alt = dict(alt[0])
    altjson = _vorlage_json(_vorlage_eintrag(db, vid))
    v = _vorlage_daten(db, data, alt)
    if _q(db, """SELECT 1 FROM master_schedule_entries WHERE employee_id = :employee_id AND object_id = :object_id
                 AND weekday = :weekday AND coalesce(rhythm,'weekly') = :rhythm AND id <> :id""", **v, id=vid):
        raise HTTPException(409, "Diesen Eintrag gibt es in der Vorlage schon (gleicher MA, Objekt, Wochentag, Rhythmus)")
    db.execute(text("""UPDATE master_schedule_entries SET employee_id = :employee_id, object_id = :object_id, weekday = :weekday,
                              start_time = :start_time, end_time = :end_time, planned_hours = :planned_hours, is_driver = :is_driver,
                              rhythm = :rhythm, month_week = :month_week WHERE id = :id"""), {**v, "id": vid})
    log_audit(db, user.id, v["employee_id"], "vorlage_geaendert", entity_type="master_schedule", entity_id=vid,
              old_value=altjson, details=f"Vorlage geaendert: {_vl_text(v, db)}")
    db.commit()
    return {"alt": altjson, "neu": _vorlage_json(_vorlage_eintrag(db, vid))}


@router.delete("/vorlage/{vid}")
def vorlage_loeschen(vid: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    alt = _vorlage_json(_vorlage_eintrag(db, vid))
    db.execute(text("DELETE FROM master_schedule_entries WHERE id = :i"), {"i": vid})
    log_audit(db, user.id, alt["employee_id"], "vorlage_geloescht", entity_type="master_schedule", entity_id=vid, old_value=alt,
              details=f"Vorlage geloescht: {alt['name']}, {alt['tag']} {alt['beginn']}-{alt['ende']}, {alt['objekt']}")
    db.commit()
    return {"status": "geloescht", "alt": alt}


@router.post("/vorlage/aus-woche")
def vorlage_aus_woche(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Vorlage aus einer vorhandenen Planwoche fuellen (woechentlich). vorschau=true: nur anzeigen.
    Schon vorhandene Vorlage-Eintraege (MA/Objekt/Wochentag) und Sonntage der Sonntagsregel werden ausgelassen."""
    from app.services import plan_vorlage as pv, sonntag_d0002 as so
    mo = pv.montag(_d(data.get("woche"), "woche"))
    obj, _ = _scope(db, user)
    nur_obj = int(data["object_id"]) if data.get("object_id") else None
    rows = _q(db, f"""SELECT s.employee_id, s.object_id, s.date, s.start_time, s.end_time, s.is_driver, o.name AS objekt,
                             e.first_name || ' ' || e.last_name AS name
                        FROM schedules s JOIN employees e ON e.id = s.employee_id JOIN objects o ON o.id = s.object_id
                       WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal','vertretung') AND e.is_active AND NOT coalesce(e.is_test,false)
                         AND s.start_time IS NOT NULL AND s.end_time IS NOT NULL
                         AND s.object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK}) AND {_flt('s.object_id', obj)}
                       ORDER BY s.date, s.start_time, name""", **_params(obj, None, a=mo, b=mo + timedelta(days=6)))
    da = {(r["employee_id"], r["object_id"], r["weekday"]) for r in _q(db, """SELECT employee_id, object_id, weekday
                                                                              FROM master_schedule_entries WHERE coalesce(is_active,true)""")}
    out, neu = [], set()
    for r in rows:
        if nur_obj and r["object_id"] != nur_obj:
            continue
        k = (r["employee_id"], r["object_id"], r["date"].weekday())
        grund = ("Sonntag kommt aus der Sonntagsautomatik" if r["employee_id"] == so.RULE_EMPLOYEE_ID and r["date"].weekday() == 6
                 else "schon in der Vorlage" if k in da else "doppelt in der Woche" if k in neu else None)
        if not grund:
            neu.add(k)
        out.append({"employee_id": r["employee_id"], "name": r["name"], "object_id": r["object_id"], "objekt": r["objekt"],
                    "wochentag": r["date"].weekday(), "tag": WOCHENTAG[r["date"].weekday()], "beginn": _hm(r["start_time"]),
                    "ende": _hm(r["end_time"]), "fahrer": bool(r["is_driver"]), "status": "ok" if not grund else "konflikt", "grund": grund})
    res = {"woche": mo.isoformat(), "eintraege": out, "anzulegen": sum(1 for o in out if o["status"] == "ok"),
           "uebersprungen": sum(1 for o in out if o["status"] != "ok")}
    if data.get("vorschau", True):
        return {**res, "vorschau": True}
    ids = []
    for o in out:
        if o["status"] != "ok":
            continue
        v = _vorlage_daten(db, {"employee_id": o["employee_id"], "object_id": o["object_id"], "wochentag": o["wochentag"],
                                "beginn": o["beginn"], "ende": o["ende"], "fahrer": o["fahrer"]})
        vid = db.execute(text("""INSERT INTO master_schedule_entries (employee_id, object_id, weekday, start_time, end_time, planned_hours,
                                        is_driver, is_active, rhythm, created_at)
                                 VALUES (:employee_id, :object_id, :weekday, :start_time, :end_time, :planned_hours, :is_driver, true,
                                         'weekly', now()) RETURNING id"""), v).scalar()
        ids.append(vid)
        log_audit(db, user.id, v["employee_id"], "vorlage_angelegt", entity_type="master_schedule", entity_id=vid,
                  details=f"Vorlage aus Woche {mo.strftime('%d.%m.%Y')}: {_vl_text(v, db)}")
    db.commit()
    return {**res, "vorschau": False, "ids": ids}


@router.post("/dienstplan/aus-vorlage")
def woche_aus_vorlage(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Woche nur aus der Vorlage erzeugen (nicht aus der Vorwoche). Urlaub/Krank/Absage: keine Schicht, sondern offene Luecke.
    vorschau=true (Standard): nur anzeigen. Speichern in EINER Transaktion, Rueckgaengig ueber /dienstplan/kopie/{id}."""
    from app.services import plan_vorlage as pv
    mo = pv.montag(_d(data.get("woche"), "woche"))
    obj, _ = _scope(db, user)
    soll = pv.soll(db, mo, mo + timedelta(days=6), obj)
    if not soll:
        raise HTTPException(400, "Die Vorlage ist leer – bitte zuerst Vorlage anlegen")
    neu = [{"vorlage_id": m["id"], "employee_id": m["employee_id"], "object_id": m["object_id"], "datum": d,
            "start": m["start_time"], "ende": m["end_time"], "fahrer": bool(m["is_driver"])} for m, d in soll]
    plan = _pruefe_neue(db, neu, mo, mo + timedelta(days=6))
    plan["luecken"] = sum(1 for e in plan["eintraege"] if e["status"] == "abwesend")
    if data.get("vorschau", True):
        return {**plan, "woche": mo.isoformat(), "vorschau": True}
    r = _anlegen(db, user, plan, "Schicht aus Vorlage")
    return {**r, "woche": mo.isoformat(), "luecken": plan["luecken"]}


@router.post("/dienstplan/fertig")
def woche_fertig(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Planwoche als fertig melden (fertig=false: wieder oeffnen)."""
    from app.services import plan_vorlage as pv
    return pv.fertig_setzen(db, pv.montag(_d(data.get("woche"), "woche")), user, bool(data.get("fertig", True)))


# --- Kontingent (Festgehalt): Soll / verplant / Rest, Rest gleichmaessig auf Werktage verteilen -----
def _monat(v):
    try:
        y, m = map(int, str(v).split("-"))
        return date(y, m, 1)
    except (TypeError, ValueError):
        raise HTTPException(400, "monat als JJJJ-MM")


def _plan_std(r):
    if r["planned_hours"] is not None:
        return float(r["planned_hours"])
    return _vl_std(r["start_time"], r["end_time"])


def _kontingent_person(db, eid, m0):
    from app.services import festgehalt, sonntag_d0002 as so
    m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    fg = festgehalt.active_on(db, eid, m0)
    if not fg:
        return None
    rows = _q(db, f"""SELECT date, start_time, end_time, planned_hours FROM schedules WHERE employee_id = :e AND date BETWEEN :a AND :b
                      AND status IN ('normal','vertretung') AND object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                      AND start_time IS NOT NULL AND end_time IS NOT NULL""", e=eid, a=m0, b=m1)
    sonntage, werk = {}, 0.0
    for r in rows:
        if r["date"].weekday() == 6:
            spanne = _vl_std(r["start_time"], r["end_time"])
            h = spanne - so.BREAK_MINUTES / 60 if spanne > so.BREAK_FROM_HOURS else spanne   # wie die Sonntagsbuchung
            sonntage[r["date"]] = {"datum": r["date"].isoformat(), "stunden": round(h, 2), "angelegt": True}
        else:
            werk += _plan_std(r)
    if not sonntage and so.applies(eid, m0 + timedelta(days=(6 - m0.weekday()) % 7)):
        # Sonntagsautomatik legt die ersten 3 Sonntage am 20. des Vormonats an - bis dahin als erwartet zeigen
        d = m0 + timedelta(days=(6 - m0.weekday()) % 7)
        spanne = _vl_std(so.FILL_START, so.FILL_END)
        for _ in range(so.MAX_SUNDAYS):
            sonntage[d] = {"datum": d.isoformat(), "stunden": round(spanne - so.BREAK_MINUTES / 60, 2), "angelegt": False}
            d += timedelta(days=7)
    so_h = round(sum(x["stunden"] for x in sonntage.values()), 2)
    name = _q(db, "SELECT first_name || ' ' || last_name AS n, personal_nr FROM employees WHERE id = :i", i=eid)[0]
    soll = float(fg.monatsstunden or 0)
    return {"employee_id": eid, "name": name["n"], "personal_nr": name["personal_nr"], "monat": m0.strftime("%Y-%m"),
            "soll": soll, "sonntag_stunden": so_h, "sonntage": sorted(sonntage.values(), key=lambda x: x["datum"]),
            "sonntage_automatisch": eid == so.RULE_EMPLOYEE_ID and m1 >= so.RULE_START,
            "werktag_stunden": round(werk, 2), "verplant": round(so_h + werk, 2), "rest": round(soll - so_h - werk, 2)}


@router.get("/kontingent")
def kontingent(monat: str = Query(None), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Monatskontingent fuer MA mit Festgehalt: Soll, Sonntage, Werktage, verplant, Rest."""
    from app.services import festgehalt
    m0 = _monat(monat) if monat else date.today().replace(day=1)
    out = [_kontingent_person(db, eid, m0) for eid in sorted(festgehalt.active_employee_ids(db, m0.year, m0.month))]
    return {"monat": m0.strftime("%Y-%m"), "personen": [p for p in out if p]}


@router.post("/kontingent/verteilen")
def kontingent_verteilen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Rest-Stunden gleichmaessig auf die freien Werktage (Mo-Fr, ohne Feiertag/Urlaub/Krank/Absage, ab heute) verteilen.
    Objekt und Beginn je Wochentag aus der Vorlage, sonst aus den letzten 8 Wochen. vorschau=true: nur anzeigen.
    Gespeichert wird wie beim Kopieren (Rueckgaengig ueber /dienstplan/kopie/{id}). Am Gehalt aendert sich nichts."""
    from app.services import plan_vorlage as pv
    from app.services.holidays_bw import is_feiertag_bw
    eid = int(data.get("employee_id") or 0)
    m0 = _monat(data.get("monat"))
    m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    p = _kontingent_person(db, eid, m0)
    if not p:
        raise HTTPException(400, "Für diesen Monat ist kein Festgehalt hinterlegt")
    von = max(m0, date.today())
    belegt = {r["date"] for r in _q(db, "SELECT date FROM schedules WHERE employee_id = :e AND date BETWEEN :a AND :b", e=eid, a=von, b=m1)}
    sperre = {**pv.absagen(db, von, m1), **_abwesend_map(db, von, m1)}
    tage = [von + timedelta(days=i) for i in range((m1 - von).days + 1)]
    tage = [d for d in tage if d.weekday() < 5 and not is_feiertag_bw(d) and d not in belegt and (eid, d) not in sperre]
    res = {"monat": p["monat"], "rest": p["rest"], "tage": len(tage), "eintraege": [], "anzulegen": 0, "uebersprungen": 0}
    if p["rest"] <= 0 or not tage:
        return {**res, "vorschau": True, "hinweis": "Kein Rest zu verteilen" if p["rest"] <= 0 else "Keine freien Werktage mehr im Monat"}
    viertel = round(p["rest"] * 4)                          # in Viertelstunden, Rest auf die ersten Tage
    je, ueber = divmod(viertel, len(tage))
    vl = {}
    for m in pv.vorlage(db):
        if m["employee_id"] == eid:
            vl.setdefault(m["weekday"], m)
    ueblich = _q(db, f"""SELECT object_id, start_time, count(*) AS n FROM schedules WHERE employee_id = :e AND date BETWEEN :a AND :b
                         AND extract(isodow FROM date) < 6 AND status IN ('normal','vertretung') AND object_id NOT IN ({OBJ_URLAUB},{OBJ_KRANK})
                         GROUP BY 1, 2 ORDER BY n DESC LIMIT 1""", e=eid, a=date.today() - timedelta(days=56), b=date.today())
    neu = []
    for i, d in enumerate(tage):
        h = (je + (1 if i < ueber else 0)) / 4
        if h <= 0:
            continue
        q = vl.get(d.weekday())
        obj_id = q["object_id"] if q else (ueblich[0]["object_id"] if ueblich else 1)
        beginn = q["start_time"] if q else (ueblich[0]["start_time"] if ueblich else datetime.strptime("13:00", "%H:%M").time())
        ende = (datetime.combine(d, beginn) + timedelta(hours=h)).time()
        neu.append({"employee_id": eid, "object_id": obj_id, "datum": d, "start": beginn, "ende": ende, "fahrer": bool(q and q["is_driver"])})
    plan = _pruefe_neue(db, neu, von, m1)
    if data.get("vorschau", True):
        return {**res, **plan, "vorschau": True}
    return {**res, **_anlegen(db, user, plan, "Kontingent verteilt")}


# --- Minijob-Grenze / Mindestlohn (datumsabhaengig) und Objekt-Marge (nur Admin) -------------------------
def _nur_admin(user):
    if not ol_scope.is_admin(user):
        raise HTTPException(403, "Nur für Admin")


@router.get("/minijob")
def minijob_liste(monat: str = Query(None), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Minijobber mit Ist, geplant, Hochrechnung bis Monatsende und Quote zur Grenze des Monats."""
    from app.services import minijob as mj
    now = datetime.now()
    m0 = _monat(monat) if monat else now.date().replace(day=1)
    rows = mj.hochrechnung(db, m0.year, m0.month, now)
    if not ol_scope.is_admin(user):
        rows = [{k: v for k, v in r.items() if k not in ("ist", "geplant", "hochrechnung", "stundenlohn", "grenze")} for r in rows]
    cfg = mj.einstellung(db)
    db.commit()
    return {"monat": m0.strftime("%Y-%m"), "stufe": mj.stufe_am(db, m0, cfg), "warn_ab_prozent": cfg["warn_ab_prozent"],
            "naechste": mj.naechste_aenderung(db, now.date()), "personen": rows}


@router.get("/einstellungen/lohn-grenzen")
def lohn_grenzen(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    _nur_admin(user)
    from app.services import minijob as mj
    r = mj.einstellung(db)
    db.commit()
    return r


@router.put("/einstellungen/lohn-grenzen")
def lohn_grenzen_speichern(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    _nur_admin(user)
    from app.services import minijob as mj
    try:
        return mj.speichern(db, data, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/objekt-marge")
def objekt_marge(monat: str = Query(None), db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Personalkosten (Stunden x Lohn x Lohnnebenkosten + KM) gegen Umsatz je Objekt, laufender Monat hochgerechnet. Nur Admin."""
    _nur_admin(user)
    from app.services import objekt_marge as om
    now = datetime.now()
    m0 = _monat(monat) if monat else now.date().replace(day=1)
    return om.marge(db, m0.year, m0.month, now)


@router.put("/einstellungen/objekt-marge")
def objekt_marge_ziel(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    _nur_admin(user)
    from app.services import objekt_marge as om
    try:
        return om.speichern(db, data.get("ziel_prozent"), user.id)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) and "%" in str(e) else "Ziel-Marge 0–80 %")
