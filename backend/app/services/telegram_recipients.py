"""
Telegram-Empfaenger fuer Admin-Meldungen (notify_admin).

Empfaenger:
  - 'admin_chat'  = TELEGRAM_ADMIN_CHAT_ID aus .env (Drazen)
  - 'user:<id>'   = aktive Benutzer mit Rolle ADMIN oder OBJEKTLEITER,
                    deren Mitarbeiter eine eigene telegram_chat_id hat
Je Empfaenger und Meldungsart ein Haken (Tabelle telegram_recipient_settings).
Fehlt eine Zeile, gilt der Haken als gesetzt (Standard: alles an).
"""
import os
from sqlalchemy import text

ADMIN_CHAT_KEY = "admin_chat"

CAT_GENEHMIGUNGEN = "genehmigungen"
CAT_STEMPEL = "stempel"
CAT_ABWESENHEIT = "abwesenheit"
CAT_SONSTIGES = "sonstiges"

CATEGORIES = [
    (CAT_GENEHMIGUNGEN, "Genehmigungen", "Mehrzeit, Nachtrag, Korrektur, offene Genehmigungen 9 Uhr"),
    (CAT_STEMPEL, "Nicht gestempelt / Überfällig", "Fehlende Stempel, überfällige Stempel, 48h ohne Antwort"),
    (CAT_ABWESENHEIT, "Urlaub, Tausch, Krankmeldung, Absage", "Urlaubsanträge, Tauschanfragen, Krankmeldungen, Ausfälle"),
    (CAT_SONSTIGES, "Sonstiges", "Nachrichten, verspätete Stempelung, Schichtabfrage-Antworten, Monatskorrektur"),
]
CATEGORY_KEYS = [c[0] for c in CATEGORIES]


def admin_chat_id() -> str:
    return (os.getenv("TELEGRAM_ADMIN_CHAT_ID", "") or "").strip()


def list_recipients(db):
    """Alle moeglichen Empfaenger (ohne Einstellungen)."""
    recipients = []
    acid = admin_chat_id()
    if acid:
        row = db.execute(text(
            "SELECT first_name, last_name FROM employees "
            "WHERE telegram_chat_id::text = :cid AND is_active = true ORDER BY id LIMIT 1"
        ), {"cid": acid}).fetchone()
        name = f"{row.first_name} {row.last_name}" if row else "Admin"
        recipients.append({
            "key": ADMIN_CHAT_KEY, "label": f"{name} (Admin-Chat)", "first_name": row.first_name if row else "Admin",
            "chat_id": acid, "role": "ADMIN_CHAT", "personal_nr": None, "user_id": None,
        })
    rows = db.execute(text("""
        SELECT u.id AS user_id, u.role, e.personal_nr, e.first_name, e.last_name,
               e.telegram_chat_id::text AS chat_id
        FROM users u
        JOIN employees e ON e.user_id = u.id
        WHERE u.is_active = true AND e.is_active = true
          AND u.role::text IN ('ADMIN', 'OBJEKTLEITER')
          AND e.telegram_chat_id IS NOT NULL
        ORDER BY e.personal_nr
    """)).fetchall()
    for r in rows:
        recipients.append({
            "key": f"user:{r.user_id}",
            "label": f"{r.first_name} {r.last_name} ({r.personal_nr}, {'Admin' if r.role == 'ADMIN' else 'Objektleitung'})",
            "first_name": r.first_name, "chat_id": r.chat_id, "role": r.role,
            "personal_nr": r.personal_nr, "user_id": r.user_id,
        })
    return recipients


def load_settings(db):
    """{(recipient_key, category): enabled} - nur explizit gespeicherte Werte."""
    rows = db.execute(text(
        "SELECT recipient_key, category, enabled FROM telegram_recipient_settings"
    )).fetchall()
    return {(r.recipient_key, r.category): bool(r.enabled) for r in rows}


def recipients_with_settings(db):
    settings = load_settings(db)
    out = []
    for r in list_recipients(db):
        r = dict(r)
        r["settings"] = {c: settings.get((r["key"], c), True) for c in CATEGORY_KEYS}
        out.append(r)
    return out


def chat_ids_for_category(db, category: str):
    """Chat-IDs aller Empfaenger mit Haken fuer diese Meldungsart, ohne Doppelte.
    Unbekannte Kategorie -> sonstiges."""
    if category not in CATEGORY_KEYS:
        category = CAT_SONSTIGES
    result = []
    for r in recipients_with_settings(db):
        if r["settings"].get(category, True) and r["chat_id"] and r["chat_id"] not in result:
            result.append(r["chat_id"])
    return result


def approver_for_chat(db, chat_id):
    """Wer darf Admin-Knoepfe druecken? Admin-Chat oder Chat-ID eines aktiven
    Benutzers mit Rolle ADMIN/OBJEKTLEITER. Gibt {"user_id", "name"} oder None."""
    cid = str(chat_id)
    row = db.execute(text("""
        SELECT u.id AS user_id, e.first_name
        FROM employees e JOIN users u ON u.id = e.user_id
        WHERE e.telegram_chat_id::text = :cid AND e.is_active = true AND u.is_active = true
          AND u.role::text IN ('ADMIN', 'OBJEKTLEITER')
        ORDER BY e.id LIMIT 1
    """), {"cid": cid}).fetchone()
    if row:
        return {"user_id": row.user_id, "name": row.first_name}
    if admin_chat_id() and cid == admin_chat_id():
        emp = db.execute(text(
            "SELECT e.user_id, e.first_name FROM employees e "
            "WHERE e.telegram_chat_id::text = :cid AND e.is_active = true ORDER BY e.id LIMIT 1"
        ), {"cid": cid}).fetchone()
        return {"user_id": emp.user_id if emp else None, "name": emp.first_name if emp else "Admin"}
    return None
