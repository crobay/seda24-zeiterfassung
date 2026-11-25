-- Urlaubskonten: Uebertrag aus dem Vorjahr getrennt merken (Drazen 25.11.2026 20:25)
ALTER TABLE vacation_entitlements ADD COLUMN IF NOT EXISTS days_carried double precision DEFAULT 0;
