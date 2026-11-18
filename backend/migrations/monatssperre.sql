-- Monatssperre (Drazen 18.11.2026): ist ein Monat im Monatsabschluss "abgeschlossen" (Lohn verschickt), darf an
-- seinen lohnrelevanten Daten nichts mehr geaendert werden - egal ueber welchen Weg (Admin, Cockpit, MA-App,
-- Telegram, Scheduler, Skripte). Entsperren nur ueber Cockpit › Monatsabschluss › "Wieder öffnen" (Grund + Protokoll).
-- Fehlercode SD423 -> das Backend macht daraus HTTP 423 mit Klartext.
-- Idempotent: kann beliebig oft eingespielt werden.

SET client_min_messages = warning;

CREATE TABLE IF NOT EXISTS monatsabschluss (
    monat varchar(7) PRIMARY KEY, status varchar(20) NOT NULL DEFAULT 'offen', haken text NOT NULL DEFAULT '{}',
    erzeugt_am timestamp, erzeugt_von integer, gesperrt_am timestamp, gesperrt_von integer);

CREATE OR REPLACE FUNCTION monatssperre_check(von date, bis date) RETURNS void LANGUAGE plpgsql AS $$
DECLARE m text;
BEGIN
    IF von IS NULL THEN RETURN; END IF;
    SELECT min(monat) INTO m FROM monatsabschluss
     WHERE status = 'abgeschlossen' AND monat BETWEEN to_char(von, 'YYYY-MM') AND to_char(coalesce(bis, von), 'YYYY-MM');
    IF m IS NOT NULL THEN
        RAISE EXCEPTION 'MONATSSPERRE: Der Monat %/% ist abgeschlossen (Lohn verschickt). Änderungen nur nach „Wieder öffnen“ im Monatsabschluss.',
            substr(m, 6, 2), substr(m, 1, 4) USING ERRCODE = 'SD423';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION monatssperre_trigger() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record; a date; b date;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    -- alter und neuer Stand werden beide geprueft (Verschieben aus einem / in einen gesperrten Monat)
    FOR r IN SELECT * FROM (SELECT 1 AS k, CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END AS j
                            UNION ALL SELECT 2, CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END) x WHERE j IS NOT NULL LOOP
        IF TG_TABLE_NAME = 'time_entries' THEN
            a := (r.j->>'check_in')::timestamp::date; b := a;
        ELSIF TG_TABLE_NAME = 'break_entries' THEN
            a := (r.j->>'start_time')::timestamp::date; b := a;
        ELSIF TG_TABLE_NAME IN ('km_daily_entries', 'pending_bookings') THEN
            a := (r.j->>'date')::date; b := a;
        ELSIF TG_TABLE_NAME IN ('sick_notes', 'vacation_requests') THEN
            a := (r.j->>'start_date')::date; b := (r.j->>'end_date')::date;
        ELSIF TG_TABLE_NAME IN ('km_monthly_reports', 'zeitkonto', 'monthly_carryovers') THEN
            a := make_date((r.j->>'year')::int, (r.j->>'month')::int, 1); b := a;
        ELSIF TG_TABLE_NAME = 'correction_requests' THEN
            SELECT check_in::date INTO a FROM time_entries WHERE id = (r.j->>'time_entry_id')::int; b := a;
        END IF;
        PERFORM monatssperre_check(a, b);
    END LOOP;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

-- Volle Sperre: jede Aenderung
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['time_entries', 'break_entries', 'km_daily_entries', 'km_monthly_reports', 'sick_notes',
                             'zeitkonto', 'monthly_carryovers'] LOOP
        IF to_regclass(t) IS NOT NULL THEN
            EXECUTE format('DROP TRIGGER IF EXISTS monatssperre ON %I', t);
            EXECUTE format('CREATE TRIGGER monatssperre BEFORE INSERT OR UPDATE OR DELETE ON %I
                            FOR EACH ROW EXECUTE PROCEDURE monatssperre_trigger()', t);
        END IF;
    END LOOP;
    -- Antraege: keine NEUEN Antraege fuer einen gesperrten Monat; Entscheiden/Ablehnen bleibt moeglich
    -- (eine Genehmigung schreibt in time_entries & Co. und wird dort gesperrt).
    FOREACH t IN ARRAY ARRAY['vacation_requests', 'correction_requests', 'pending_bookings'] LOOP
        IF to_regclass(t) IS NOT NULL THEN
            EXECUTE format('DROP TRIGGER IF EXISTS monatssperre ON %I', t);
            EXECUTE format('CREATE TRIGGER monatssperre BEFORE INSERT ON %I
                            FOR EACH ROW EXECUTE PROCEDURE monatssperre_trigger()', t);
        END IF;
    END LOOP;
END $$;
