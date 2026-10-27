-- Migration: Nachhol-Verhalten fuer enge Cron-Jobs (MemoryJobStore verliert sie bei Neustart).
-- Additiv, idempotent.
--
-- job_runs haelt je Job den Zeitpunkt des letzten erfolgreichen Laufs. Die Nachhol-Logik
-- in scheduler.run_due_catchup_jobs() (haengt am 15-Min-Job check_overdue_entries) laeuft
-- einen Job nur, wenn der letzte faellige Cron-Termin vorbei ist UND seither nicht gelaufen.
--
-- WICHTIG: Die beiden betroffenen Jobs werden auf now() vorbelegt = "aktuelle Periode bereits
-- erledigt". Dadurch schreibt der Wochen-Job (Urlaubssaetze) beim Neustart NICHT automatisch
-- los; er laeuft erst am naechsten regulaeren Termin (bzw. wenn die Zeile manuell entfernt wird,
-- nach Freigabe des Trockenlaufs).

CREATE TABLE IF NOT EXISTS job_runs (
    job_name    VARCHAR(100) PRIMARY KEY,
    last_run_at TIMESTAMP
);

INSERT INTO job_runs (job_name, last_run_at) VALUES
    ('update_vacation_rates_weekly', now()),
    ('auto_fill_monthly_revenues',  now())
ON CONFLICT (job_name) DO NOTHING;
