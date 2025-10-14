#!/bin/bash
echo "Stoppe ALLE Services..."
pkill -9 -f uvicorn
pkill -9 -f "npm run dev"

sleep 2

echo "Starte Backend auf Port 8001..."
cd /var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > backend.log 2>&1 &

echo "Starte Frontend..."
cd /var/www/vhosts/seda.de/app.seda.de/zeiterfassung/frontend
nohup npm run dev > frontend.log 2>&1 &

sleep 3
echo "Services laufen. Backend: 8001, Frontend: 5173"
netstat -tlpn | grep -E "8001|5173"
