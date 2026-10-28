-- ROLLBACK: vacation_entitlements 2026 - Referenz-Urlaubssaetze (Tagessatz)
-- Ist-Stand VOR dem echten Lauf von update_vacation_rates_weekly am 2026-10-28.
-- Stellt je Mitarbeiter den alten vacation_rate wieder her. Beruehrt NUR den Referenzwert,
-- keine gebuchten Urlaubstage (time_entries).
-- Anwenden:
--   PGPASSWORD=SedaDev2025 psql -U seda24_user -h localhost -d seda24_zeiterfassung \
--     -f scripts/rollback_vacation_rates_20261028.sql

BEGIN;

UPDATE vacation_entitlements SET vacation_rate = 41.71  WHERE id = 32;  -- D0001 Drazen Sertic
UPDATE vacation_entitlements SET vacation_rate = 85.05  WHERE id = 24;  -- D0002 Ruzica Sertic
UPDATE vacation_entitlements SET vacation_rate = 57.34  WHERE id = 21;  -- D0004 Ljubica Stjepic
UPDATE vacation_entitlements SET vacation_rate = 74.02  WHERE id = 23;  -- D0021 Matej Stjepic
UPDATE vacation_entitlements SET vacation_rate = 53.28  WHERE id = 25;  -- D0022 Jana Bojko
UPDATE vacation_entitlements SET vacation_rate = 61.19  WHERE id = 27;  -- D0031 Eliane DaSilvaTodaro
UPDATE vacation_entitlements SET vacation_rate = 54.19  WHERE id = 26;  -- D0032 Andreas Frosch
UPDATE vacation_entitlements SET vacation_rate = 34.27  WHERE id = 22;  -- D0034 Sonja Mutlak
UPDATE vacation_entitlements SET vacation_rate = 41.85  WHERE id = 28;  -- D0035 (inaktiv, wird vom Job nicht angefasst)
UPDATE vacation_entitlements SET vacation_rate = 74.30  WHERE id = 29;  -- D0036 Azra Brguljak
UPDATE vacation_entitlements SET vacation_rate = 111.00 WHERE id = 30;  -- D0037 Roul Rumstein (uebersprungen: keine Daten)
UPDATE vacation_entitlements SET vacation_rate = 45.46  WHERE id = 31;  -- D0038 Zyumbyul Kurd
UPDATE vacation_entitlements SET vacation_rate = 65.43  WHERE id = 33;  -- D0039 Helena Martin
UPDATE vacation_entitlements SET vacation_rate = 48.47  WHERE id = 34;  -- D0040 Lara Hardt-Fabrizis

SELECT id, employee_id, vacation_rate FROM vacation_entitlements WHERE year = 2026 ORDER BY id;

COMMIT;
