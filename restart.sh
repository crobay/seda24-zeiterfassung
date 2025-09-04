#!/bin/bash
echo "Stoppe ALLE Services..."
pkill -9 -f uvicorn
pkill -9 -f "npm run dev"
sleep 3

echo "Starte Backend auf Port 8001..."
cd /root/zeiterfassung/backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 --ssl-keyfile /root/zeiterfassung/backend/ssl/key.pem --ssl-certfile /root/zeiterfassung/backend/ssl/cert.pem > ../backend.log 2>&1 &

echo "Starte Frontend..."
cd /root/zeiterfassung/frontend
nohup npm run dev -- --host 0.0.0.0 > ../frontend.log 2>&1 &

sleep 2
echo "Services laufen. Backend: 8001, Frontend: 5173"
