#!/bin/bash
# Deploy Frontend + Pruefung. Bricht mit Fehlermeldung ab, wenn Build oder eine Pruefung fehlschlaegt.
#  1. Build (vite) nach frontend/dist
#  2. CACHE_NAME + PRECACHE-Liste (alle JS/CSS-Bundles) in dist/service-worker.js schreiben
#  3. Pruefung VOR dem Kopieren (Precache, Nachtrag, Stempeln, Token - Trockentest mit Rollback)
#  4. Kopieren nach httpdocs (vorher Sicherung)
#  5. Pruefung NACH dem Kopieren (Precache in httpdocs); bei Fehler alte Version zurueck
set -e
set -o pipefail
export PYTHONDONTWRITEBYTECODE=1

APP=/var/www/vhosts/seda.de/app.seda.de
ROOT=$APP/zeiterfassung
WEB=$APP/httpdocs
DIST=$ROOT/frontend/dist
PY=$ROOT/backend/venv/bin/python
CHECK=$ROOT/backend/scripts/post_deploy_check.py

fail() { echo ""; echo "DEPLOY ABGEBROCHEN: $1"; exit 1; }

echo "Starting deployment..."
cd $ROOT/frontend
npm run build || fail "Build fehlgeschlagen"

TIMESTAMP=$(date +%s)
sed -i "s/\.js\"/\.js?v=$TIMESTAMP\"/" $DIST/index.html

# Precache-Liste: alle Dateien in dist/assets (gehashte Bundles dieses Builds)
PRECACHE=$(cd $DIST && find assets -type f | sort | sed "s|^|'/|; s|\$|'|" | paste -sd, -)
[ -n "$PRECACHE" ] || fail "keine Bundle-Dateien in $DIST/assets"
sed -i "s/^const CACHE_NAME = .*/const CACHE_NAME = 'seda24-cache-v$TIMESTAMP';/" $DIST/service-worker.js
sed -i "s|^const PRECACHE = .*|const PRECACHE = [$PRECACHE];|" $DIST/service-worker.js
echo "Precache: $PRECACHE"

echo ""
echo "Pruefung vor dem Kopieren (dist):"
$PY $CHECK --webroot $DIST || fail "Pruefung fehlgeschlagen - httpdocs NICHT veraendert"

# Sicherung der laufenden Version
BACKUP=$(mktemp -d /tmp/seda24-deploy-backup.XXXXXX)
cp -a $WEB/index.html $WEB/service-worker.js $BACKUP/ 2>/dev/null || true
[ -d $WEB/assets ] && cp -a $WEB/assets $BACKUP/assets

restore() {
    echo "Stelle vorherige Version wieder her..."
    rm -rf $WEB/assets
    [ -d $BACKUP/assets ] && cp -a $BACKUP/assets $WEB/assets
    cp -a $BACKUP/index.html $BACKUP/service-worker.js $WEB/ 2>/dev/null || true
    chown -R seda24dev:psacln $WEB/
}

rm -rf $WEB/assets
cp -r $DIST/* $WEB/ || { restore; fail "Kopieren fehlgeschlagen - vorherige Version wiederhergestellt"; }
chown -R seda24dev:psacln $WEB/

echo ""
echo "Pruefung nach dem Kopieren (httpdocs):"
if ! $PY $CHECK --webroot $WEB --static-only; then
    restore
    fail "Pruefung in httpdocs fehlgeschlagen - vorherige Version wiederhergestellt"
fi
rm -rf $BACKUP

# Hinweis, falls das laufende Backend aelter ist als der Code (restart.sh noetig)
STARTED=$(date -d "$(systemctl show -p ActiveEnterTimestamp --value zeiterfassung-backend)" +%s 2>/dev/null || echo 0)
NEWEST=$(find $ROOT/backend/app -name '*.py' -printf '%T@\n' | sort -n | tail -1 | cut -d. -f1)
if [ "$STARTED" -lt "${NEWEST:-0}" ]; then
    echo ""
    echo "HINWEIS: Backend-Code ist neuer als der laufende Dienst -> restart.sh noetig (nur wenn niemand eingestempelt ist)."
fi

echo ""
echo "Deploy complete with cache-buster: $TIMESTAMP"
echo "PWA/Offline: Bundles im Precache, alle Pruefungen OK."
