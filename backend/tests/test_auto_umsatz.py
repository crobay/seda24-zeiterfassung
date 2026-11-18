"""Auto-Monatsumsatz (Job am 1. 06:00): Objekte mit auto_umsatz = False (Einzelauftraege, z. B. Objekt 3
Lidl Muggensturmer Str) bekommen keinen automatischen Vertragsumsatz, alle anderen wie bisher (Drazen 18.11.2026)."""
from datetime import date

from sqlalchemy import text

from app.services import scheduler
from test_stempel_toleranz import engine, Session


class _Dez(date):
    @classmethod
    def today(cls):
        return cls(2026, 12, 1)


def test_job_ueberspringt_objekte_ohne_auto_umsatz(monkeypatch):
    conn = engine.connect(); trans = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        x = lambda sql, **p: db.execute(text(sql), p)
        x("DELETE FROM customer_revenues WHERE year = 2026 AND month = 11")
        x("UPDATE objects SET is_active = true, monthly_amount_netto = 2284 WHERE id = 3")
        x("UPDATE objects SET auto_umsatz = false WHERE id = 3")
        erwartet = set(x("""SELECT id FROM objects WHERE is_active AND NOT is_test AND monthly_amount_netto > 0
                            AND auto_umsatz""").scalars())
        assert erwartet and 3 not in erwartet
        db.commit()
        monkeypatch.setattr(scheduler, "SessionLocal", lambda: Session(bind=conn, join_transaction_mode="create_savepoint"))
        monkeypatch.setattr(scheduler, "date", _Dez)
        scheduler.auto_fill_monthly_revenues()
        rows = dict(x("SELECT object_id, revenue FROM customer_revenues WHERE year = 2026 AND month = 11").all())
        assert 3 not in rows
        assert set(rows) == erwartet
        # zweiter Lauf fuegt nichts doppelt ein
        scheduler.auto_fill_monthly_revenues()
        assert x("SELECT count(*) FROM customer_revenues WHERE year = 2026 AND month = 11").scalar() == len(erwartet)
    finally:
        db.close(); trans.rollback(); conn.close()
