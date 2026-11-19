-- Etappe 1 Cockpit auf LIVE (Drazen 19.11.2026): die 5 neuen Tabellen, Schema wie DEV (dev_cockpit).
-- Idempotent (IF NOT EXISTS), aendert keine bestehende Tabelle und keine Daten. KEINE Monatssperre (Trigger kommt
-- erst mit Etappe 2 ueber migrations/monatssperre.sql).
-- Die View current_week_schedule existiert auf LIVE bereits (Eigentuemer postgres) und wird von keinem Code
-- benutzt -> bleibt unveraendert.
-- Einspielen ueber tools/etappe1_migration.sh (macht vorher die DB-Sicherung).

SET client_min_messages = warning;

-- Einstellungen (Branding, Minijob-Grenzen, Lohnart-Nummern, Lohnversand, Plan-fertig-Meldungen)
CREATE TABLE IF NOT EXISTS app_settings (
    key varchar(50) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamp DEFAULT now(),
    updated_by integer);

-- Monatsabschluss (Etappe 2 - Tabellen schon jetzt, Seite/API per Schalter COCKPIT_ABSCHLUSS aus)
CREATE TABLE IF NOT EXISTS monatsabschluss (
    monat varchar(7) PRIMARY KEY,
    status varchar(20) NOT NULL DEFAULT 'offen',
    haken text NOT NULL DEFAULT '{}',
    erzeugt_am timestamp, erzeugt_von integer,
    gesperrt_am timestamp, gesperrt_von integer);

CREATE TABLE IF NOT EXISTS monatsabschluss_dokument (
    id serial PRIMARY KEY,
    monat varchar(7) NOT NULL,
    employee_id integer REFERENCES employees(id),
    art varchar(20) NOT NULL,
    dateiname text NOT NULL,
    pfad text NOT NULL,
    groesse integer,
    sha256 varchar(64),
    zuordnung varchar(20),
    am timestamp DEFAULT now(),
    von integer);

CREATE TABLE IF NOT EXISTS monatsabschluss_versand (
    id serial PRIMARY KEY,
    monat varchar(7) NOT NULL,
    employee_id integer,
    an text, betreff text, anhaenge text,
    status varchar(20) NOT NULL,
    fehler text,
    am timestamp DEFAULT now(),
    von integer);

-- Objekt-Kuerzel/Farbe/Logo (Bearbeiten per Schalter COCKPIT_OBJEKT_LOGO aus)
CREATE TABLE IF NOT EXISTS objekt_marken (
    object_id integer PRIMARY KEY REFERENCES objects(id) ON DELETE CASCADE,
    kuerzel varchar(3),
    farbe varchar(7),
    logo text,
    updated_at timestamp DEFAULT now(),
    updated_by integer);
