-- Monatssperre (Drazen 18.11.2026): ist ein Monat im Monatsabschluss "abgeschlossen" (Lohn verschickt), darf an
-- seinen lohnrelevanten Daten nichts mehr geaendert werden - egal ueber welchen Weg (Admin, Cockpit, MA-App,
-- Telegram, Scheduler, Skripte). Entsperren nur ueber Cockpit › Monatsabschluss › "Wieder öffnen" (Grund + Protokoll).
-- Fehlercode SD423 -> das Backend macht daraus HTTP 423 mit Klartext.
-- Idempotent: kann beliebig oft eingespielt werden.

SET client_min_messages = warning;

CREATE TABLE IF NOT EXISTS monatsabschluss (
    monat varchar(7) PRIMARY KEY, status varchar(20) NOT NULL DEFAULT 'offen', haken text NOT NULL DEFAULT '{}',
    erzeugt_am timestamp, erzeugt_von integer, gesperrt_am timestamp, gesperrt_von integer);

-- ---------------------------------------------------------------------------------------------------------------
-- Wieder oeffnen nur mit Super-PIN (Drazen 19.11.2026, GoBD): jede Oeffnung, jede Aenderung im geoeffneten Monat
-- (alt/neu, wer, wann, Grund) und das erneute Sperren stehen unveraenderbar in monatsabschluss_aenderung
-- (Hash-Kette). Die Tabellen gehoeren postgres; der App-Benutzer darf nur lesen und anfuegen.
CREATE TABLE IF NOT EXISTS superpin (
    nur_eine boolean PRIMARY KEY DEFAULT true CHECK (nur_eine), user_id integer NOT NULL, pin_hash text,
    fehlversuche integer NOT NULL DEFAULT 0, gesperrt_bis timestamp, dauerhaft_gesperrt boolean NOT NULL DEFAULT false,
    gesetzt_am timestamp);
-- Inhaber = Admin-Login von Drazen; aendern nur auf dem Server (tools/superpin_reset.py)
INSERT INTO superpin (user_id) SELECT id FROM users WHERE email = 'admin@seda24.de' ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS monatsabschluss_oeffnung (
    id serial PRIMARY KEY, monat varchar(7) NOT NULL, grund text NOT NULL CHECK (length(btrim(grund)) >= 10),
    geoeffnet_am timestamp NOT NULL DEFAULT now(), geoeffnet_von integer, app_benutzer text,
    db_benutzer text NOT NULL DEFAULT current_user, gesperrt_am timestamp, gesperrt_von integer);
CREATE UNIQUE INDEX IF NOT EXISTS monatsabschluss_oeffnung_offen ON monatsabschluss_oeffnung (monat) WHERE gesperrt_am IS NULL;

CREATE TABLE IF NOT EXISTS monatsabschluss_aenderung (
    id bigserial PRIMARY KEY, oeffnung_id integer NOT NULL REFERENCES monatsabschluss_oeffnung(id), monat varchar(7) NOT NULL,
    tabelle text NOT NULL, aktion text NOT NULL, datensatz_id bigint, alt jsonb, neu jsonb,
    am timestamp NOT NULL DEFAULT clock_timestamp(), app_benutzer text, db_benutzer text NOT NULL DEFAULT current_user,
    vorher_hash text, hash text);
CREATE INDEX IF NOT EXISTS monatsabschluss_aenderung_monat ON monatsabschluss_aenderung (monat, id);

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
DECLARE r record; a date; b date; o record; oids int[] := '{}'; did text;
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
        -- wieder geoeffneter Monat (Super-PIN): Aenderung erlaubt, aber unveraenderbar protokolliert
        IF a IS NOT NULL THEN
            FOR o IN SELECT id FROM monatsabschluss_oeffnung WHERE gesperrt_am IS NULL
                      AND monat BETWEEN to_char(a, 'YYYY-MM') AND to_char(coalesce(b, a), 'YYYY-MM') LOOP
                IF NOT o.id = ANY(oids) THEN oids := oids || o.id; END IF;
            END LOOP;
        END IF;
    END LOOP;
    IF array_length(oids, 1) > 0 THEN
        did := coalesce(to_jsonb(NEW), to_jsonb(OLD))->>'id';
        INSERT INTO monatsabschluss_aenderung (oeffnung_id, monat, tabelle, aktion, datensatz_id, alt, neu, app_benutzer)
        SELECT x.id, x.monat, TG_TABLE_NAME, TG_OP, CASE WHEN did ~ '^[0-9]+$' THEN did::bigint END,
               CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END, CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END,
               nullif(current_setting('seda.app_benutzer', true), '')
          FROM monatsabschluss_oeffnung x WHERE x.id = ANY(oids);
    END IF;
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

-- ---------------------------------------------------------------------------------------------------------------
-- Protokoll: Hash-Kette (jede Zeile enthaelt den Hash der vorigen -> nachtraegliches Aendern faellt auf)
CREATE OR REPLACE FUNCTION monatsabschluss_hash_text(x monatsabschluss_aenderung) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT concat_ws('|', x.vorher_hash, x.id, x.oeffnung_id, x.monat, x.tabelle, x.aktion, x.datensatz_id, x.alt::text,
                     x.neu::text, to_char(x.am, 'YYYY-MM-DD HH24:MI:SS.US'), x.app_benutzer, x.db_benutzer)
$$;

CREATE OR REPLACE FUNCTION monatsabschluss_aenderung_kette() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(4231119);
    SELECT hash INTO NEW.vorher_hash FROM monatsabschluss_aenderung ORDER BY id DESC LIMIT 1;
    NEW.am := clock_timestamp();
    NEW.db_benutzer := current_user;
    NEW.hash := encode(sha256(convert_to(monatsabschluss_hash_text(NEW), 'UTF8')), 'hex');
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION monatsabschluss_kette_pruefen() RETURNS TABLE (zeilen bigint, erste_fehlerhafte bigint)
LANGUAGE sql STABLE AS $$
    WITH k AS (SELECT id, hash, vorher_hash, lag(hash) OVER (ORDER BY id) AS vorige,
                      encode(sha256(convert_to(monatsabschluss_hash_text(a), 'UTF8')), 'hex') AS soll
                 FROM monatsabschluss_aenderung a)
    SELECT count(*), min(id) FILTER (WHERE hash IS DISTINCT FROM soll OR vorher_hash IS DISTINCT FROM vorige) FROM k
$$;

CREATE OR REPLACE FUNCTION monatsabschluss_unveraenderbar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'monatsabschluss_oeffnung' AND TG_OP = 'UPDATE' AND OLD.gesperrt_am IS NULL
       AND NEW.gesperrt_am IS NOT NULL AND (NEW.id, NEW.monat, NEW.grund, NEW.geoeffnet_am, NEW.geoeffnet_von, NEW.app_benutzer,
       NEW.db_benutzer) IS NOT DISTINCT FROM (OLD.id, OLD.monat, OLD.grund, OLD.geoeffnet_am, OLD.geoeffnet_von,
       OLD.app_benutzer, OLD.db_benutzer) THEN
        RETURN NEW;              -- einzig erlaubt: offene Oeffnung einmal schliessen (erneut gesperrt)
    END IF;
    RAISE EXCEPTION 'PROTOKOLL: % ist unveraenderbar (GoBD) – % nicht erlaubt.', TG_TABLE_NAME, TG_OP USING ERRCODE = 'SD423';
END $$;

-- Oeffnen: nur ein abgeschlossener Monat; die Oeffnung selbst steht als erste Zeile im Protokoll
CREATE OR REPLACE FUNCTION monatsabschluss_oeffnung_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NOT EXISTS (SELECT 1 FROM monatsabschluss WHERE monat = NEW.monat AND status = 'abgeschlossen') THEN
            RAISE EXCEPTION 'Der Monat % ist nicht gesperrt – nichts zu öffnen.', NEW.monat USING ERRCODE = 'SD409';
        END IF;
        INSERT INTO monatsabschluss_aenderung (oeffnung_id, monat, tabelle, aktion, neu, app_benutzer)
        VALUES (NEW.id, NEW.monat, 'monatsabschluss', 'GEOEFFNET',
                jsonb_build_object('grund', NEW.grund, 'user_id', NEW.geoeffnet_von), NEW.app_benutzer);
    ELSE
        INSERT INTO monatsabschluss_aenderung (oeffnung_id, monat, tabelle, aktion, neu, app_benutzer)
        VALUES (NEW.id, NEW.monat, 'monatsabschluss', 'GESPERRT', jsonb_build_object('user_id', NEW.gesperrt_von),
                nullif(current_setting('seda.app_benutzer', true), ''));
    END IF;
    RETURN NEW;
END $$;

-- Status-Wechsel des Monats: Entsperren nur mit offener Oeffnung (= mit Protokoll), Sperren schliesst sie
CREATE OR REPLACE FUNCTION monatsabschluss_status_waechter() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status = 'abgeschlossen' OR EXISTS (SELECT 1 FROM monatsabschluss_oeffnung WHERE monat = OLD.monat) THEN
            RAISE EXCEPTION 'Der Monatsabschluss % hat ein Sperr-Protokoll und kann nicht gelöscht werden.', OLD.monat USING ERRCODE = 'SD423';
        END IF;
        RETURN OLD;
    END IF;
    IF NEW.monat <> OLD.monat AND (OLD.status = 'abgeschlossen' OR EXISTS (SELECT 1 FROM monatsabschluss_oeffnung WHERE monat = OLD.monat)) THEN
        RAISE EXCEPTION 'Monat eines gesperrten Abschlusses nicht änderbar.' USING ERRCODE = 'SD423';
    END IF;
    IF OLD.status = 'abgeschlossen' AND NEW.status <> 'abgeschlossen'
       AND NOT EXISTS (SELECT 1 FROM monatsabschluss_oeffnung WHERE monat = NEW.monat AND gesperrt_am IS NULL) THEN
        RAISE EXCEPTION 'MONATSSPERRE: Der Monat %/% kann nur mit Super-PIN und Grund über „Wieder öffnen“ entsperrt werden.',
            substr(NEW.monat, 6, 2), substr(NEW.monat, 1, 4) USING ERRCODE = 'SD423';
    END IF;
    IF NEW.status = 'abgeschlossen' AND OLD.status <> 'abgeschlossen' THEN
        UPDATE monatsabschluss_oeffnung SET gesperrt_am = now(), gesperrt_von = NEW.gesperrt_von
         WHERE monat = NEW.monat AND gesperrt_am IS NULL;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS kette ON monatsabschluss_aenderung;
CREATE TRIGGER kette BEFORE INSERT ON monatsabschluss_aenderung FOR EACH ROW EXECUTE PROCEDURE monatsabschluss_aenderung_kette();
DROP TRIGGER IF EXISTS unveraenderbar ON monatsabschluss_aenderung;
CREATE TRIGGER unveraenderbar BEFORE UPDATE OR DELETE ON monatsabschluss_aenderung FOR EACH ROW EXECUTE PROCEDURE monatsabschluss_unveraenderbar();
DROP TRIGGER IF EXISTS unveraenderbar_t ON monatsabschluss_aenderung;
CREATE TRIGGER unveraenderbar_t BEFORE TRUNCATE ON monatsabschluss_aenderung FOR EACH STATEMENT EXECUTE PROCEDURE monatsabschluss_unveraenderbar();
DROP TRIGGER IF EXISTS unveraenderbar ON monatsabschluss_oeffnung;
CREATE TRIGGER unveraenderbar BEFORE UPDATE OR DELETE ON monatsabschluss_oeffnung FOR EACH ROW EXECUTE PROCEDURE monatsabschluss_unveraenderbar();
DROP TRIGGER IF EXISTS unveraenderbar_t ON monatsabschluss_oeffnung;
CREATE TRIGGER unveraenderbar_t BEFORE TRUNCATE ON monatsabschluss_oeffnung FOR EACH STATEMENT EXECUTE PROCEDURE monatsabschluss_unveraenderbar();
DROP TRIGGER IF EXISTS protokoll ON monatsabschluss_oeffnung;
CREATE TRIGGER protokoll AFTER INSERT OR UPDATE ON monatsabschluss_oeffnung FOR EACH ROW EXECUTE PROCEDURE monatsabschluss_oeffnung_log();
DROP TRIGGER IF EXISTS waechter ON monatsabschluss;
CREATE TRIGGER waechter BEFORE UPDATE OR DELETE ON monatsabschluss FOR EACH ROW EXECUTE PROCEDURE monatsabschluss_status_waechter();

-- Rechte: Protokoll-Tabellen gehoeren postgres, die App darf nur lesen/anfuegen (kein UPDATE/DELETE/TRUNCATE/DISABLE TRIGGER)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'seda24_user') THEN
        ALTER TABLE monatsabschluss_aenderung OWNER TO postgres;
        ALTER TABLE monatsabschluss_oeffnung OWNER TO postgres;
        ALTER TABLE superpin OWNER TO postgres;
        REVOKE ALL ON monatsabschluss_aenderung, monatsabschluss_oeffnung, superpin FROM seda24_user;
        GRANT SELECT, INSERT ON monatsabschluss_aenderung, monatsabschluss_oeffnung TO seda24_user;
        GRANT UPDATE (gesperrt_am, gesperrt_von) ON monatsabschluss_oeffnung TO seda24_user;
        GRANT SELECT, UPDATE (pin_hash, fehlversuche, gesperrt_bis, dauerhaft_gesperrt, gesetzt_am) ON superpin TO seda24_user;
        GRANT USAGE ON SEQUENCE monatsabschluss_aenderung_id_seq, monatsabschluss_oeffnung_id_seq TO seda24_user;
    END IF;
END $$;
