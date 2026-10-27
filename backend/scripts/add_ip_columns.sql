-- Migration: Netz-Anzeige in der Stempeluhr (Captive-Portal-Hinweis)
-- Additiv + nullable, keine bestehenden Spalten anfassen.
-- Idempotent (ADD COLUMN IF NOT EXISTS) -> gefahrlos mehrfach ausfuehrbar.

ALTER TABLE objects      ADD COLUMN IF NOT EXISTS ip_prefix VARCHAR(32);
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS client_ip VARCHAR(45);

-- Objekt 20 (Lidl Neu Bie2): Praefix der Lidl-Standleitung
UPDATE objects SET ip_prefix = '185.124.194.' WHERE id = 20;
