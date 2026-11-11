-- Test-Kennzeichen fuer Mitarbeiter und Objekte (z.B. T9999 / "TEST BrowserStack").
-- Test-Daten erscheinen nicht in Lohnuebersicht, Lexware, PDF-Abrechnung, Lohn-Mail
-- und Telegram-Meldungen an Admin/Rosi. Nur additiv, Vorgabe false.
ALTER TABLE employees ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE objects   ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;
-- Rollback:
-- ALTER TABLE employees DROP COLUMN is_test;
-- ALTER TABLE objects   DROP COLUMN is_test;
