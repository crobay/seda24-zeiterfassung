#!/bin/bash
# Frische Kopie der LIVE-Daten nach DEV (dev_cockpit) - fuer den Monatsabschluss-Durchlauf (Drazen 19.11.2026).
# LIVE wird nur gelesen (pg_dump). Vorher wird dev_cockpit gesichert; DEV-Einstellungen (app_settings: Branding,
# Lohnarten, Lohnversand-Testmodus ...) und Objekt-Kuerzel bleiben erhalten.
# Auf der Kopie wird alles abgeschaltet, was Nachrichten ausloesen koennte (Telegram-Chat-IDs, Push-Abos) -
# DEV hat ausserdem keinen Bot-Token, keinen VAPID-Schluessel und keinen Graph-Zugang.
set -euo pipefail
DEV=/var/www/vhosts/seda.de/dev.seda.de/cockpit
BK=/var/www/vhosts/seda.de/dev.seda.de/backups
STAMP=$(date +%Y%m%d_%H%M%S)
TMP=$(mktemp -d); chmod 755 "$TMP"   # postgres muss die Dateien lesen
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$BK"
PG="sudo -n -u postgres"

echo "1) DEV sichern -> $BK/dev_cockpit_vor_refresh_$STAMP.sql.gz"
$PG pg_dump dev_cockpit | gzip > "$BK/dev_cockpit_vor_refresh_$STAMP.sql.gz"
$PG pg_dump --data-only -t app_settings -t objekt_marken dev_cockpit > "$TMP/dev_settings.sql"; chmod 644 "$TMP/dev_settings.sql"
# Super-PIN (nur Hash) ueber den Refresh behalten, damit Drazen sie nicht neu setzen muss
$PG psql -X -At -d dev_cockpit -c "SELECT CASE WHEN to_regclass('superpin') IS NOT NULL THEN (SELECT coalesce(string_agg(format(
    'UPDATE superpin SET pin_hash = %L, gesetzt_am = %L;', pin_hash, gesetzt_am), ''), '') FROM superpin WHERE pin_hash IS NOT NULL) END" \
    > "$TMP/dev_superpin.sql"; chmod 644 "$TMP/dev_superpin.sql"

echo "2) LIVE lesen (pg_dump seda24_zeiterfassung)"
$PG pg_dump seda24_zeiterfassung > "$TMP/live.sql"; chmod 644 "$TMP/live.sql"
grep -q '^COPY public.time_entries ' "$TMP/live.sql" || { echo "LIVE-Dump unvollstaendig - ABBRUCH (DEV unveraendert)"; exit 1; }

echo "3) DEV-Backend stoppen, dev_cockpit neu aufbauen"
"$DEV/dev_backend.sh" stop || true
$PG psql -X -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'dev_cockpit' AND pid <> pg_backend_pid()" >/dev/null
$PG dropdb dev_cockpit
$PG createdb -O seda24_user dev_cockpit
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$TMP/live.sql" >/dev/null

echo "4) Cockpit-Tabellen + Monatssperre (DEV = Stand Etappe 2)"
BACKUP_DIR="$TMP" "$DEV/tools/etappe1_migration.sh" dev_cockpit | tail -1
$PG psql -X -q -d dev_cockpit -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO seda24_user; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO seda24_user"
# danach: Protokoll-Tabellen gehoeren postgres, App nur lesen/anfuegen (Rechte setzt monatssperre.sql selbst)
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$DEV/backend/migrations/monatssperre.sql"
$PG psql -X -q -d dev_cockpit -c "ALTER FUNCTION monatssperre_check(date,date) OWNER TO seda24_user; ALTER FUNCTION monatssperre_trigger() OWNER TO seda24_user"
# Terminal-Modus (24.11.2026): Tabellen + time_entries.quelle (idempotent, solange LIVE sie noch nicht hat)
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$DEV/backend/migrations/terminal.sql"
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$DEV/backend/migrations/verspaetet.sql" >/dev/null

echo "5) DEV-Einstellungen zurueck, Nachrichtenwege auf der Kopie aus"
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$TMP/dev_settings.sql" >/dev/null
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -f "$TMP/dev_superpin.sql" >/dev/null
$PG psql -X -q -v ON_ERROR_STOP=1 -d dev_cockpit -c "UPDATE employees SET telegram_chat_id = NULL WHERE telegram_chat_id IS NOT NULL;
    UPDATE push_subscriptions SET is_active = false WHERE is_active"

echo "5b) Vorlage (Fixum) Startbestand KW 48 auf DEV"
(cd "$DEV/backend" && ./venv/bin/python ../tools/dev_fixum_startbestand.py | tail -1)

echo "6) Alte DEV-Abschlussdateien beiseite (nicht geloescht)"
if [ -d "$DEV/backend/data/abschluss" ]; then mv "$DEV/backend/data/abschluss" "$DEV/backend/data/abschluss_vor_refresh_$STAMP"; fi

echo "7) DEV-Backend starten"
"$DEV/dev_backend.sh" start
$PG psql -X -At -d dev_cockpit -c "SELECT 'Kontrolle: ' || (SELECT count(*) FROM time_entries) || ' Zeiten, ' || (SELECT count(*) FROM employees WHERE telegram_chat_id IS NOT NULL)
    || ' Chat-IDs, ' || (SELECT count(*) FROM pg_trigger WHERE tgname = 'monatssperre') || ' Sperr-Trigger, Super-PIN-Inhaber ' || (SELECT user_id FROM superpin) || ', letzte Buchung ' || (SELECT max(check_in) FROM time_entries)"
echo "REFRESH OK ($STAMP)"
