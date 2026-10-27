-- ROLLBACK: Urlaubssatz Lara Hardt-Fabrizis (D0040, employee_id=34), Antrag #9
-- Stellt den Ist-Zustand vom 2026-10-28 wieder her (hourly_rate = 21.10 auf allen 5 Zeilen).
-- Nur diese 5 Zeilen, kein anderer Mitarbeiter.
-- Anwenden mit:
--   PGPASSWORD=SedaDev2025 psql -U seda24_user -h localhost -d seda24_zeiterfassung \
--     -f scripts/rollback_lara_d0040_antrag9_urlaubssatz.sql

BEGIN;

UPDATE time_entries SET hourly_rate = 21.10 WHERE id = 1666;  -- 2026-09-25
UPDATE time_entries SET hourly_rate = 21.10 WHERE id = 1667;  -- 2026-09-29
UPDATE time_entries SET hourly_rate = 21.10 WHERE id = 1668;  -- 2026-10-02
UPDATE time_entries SET hourly_rate = 21.10 WHERE id = 1669;  -- 2026-10-06
UPDATE time_entries SET hourly_rate = 21.10 WHERE id = 1670;  -- 2026-10-09

-- Kontrolle
SELECT id, check_in::date AS datum, hourly_rate FROM time_entries
WHERE id IN (1666,1667,1668,1669,1670) ORDER BY id;

COMMIT;
