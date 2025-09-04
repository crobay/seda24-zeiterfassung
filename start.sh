#!/bin/bash
echo "Starting SEDA24 Zeiterfassung..."

# Backend MIT SSL starten
cd /root/zeiterfassung/backend
source venv/bin/activate
nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 --ssl-keyfile=/root/zeiterfassung/certs/key.pem --ssl-certfile=/root/zeiterfassung/certs/cert.pem > ../backend.log 2>&1 &
echo "Backend gestartet auf HTTPS Port 8001"

# Frontend starten
cd /root/zeiterfassung/frontend
nohup npm run dev -- --host 0.0.0.0 > ../frontend.log 2>&1 &
echo "Frontend gestartet auf HTTPS Port 5173"

echo "Beide Dienste laufen!"
