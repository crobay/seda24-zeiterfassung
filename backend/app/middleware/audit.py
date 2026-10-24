"""
Audit-Middleware fuer SEDA24 V3.0
Loggt automatisch alle schreibenden API-Aufrufe.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.database import SessionLocal
from app.models.models import AuditLog

logger = logging.getLogger(__name__)

TRACKED_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}
TRACKED_PATHS = [
    '/api/v1/time-entries/',
    '/api/v1/admin/',
    '/api/v1/push/',
    '/api/v1/confirmations/',
]
# Pfade die NICHT geloggt werden (zu viel Traffic)
EXCLUDED_PATHS = [
    '/api/v1/push/vapid-public-key',
    '/health',
    '/',
]


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        if request.method not in TRACKED_METHODS:
            return response

        path = request.url.path
        if any(path.startswith(exc) for exc in EXCLUDED_PATHS):
            return response

        should_log = any(path.startswith(tp) for tp in TRACKED_PATHS)
        if not should_log:
            return response

        try:
            db = SessionLocal()
            log_entry = AuditLog(
                action=f"{request.method} {path}",
                ip_address=request.client.host if request.client else None,
                user_agent=(request.headers.get('user-agent', '') or '')[:255],
                details=f"Status: {response.status_code}",
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.error(f"Audit-Log Fehler: {e}")
        finally:
            db.close()

        return response
