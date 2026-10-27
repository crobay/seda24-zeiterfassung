#!/bin/bash
# Startet das Zeiterfassung-Backend ueber systemd neu.
# Kein pkill/nohup mehr - der Dienst laeuft als systemd-Unit zeiterfassung-backend.
# HTTPS/SSL (Plesk/nginx) wird NICHT angefasst.
# Hinweis: ggf. mit sudo ausfuehren (systemctl braucht Root-Rechte).

SERVICE=zeiterfassung-backend

echo "Starte $SERVICE neu (systemd)..."
systemctl restart "$SERVICE"
rc=$?
if [ $rc -ne 0 ]; then
    echo "FEHLER: 'systemctl restart $SERVICE' lieferte Exit-Code $rc (Rechte? bitte mit sudo ausfuehren)."
fi

sleep 3

if systemctl is-active --quiet "$SERVICE"; then
    echo "OK: $SERVICE ist sauber oben (active)."
    systemctl --no-pager -n 3 status "$SERVICE" | sed -n '1,3p'
    exit 0
else
    echo "FEHLER: $SERVICE ist NICHT aktiv!"
    systemctl --no-pager -n 15 status "$SERVICE"
    exit 1
fi
