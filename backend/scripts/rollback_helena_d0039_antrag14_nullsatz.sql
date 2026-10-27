-- ROLLBACK: Helena Martin (D0039, employee_id=33), Urlaubsantrag #14 (Juli 2027)
-- Stellt den Ist-Zustand vom 2026-10-28 wieder her (hourly_rate = 0.00 auf allen 10 Zeilen).
-- Nur Antrag #14, nur diese 10 zukuenftigen Urlaubstage, kein anderer Antrag/Mitarbeiter.
-- Anwenden mit:
--   PGPASSWORD=SedaDev2025 psql -U seda24_user -h localhost -d seda24_zeiterfassung \
--     -f scripts/rollback_helena_d0039_antrag14_nullsatz.sql

BEGIN;

UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1912;  -- 2027-07-12
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1913;  -- 2027-07-13
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1914;  -- 2027-07-14
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1915;  -- 2027-07-15
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1916;  -- 2027-07-16
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1917;  -- 2027-07-19
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1918;  -- 2027-07-20
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1919;  -- 2027-07-21
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1920;  -- 2027-07-22
UPDATE time_entries SET hourly_rate = 0.00 WHERE id = 1921;  -- 2027-07-23

SELECT id, check_in::date AS datum, hourly_rate FROM time_entries
WHERE id BETWEEN 1912 AND 1921 ORDER BY id;

COMMIT;
