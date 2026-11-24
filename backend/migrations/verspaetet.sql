-- Verspaetet uebertragene Stempel (Drazen 24.11.2026): Handy-Zeit und Eingang am Server je Kommen/Gehen festhalten.
-- server_received_at wird beim Gehen ueberschrieben, daher eigene Spalten; spaetere Korrekturen von check_in/check_out
-- aendern den Hinweis nicht. Idempotent.
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS kommen_handy timestamp;
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS kommen_eingang timestamp;
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS gehen_handy timestamp;
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS gehen_eingang timestamp;

-- Nachtragen fuer App-Stempel (client_id, nicht manuell) in nicht abgeschlossenen Monaten:
-- Kommen-Eingang = created_at (Anlage beim Eingang), Gehen-Eingang = server_received_at (beim Gehen gesetzt).
-- Nur Zeiten mit Sekunden-Anteil (App-Stempel); im Cockpit korrigierte Zeiten sind volle Minuten und bleiben ohne Hinweis.
UPDATE time_entries t SET kommen_handy = t.check_in, kommen_eingang = t.created_at,
       gehen_handy = CASE WHEN t.check_out IS NOT NULL AND t.server_received_at >= t.created_at
                           AND extract(second FROM t.check_out) <> 0 THEN t.check_out END,
       gehen_eingang = CASE WHEN t.check_out IS NOT NULL AND t.server_received_at >= t.created_at
                            AND extract(second FROM t.check_out) <> 0 THEN t.server_received_at END
 WHERE t.client_id IS NOT NULL AND extract(second FROM t.check_in) <> 0 AND NOT coalesce(t.is_manual_entry, false) AND t.created_at IS NOT NULL
   AND t.kommen_eingang IS NULL AND t.gehen_eingang IS NULL
   AND to_char(t.check_in, 'YYYY-MM') NOT IN (SELECT monat FROM monatsabschluss WHERE status = 'abgeschlossen')
   AND to_char(coalesce(t.check_out, t.check_in), 'YYYY-MM') NOT IN (SELECT monat FROM monatsabschluss WHERE status = 'abgeschlossen');
