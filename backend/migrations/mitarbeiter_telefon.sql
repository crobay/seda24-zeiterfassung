-- Handynummer je Mitarbeiter fuer den Anrufen-Knopf im Anwesend-Blatt (Drazen 26.11.2026 18:21)
ALTER TABLE employees ADD COLUMN IF NOT EXISTS telefon varchar(40);
