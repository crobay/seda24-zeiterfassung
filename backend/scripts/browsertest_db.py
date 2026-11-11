#!/usr/bin/env python3
"""
DB-Hilfe fuer den echten Browser-Test (tools/browsertest/offline_test.mjs) und die Screenshots.
Arbeitet NUR mit dem Test-Mitarbeiter T9999 (is_test = true), alles andere wird abgelehnt.

  precheck            T9999 vorhanden, is_test, nicht eingestempelt -> {"employee_id", "max_te_id"}
  entry <client_id>   Zeiteintrag von T9999 mit dieser client_id -> {"id", "check_in", "check_out"} oder null
  cleanup <max_te_id> [grund]
                      loescht alle Zeiteintraege von T9999 mit id > max_te_id samt Pausen, KM,
                      Korrekturen; ein Audit-Eintrag mit den geloeschten IDs
Ausgabe: eine Zeile JSON.
"""
import json
import logging
import os
import sys

logging.FileHandler = lambda *a, **k: logging.NullHandler()
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from sqlalchemy import text  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

PNR = "T9999"


def test_employee(db):
    row = db.execute(text("SELECT id, is_test FROM employees WHERE personal_nr = :p"), {"p": PNR}).fetchall()
    if len(row) != 1 or not row[0][1]:
        raise SystemExit(json.dumps({"error": f"{PNR} fehlt oder ist nicht als Test markiert"}))
    return row[0][0]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    db = SessionLocal()
    try:
        emp = test_employee(db)
        if cmd == "precheck":
            open_ids = [r[0] for r in db.execute(text(
                "SELECT id FROM time_entries WHERE employee_id = :e AND check_out IS NULL"), {"e": emp})]
            max_id = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM time_entries")).scalar()
            print(json.dumps({"employee_id": emp, "max_te_id": max_id, "open_entries": open_ids}))
        elif cmd == "entry":
            r = db.execute(text("""SELECT id, check_in, check_out FROM time_entries
                                   WHERE employee_id = :e AND client_id = :c"""),
                           {"e": emp, "c": sys.argv[2]}).fetchone()
            print(json.dumps(r and {"id": r[0], "check_in": str(r[1]), "check_out": r[2] and str(r[2])}))
        elif cmd == "cleanup":
            since = int(sys.argv[2])
            reason = sys.argv[3] if len(sys.argv) > 3 else "Browser-Test"
            ids = [r[0] for r in db.execute(text(
                "SELECT id FROM time_entries WHERE employee_id = :e AND id > :s ORDER BY id"), {"e": emp, "s": since})]
            counts = {}
            if ids:
                p = {"e": emp, "ids": ids}
                for t in ("break_entries", "km_daily_entries", "correction_requests"):
                    counts[t] = db.execute(text(
                        f"DELETE FROM {t} WHERE time_entry_id = ANY(:ids) AND time_entry_id IN "
                        f"(SELECT id FROM time_entries WHERE employee_id = :e)"), p).rowcount
                counts["time_entries"] = db.execute(text(
                    "DELETE FROM time_entries WHERE employee_id = :e AND id = ANY(:ids)"), p).rowcount
                db.execute(text("""INSERT INTO audit_log (user_id, employee_id, action, entity_type, entity_id,
                                                          old_value, new_value, details, created_at)
                                   VALUES (NULL, :e, 'test_entries_deleted', 'time_entry', NULL,
                                           :old, NULL, :d, NOW())"""),
                           {"e": emp, "old": json.dumps({"time_entry_ids": ids, "counts": counts}),
                            "d": f"{reason}: Testbuchungen von {PNR} wieder geloescht (IDs {ids})"})
            db.commit()
            print(json.dumps({"deleted": ids, "counts": counts}))
        else:
            raise SystemExit(__doc__)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
