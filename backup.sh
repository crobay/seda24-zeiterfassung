#!/bin/bash
# Backup Script für SEDA24 Zeiterfassung

BACKUP_DIR="/var/www/vhosts/seda.de/app.seda.de/backups"
DATE=$(date +%Y%m%d_%H%M)
KEEP_DAYS=7

# Backup-Verzeichnis erstellen falls nicht vorhanden
mkdir -p $BACKUP_DIR

# Datenbank-Backup
sudo -u postgres pg_dump seda24_zeiterfassung | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Nur wichtige Dateien backuppen (ohne node_modules, venv)
tar -czf $BACKUP_DIR/files_$DATE.tar.gz \
  --exclude='node_modules' \
  --exclude='venv' \
  --exclude='*.log' \
  /var/www/vhosts/seda.de/app.seda.de/zeiterfassung/

# Alte Backups löschen (älter als 7 Tage)
find $BACKUP_DIR -name "*.gz" -mtime +$KEEP_DAYS -delete

echo "Backup erstellt: $DATE"
