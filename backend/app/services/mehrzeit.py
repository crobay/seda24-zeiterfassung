"""Mehrzeit nach Schichtende - Regel Drazen 19.11.2026 (ersetzt den automatischen Mehrzeit-Antrag).

- Gezaehlt wird immer nur Schichtbeginn bis Schichtende laut Dienstplan (Kommen ab Beginn-10, Gehen beliebig spaeter).
- Gehen bis Schichtende + (FRAGE_AB-1) Min: keine Frage, kein Antrag moeglich.
- Gehen ab Schichtende + FRAGE_AB Min (Einstellung, Standard 15): die App fragt direkt nach dem Gehen
  "Hast du laenger gearbeitet?". Nur bei "Ja" + Pflicht-Grund entsteht ein Mehrzeit-Antrag an die Genehmiger,
  minutengenau ab Schichtende bis zum gestempelten Gehen (nie mehr als gestempelt).
- Frage weggedrueckt: in der Historie beim Eintrag FENSTER_TAGE lang "Mehrzeit beantragen", danach und in
  gesperrten Monaten nicht mehr. Pro Zeiteintrag hoechstens ein Mehrzeit-Antrag.
"""
import math
import os
from datetime import datetime, timedelta

from sqlalchemy import text

FRAGE_AB_KEY = "mehrzeit_frage_ab_min"
FRAGE_AB_STANDARD = 15
FENSTER_TAGE = 3
GRUND_MIN, GRUND_MAX = 10, 300


def _hat_tabelle(db, name):
    return bool(db.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": name}).scalar())


def frage_ab(db) -> int:
    """Ab wie vielen Minuten nach Schichtende gefragt wird. Cockpit-Einstellung (app_settings), sonst
    MEHRZEIT_FRAGE_AB_MIN aus backend/.env, sonst 15."""
    if _hat_tabelle(db, "app_settings"):
        v = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": FRAGE_AB_KEY}).scalar()
        if v and str(v).strip().isdigit():
            return int(str(v).strip())
    try:
        return int(os.getenv("MEHRZEIT_FRAGE_AB_MIN", FRAGE_AB_STANDARD))
    except ValueError:
        return FRAGE_AB_STANDARD


def frage_ab_speichern(db, minuten, user_id):
    try:
        n = int(minuten)
    except (TypeError, ValueError):
        raise ValueError("Bitte eine ganze Zahl an Minuten angeben")
    if not 5 <= n <= 120:
        raise ValueError("Erlaubt sind 5 bis 120 Minuten")
    alt = frage_ab(db)
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": FRAGE_AB_KEY, "v": str(n), "u": user_id})
    from app.services.booking_service import log_audit
    log_audit(db, user_id, None, "mehrzeit_frage_ab_geaendert", entity_type="einstellung",
              old_value={"minuten": alt}, new_value={"minuten": n},
              details=f"Mehrzeit-Frage ab {alt} -> {n} Min nach Schichtende")
    db.commit()
    return {"frage_ab_min": n}


def minuten_nach_ende(check_in: datetime, check_out: datetime, ende: datetime) -> int:
    """Ganze Minuten ab Schichtende (bzw. ab Kommen, falls spaeter) bis Gehen - abgerundet, nie mehr als gestempelt."""
    if not check_out or check_out <= ende:
        return 0
    return max(0, math.floor((check_out - max(ende, check_in)).total_seconds() / 60))


def stunden(minuten: int) -> float:
    """Minuten -> Stunden fuer pending_bookings (numeric 5,2), abgerundet: nie mehr als gestempelt."""
    return math.floor(minuten * 100 / 60) / 100


def monat_gesperrt(db, tag) -> bool:
    """Abgeschlossener Monat (Monatsabschluss im Cockpit). Ohne Cockpit-Tabellen: nie gesperrt."""
    if not _hat_tabelle(db, "monatsabschluss"):
        return False
    st = db.execute(text("SELECT status FROM monatsabschluss WHERE monat = :m"), {"m": tag.strftime("%Y-%m")}).scalar()
    return st == "abgeschlossen"


def vorhandener_antrag(db, entry_id):
    return db.execute(text("""SELECT id, status FROM pending_bookings WHERE related_time_entry_id = :te
                              AND reason = 'mehrzeit_dienstplan' ORDER BY id LIMIT 1"""), {"te": entry_id}).first()


def pruefen(db, entry, now=None):
    """Kann zu diesem Zeiteintrag (noch) Mehrzeit beantragt werden?
    Gibt {"minuten", "schicht", "schicht_ende", "gehen", "bis"} zurueck, sonst {"grund": "..."} mit dem Hinderungsgrund."""
    from app.api.v1.endpoints.time_entries import schicht_fuer_stempel
    now = now or datetime.now()
    if not entry.check_out:
        return {"grund": "Noch nicht ausgestempelt"}
    schicht = schicht_fuer_stempel(entry.employee_id, entry.object_id, entry.check_in, db)
    if not schicht:
        return {"grund": "Keine Schicht im Dienstplan"}
    _, beginn, ende = schicht
    minuten = minuten_nach_ende(entry.check_in, entry.check_out, ende)
    ab = frage_ab(db)
    if minuten < ab:
        return {"grund": f"Weniger als {ab} Minuten nach Schichtende"}
    a = vorhandener_antrag(db, entry.id)
    if a:
        return {"grund": "Mehrzeit ist schon beantragt", "antrag_id": a.id, "antrag_status": a.status}
    bis = entry.check_out + timedelta(days=FENSTER_TAGE)
    if now > bis:
        return {"grund": f"Mehrzeit kann nur {FENSTER_TAGE} Tage lang beantragt werden"}
    if monat_gesperrt(db, entry.check_in.date()):
        return {"grund": "Der Monat ist abgeschlossen"}
    return {"minuten": minuten, "schicht": f"{beginn:%H:%M}-{ende:%H:%M}", "schicht_ende": f"{ende:%H:%M}",
            "gehen": f"{entry.check_out:%H:%M}", "bis": bis.isoformat(timespec="minutes")}


def frage(db, entry):
    """Fuer die Antwort auf das Gehen: Frage anzeigen? (gleiche Regeln wie pruefen)"""
    p = pruefen(db, entry)
    if "minuten" not in p:
        return None
    return {"entry_id": entry.id, "minuten": p["minuten"], "schicht": p["schicht"], "schicht_ende": p["schicht_ende"],
            "gehen": p["gehen"], "frage_ab": frage_ab(db)}


def woche(db, montag):
    """Mehrzeit-Antraege je MA in der Woche ab montag (nach Arbeitstag), mit Status."""
    rows = db.execute(text("""SELECT pb.employee_id, e.personal_nr, e.first_name, e.last_name,
                                     count(*) AS anzahl,
                                     count(*) FILTER (WHERE pb.status = 'offen') AS offen,
                                     count(*) FILTER (WHERE pb.status = 'genehmigt') AS genehmigt,
                                     count(*) FILTER (WHERE pb.status IN ('abgelehnt', 'erledigt')) AS abgelehnt,
                                     coalesce(sum(pb.requested_hours), 0) AS stunden
                              FROM pending_bookings pb JOIN employees e ON e.id = pb.employee_id
                              WHERE pb.reason = 'mehrzeit_dienstplan' AND pb.date BETWEEN :a AND :b
                              GROUP BY 1, 2, 3, 4 ORDER BY anzahl DESC, e.last_name"""),
                      {"a": montag, "b": montag + timedelta(days=6)}).mappings().all()
    return [{**dict(r), "stunden": float(r["stunden"])} for r in rows]
