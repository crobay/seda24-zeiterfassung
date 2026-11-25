-- Taetigkeit bei Sonderreinigung (Drazen 25.11.2026): kurzer Text fuer den Zeitnachweis (z. B. Fenster, Grundreinigung).
-- Art bleibt service_type, Satz hourly_rate (Lohnart ueber service_type) - nur dieses Feld ist neu. Idempotent.
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS taetigkeit varchar(60);
