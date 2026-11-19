#!/bin/bash
# Etappe 1 Cockpit: DB-Sicherung, dann die 5 neuen Tabellen (backend/migrations/etappe1_cockpit.sql) in EINER
# Transaktion. Bricht bei jedem Fehler ab; die bestehenden Daten werden nicht veraendert.
#   tools/etappe1_migration.sh <datenbank>          (LIVE: seda24_zeiterfassung)
# Rueckweg: siehe Ausgabe (DROP der 5 leeren Tabellen) bzw. Sicherung einspielen.
set -euo pipefail
DB=${1:?Datenbank angeben}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SQL=$ROOT/backend/migrations/etappe1_cockpit.sql
BACKUP_DIR=${BACKUP_DIR:-/var/www/vhosts/seda.de/app.seda.de/backups}
STAMP=$(date +%Y%m%d_%H%M%S)
DUMP=$BACKUP_DIR/vor_etappe1_${DB}_$STAMP.sql.gz

echo "1) Sicherung $DB -> $DUMP"
sudo -n -u postgres pg_dump "$DB" | gzip > "$DUMP"
gzip -t "$DUMP"
[ "$(zcat "$DUMP" | grep -c '^COPY public.time_entries ')" = 1 ] || { echo "Sicherung unvollstaendig - ABBRUCH"; exit 1; }
echo "   ok ($(du -h "$DUMP" | cut -f1))"

echo "2) Tabellen anlegen"
sudo -n -u postgres psql -X -q -v ON_ERROR_STOP=1 -1 -d "$DB" -f "$SQL"
# Eigentuemer wie die uebrigen Tabellen (Backend verbindet als seda24_user)
for t in app_settings monatsabschluss monatsabschluss_dokument monatsabschluss_versand objekt_marken; do
    sudo -n -u postgres psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "ALTER TABLE $t OWNER TO seda24_user"
done
for s in monatsabschluss_dokument_id_seq monatsabschluss_versand_id_seq; do
    sudo -n -u postgres psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "ALTER SEQUENCE $s OWNER TO seda24_user"
done

echo "3) Kontrolle"
sudo -n -u postgres psql -X -At -d "$DB" -c "SELECT tablename || ' (' || tableowner || ')' FROM pg_tables WHERE tablename IN
  ('app_settings','monatsabschluss','monatsabschluss_dokument','monatsabschluss_versand','objekt_marken') ORDER BY 1"
n=$(sudo -n -u postgres psql -X -At -d "$DB" -c "SELECT count(*) FROM pg_tables WHERE tableowner = 'seda24_user' AND tablename IN
  ('app_settings','monatsabschluss','monatsabschluss_dokument','monatsabschluss_versand','objekt_marken')")
[ "$n" = 5 ] || { echo "nur $n von 5 Tabellen - ABBRUCH"; exit 1; }
t=$(sudo -n -u postgres psql -X -At -d "$DB" -c "SELECT count(*) FROM pg_trigger WHERE tgname = 'monatssperre'")
[ "$t" = 0 ] || { echo "WARNUNG: Monatssperre-Trigger vorhanden ($t) - gehoert erst zu Etappe 2"; exit 1; }
echo "MIGRATION OK. Rueckweg: DROP TABLE objekt_marken, monatsabschluss_versand, monatsabschluss_dokument, monatsabschluss, app_settings;"
echo "                 oder: zcat $DUMP | sudo -u postgres psql $DB  (nur in leere DB)"
