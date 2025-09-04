#!/bin/bash

# Backend stoppen
pkill -f "uvicorn app.main:app"
echo "Backend gestoppt"

# Frontend stoppen
pkill -f "npm run dev"
pkill -f "vite"
echo "Frontend gestoppt"

# Status zeigen
ps aux | grep -E "uvicorn|vite" | grep -v grep
echo "Alle Dienste gestoppt"
