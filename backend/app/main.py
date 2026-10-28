import logging
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine
from app.models import models
from app.api.v1.endpoints import (
    auth, employees, time_entries, breaks, reports,
    corrections, warnings, quick_booking, hours_management,
    admin, schedule, vacation, km
)
from app.api.v1.endpoints import push, confirmations, messages, self_booking, fest
from app.middleware.audit import AuditMiddleware
from app.services.scheduler import init_scheduler, shutdown_scheduler
from app.services.telegram_bot import start_bot as start_telegram_bot, stop_bot as stop_telegram_bot

import os as _os
_log_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "logs")
_os.makedirs(_log_dir, exist_ok=True)
_file_handler = logging.FileHandler(_os.path.join(_log_dir, "auth.log"))
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO)
logging.getLogger("app.api.v1.endpoints.auth").addHandler(_file_handler)
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SEDA24 Zeiterfassung API",
    version="3.0.0"
)

# Middleware
# AuditMiddleware stillgelegt (2026-10-29): erzeugte nur grobe Zugriffszeilen ohne
# Benutzer und ohne Inhalt. Nachvollziehbarkeit laeuft jetzt ueber explizite log_audit-
# Aufrufe in den Endpunkten (mit user_id aus Token + old/new) und die Protokoll-Ansicht.
# app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bestehende Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(employees.router, prefix="/api/v1/employees", tags=["employees"])
app.include_router(time_entries.router, prefix="/api/v1/time-entries", tags=["time-entries"])
app.include_router(breaks.router, prefix="/api/v1/breaks", tags=["breaks"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["corrections"])
app.include_router(warnings.router, prefix="/api/v1/warnings", tags=["warnings"])
app.include_router(quick_booking.router, prefix="/api/v1/quick-booking", tags=["quick-booking"])
app.include_router(hours_management.router, prefix="/api/v1/hours-management", tags=["hours"])
app.include_router(km.router, prefix="/api/v1/km", tags=["km"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])
app.include_router(vacation.router, prefix="/api/v1/vacation", tags=["vacation"])

# V3.0 Routers
app.include_router(push.router, prefix="/api/v1/push", tags=["push"])
app.include_router(confirmations.router, prefix="/api/v1/confirmations", tags=["confirmations"])
app.include_router(messages.router, prefix="/api/v1/messages", tags=["messages"])
app.include_router(self_booking.router, prefix="/api/v1/self-booking", tags=["self-booking"])
app.include_router(fest.router, prefix="/api/v1/fest", tags=["fest"])


@app.on_event("startup")
async def startup_event():
    """APScheduler beim App-Start initialisieren."""
    try:
        init_scheduler()
        logger.info("V3.0 Scheduler gestartet")
    except Exception as e:
        logger.error(f"Scheduler-Start fehlgeschlagen: {e}")
    try:
        start_telegram_bot()
        logger.info("Telegram-Bot gestartet")
    except Exception as e:
        logger.error(f"Telegram-Bot-Start fehlgeschlagen: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """APScheduler beim App-Stop sauber beenden."""
    shutdown_scheduler()
    stop_telegram_bot()


@app.get("/")
def read_root():
    return {"message": "SEDA24 Zeiterfassung API V3.0 läuft!"}


@app.get("/health")
def health_check():
    from app.services.scheduler import scheduler
    scheduler_running = scheduler.running if scheduler else False
    return {
        "status": "healthy",
        "version": "3.0.0",
        "scheduler": "running" if scheduler_running else "stopped",
    }
