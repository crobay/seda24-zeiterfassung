from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine
from app.models import models
from app.api.v1.endpoints import auth, time_entries, breaks, reports, corrections, warnings, quick_booking, admin
from app.api.v1.endpoints import employees, time_entries
from app.api.v1.endpoints import auth, admin, employees, customers, time_entries, corrections, hours_management

# from app.api.v1.endpoints import employees

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SEDA24 Zeiterfassung API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(employees.router, prefix="/api/v1/employees", tags=["employees"])
app.include_router(time_entries.router, prefix="/api/v1/time-entries", tags=["time-entries"])
app.include_router(breaks.router, prefix="/api/v1/breaks", tags=["breaks"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["corrections"])
app.include_router(warnings.router, prefix="/api/v1/warnings", tags=["warnings"])
app.include_router(quick_booking.router, prefix="/api/v1/quick-booking", tags=["quick-booking"])
app.include_router(hours_management.router, prefix="/api/v1/hours-management", tags=["hours"])

@app.get("/")
def read_root():
    return {"message": "SEDA24 Zeiterfassung API läuft!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
