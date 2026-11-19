"""
Abruf der Zeiterfassungs-Exporte (scripts/export_zeiterfassung.py) fuer die Buchhaltung.
Abgeholt von Drazens PC (frontend/public/downloads/seda24_export_abruf.ps1).

- Kein Login: eigener Export-Schluessel im Header X-Export-Key, er gilt nur fuer diese Dateien.
  Schluessel liegt in backend/secrets/export_api_key (wird je Anfrage gelesen, Wechsel ohne Neustart).
- Nur ueber HTTPS: /api/v1 wird nur in der SSL-Seite per Apache-Proxy (localhost) weitergereicht,
  http:// leitet auf https:// um. Direkte Verbindungen auf Port 8001 werden abgelehnt: uvicorn
  (proxy_headers) ersetzt den Client nur bei Verbindungen von 127.0.0.1 und setzt dabei Port 0 -
  eine direkte Verbindung hat immer ihren echten Port > 0.
- Jeder Datei-Abruf, jede Fehlermeldung und jeder abgelehnte Versuch steht im Audit-Log.
"""
import hashlib
import hmac
import logging
import os
import re
import time
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import AuditLog
from app.services.export_termine import ABRUF_ZEIT, exporttag, vormonat

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
EXPORT_DIR = os.path.join(BACKEND, 'exports', 'zeiterfassung')
KEY_FILE = os.path.join(BACKEND, 'secrets', 'export_api_key')
FILE_RE = re.compile(r'^(zeiterfassung_\d{4}-(0[1-9]|1[0-2])|objekte_kunden)\.csv$')
LOCAL_PROXY = {'127.0.0.1', '::1'}


def _client_ip(request: Request):
    xff = request.headers.get('x-forwarded-for')
    if xff and xff.split(',')[0].strip():
        return xff.split(',')[0].strip()
    return request.client.host if request.client else None


def _audit(db: Session, request: Request, action: str, details: str):
    db.add(AuditLog(action=action, entity_type='export', details=details,
                    ip_address=(_client_ip(request) or '')[:45],
                    user_agent=(request.headers.get('user-agent', '') or '')[:255]))
    db.commit()


def _check(request: Request, db: Session, what: str):
    via_proxy = request.client and (request.client.port == 0 or request.client.host in LOCAL_PROXY)
    if not via_proxy:
        _audit(db, request, 'export_abruf_abgelehnt', f'{what}: nicht ueber HTTPS-Proxy')
        raise HTTPException(status_code=403, detail='Nur ueber HTTPS')
    try:
        with open(KEY_FILE) as f:
            key = f.read().strip()
    except OSError:
        logger.error('Export-Schluessel fehlt: %s', KEY_FILE)
        raise HTTPException(status_code=503, detail='Export nicht eingerichtet')
    given = request.headers.get('x-export-key', '')
    if not key or not hmac.compare_digest(given.encode(), key.encode()):
        _audit(db, request, 'export_abruf_abgelehnt', f'{what}: falscher oder fehlender Schluessel')
        time.sleep(1)
        raise HTTPException(status_code=403, detail='Kein Zugriff')


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


@router.get('/zeiterfassung')
def list_files(request: Request, db: Session = Depends(get_db)):
    """Verfuegbare Dateien mit Groesse, Stand und SHA-256 (die Liste selbst wird nicht protokolliert).
    vormonat/abruf_ab: das Windows-Skript holt die Vormonatsdatei erst ab 15:00 am Exporttag."""
    _check(request, db, 'Liste')
    logger.info('Export-Liste abgefragt von %s (%s)', _client_ip(request), request.headers.get('user-agent', '')[:80])
    files = []
    for name in sorted(os.listdir(EXPORT_DIR)) if os.path.isdir(EXPORT_DIR) else []:
        if FILE_RE.match(name):
            p = os.path.join(EXPORT_DIR, name)
            files.append({'name': name, 'size': os.path.getsize(p), 'sha256': _sha256(p),
                          'modified': datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec='seconds')})
    vm = vormonat()
    return {'files': files, 'vormonat': vm,
            'abruf_ab': datetime.combine(exporttag(vm), ABRUF_ZEIT).isoformat(timespec='seconds')}


@router.get('/zeiterfassung/{name}')
def download(name: str, request: Request, db: Session = Depends(get_db)):
    _check(request, db, name[:60])
    path = os.path.join(EXPORT_DIR, name)
    if not FILE_RE.match(name) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='Datei nicht vorhanden')
    _audit(db, request, 'export_abruf', f'Export {name} abgerufen ({os.path.getsize(path)} Bytes)')
    return FileResponse(path, media_type='text/csv; charset=utf-8', filename=name)


@router.post('/zeiterfassung/quittung')
def confirm(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Bestaetigung des Windows-Skripts: diese Dateien liegen jetzt in Q: (Name + SHA-256 der Kopie)."""
    _check(request, db, 'Quittung')
    pc = str(payload.get('rechner', 'PC'))[:40]
    items = []
    for f in (payload.get('dateien') or [])[:50]:
        name = str((f or {}).get('name', ''))
        if FILE_RE.match(name):
            sha = str(f.get('sha256', '')).lower()[:64]
            path = os.path.join(EXPORT_DIR, name)
            same = os.path.isfile(path) and sha == _sha256(path)
            items.append(f"{name} ({sha[:12]}{'' if same else ', WEICHT VOM SERVER AB'})")
    _audit(db, request, 'export_quittung', f"In Q: aktualisiert ({pc}): " + (', '.join(items) or 'keine Dateien'))
    return {'ok': True}


@router.post('/zeiterfassung/fehler')
def report_error(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Fehlermeldung des Windows-Skripts -> Telegram (Meldungsart Sonstiges)."""
    _check(request, db, 'Fehlermeldung')
    msg = str(payload.get('text', ''))[:500] or 'ohne Text'
    pc = str(payload.get('rechner', 'PC'))[:40]
    _audit(db, request, 'export_fehler', f'Fehler beim Abruf nach Q: ({pc}): {msg}')
    from app.services.telegram_bot import notify_admin
    notify_admin(f"⚠️ Zeiterfassungs-Export nach Q: fehlgeschlagen ({pc}): {msg}", category='sonstiges')
    return {'ok': True}


# ------------------------------------------------------------------ Lohnabrechnungen vom PC (Drazen 19.11.2026)
# Das PC-Skript seda24_lohn_upload.ps1 (gleicher Export-Schluessel, gleiche Aufgabenplanung auf SEDA2026) laedt neue
# Lohnabrechnung_*.pdf aus dem Lexware-Ausgabeordner hoch. Rohdaten als Body (application/pdf), Dateiname und
# SHA-256 im Header. Der Server prueft die Pruefsumme, speichert verschluesselt (services/lohnablage.py), ordnet nach
# PersNr/Name zu und gibt eine Quittung zurueck. Nur mit Schalter COCKPIT_ABSCHLUSS (Monatsabschluss im Cockpit).
MONAT_RE = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')
MAX_PDF = 10_000_000


def _monat_ok(monat: str):
    from app.services import features
    if not features.an('ABSCHLUSS'):
        raise HTTPException(status_code=404, detail='Monatsabschluss auf diesem Server nicht freigeschaltet')
    mm = MONAT_RE.match(monat or '')
    if not mm:
        raise HTTPException(status_code=400, detail='Monat als JJJJ-MM')
    y, m = int(mm.group(1)), int(mm.group(2))
    heute = datetime.now()
    alter = (heute.year - y) * 12 + heute.month - m
    if not 0 <= alter <= 2:
        raise HTTPException(status_code=400, detail='Nur aktueller Monat und die zwei Vormonate')
    return y, m


@router.get('/lohnabrechnungen/{monat}')
def lohn_stand(monat: str, request: Request, db: Session = Depends(get_db)):
    """Fuer das PC-Skript: welche Pruefsummen hat der Server schon, wie viele Lohnabrechnungen fehlen noch."""
    _check(request, db, f'Lohnabrechnungen {monat[:7]}')
    y, m = _monat_ok(monat)
    from app.services import monatsabschluss as ma
    ma.tabellen(db)
    shas = [r[0] for r in db.execute(text("""SELECT DISTINCT sha256 FROM monatsabschluss_dokument WHERE monat = :k
                                              AND art = 'lohnabrechnung'"""), {'k': monat}).fetchall()]
    st = ma.lohnabrechnungen_stand(db, y, m)
    return {'monat': monat, 'sha256': shas, 'erwartet': st['erwartet'], 'da': st['da'],
            'nicht_zugeordnet': st['nicht_zugeordnet'], 'gesperrt': ma.zustand(db, y, m)['status'] == 'abgeschlossen'}


@router.post('/lohnabrechnungen/{monat}')
async def lohn_upload(monat: str, request: Request, db: Session = Depends(get_db)):
    _check(request, db, f'Lohnabrechnung-Upload {monat[:7]}')
    y, m = _monat_ok(monat)
    from urllib.parse import unquote
    name = os.path.basename(unquote(request.headers.get('x-dateiname', '')))[:150]
    soll = request.headers.get('x-sha256', '').lower().strip()
    pc = request.headers.get('x-rechner', 'PC')[:40]
    if not re.fullmatch(r'[^/\\]+\.pdf', name, re.I) or not re.fullmatch(r'[0-9a-f]{64}', soll):
        raise HTTPException(status_code=400, detail='Header X-Dateiname (.pdf) und X-SHA256 noetig')
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_PDF:
            raise HTTPException(status_code=413, detail='Datei zu gross (max. 10 MB)')
    ist = hashlib.sha256(body).hexdigest()
    if ist != soll:
        _audit(db, request, 'lohnabrechnung_upload_fehler', f'{name} ({pc}): Pruefsumme stimmt nicht')
        raise HTTPException(status_code=422, detail='Pruefsumme stimmt nicht - bitte erneut senden')
    from app.services import monatsabschluss as ma
    ma.tabellen(db)
    try:
        q = ma.lohnabrechnungen_aufnehmen(db, y, m, [(name, body)], None, quelle=f'PC {pc}')[0]
    except PermissionError as e:
        _audit(db, request, 'lohnabrechnung_upload_fehler', f'{name} ({pc}): {e}')
        raise HTTPException(status_code=409, detail=str(e))
    zu = ', '.join(f"{t.get('name') or 'nicht zugeordnet'}" for t in q['teile']) or '-'
    _audit(db, request, 'lohnabrechnung_upload', f"Lohnabrechnung {monat} vom PC {pc}: {name} ({ist[:12]}, {q['status']}) -> {zu}")
    st = ma.lohnabrechnungen_stand(db, y, m)
    return {'quittung': q, 'stand': {'erwartet': st['erwartet'], 'da': st['da'], 'nicht_zugeordnet': st['nicht_zugeordnet']}}
