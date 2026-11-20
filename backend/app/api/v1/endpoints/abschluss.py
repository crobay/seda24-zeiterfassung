"""Monatsabschluss mit einem Klick (PROTOTYP, nur DEV, nur Admin). Logik in app/services/monatsabschluss.py."""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.endpoints.admin import verify_admin
from app.db.database import get_db
from app.services import monatsabschluss as ma
from app.services.ol_scope import _ist_admin

router = APIRouter()


def nur_admin(user=Depends(verify_admin)):
    """verify_admin laesst auch die Objektleitung durch - Lohnabrechnungen sieht nur der Admin (Drazen)."""
    if not _ist_admin(user):
        raise HTTPException(403, "Nur für Admin")
    return user


def _ym(monat: str):
    try:
        y, m = map(int, monat.split("-"))
        assert 2020 <= y <= 2100 and 1 <= m <= 12
        return y, m
    except Exception:
        raise HTTPException(400, "monat als JJJJ-MM")


def _fehler(f):
    try:
        return f()
    except PermissionError as e:
        raise HTTPException(423, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except KeyError:
        raise HTTPException(404, "Prüfpunkt unbekannt")


def _wer(db, user):
    return db.execute(text("""SELECT coalesce(e.first_name || ' ' || e.last_name, u.email) FROM users u
                              LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = :i"""), {"i": user.id}).scalar()


@router.get("/{monat}")
def uebersicht(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    z = ma.zustand(db, y, m)
    p = ma.pruefliste(db, y, m)
    return {"monat": monat, "status": z["status"], "pruefliste": p, "lohnarten": ma.lohnarten(db),
            "erzeugt_am": z["erzeugt_am"] and z["erzeugt_am"].isoformat(timespec="minutes"), **ma.dokumente(db, y, m),
            "protokoll": ma.protokoll(db, y, m), "lohnablage": _ablage(db, monat), "superpin": _superpin(db, user)}


def _superpin(db, user):
    from app.services import superpin
    return superpin.status(db, user)


def _ablage(db, monat):
    from app.services import lohnablage as la
    e = la.einstellungen(db)
    return {**e, "loeschen_ab": la.loeschdatum(monat, e["aufbewahrung_monate"]).isoformat()}


@router.post("/{monat}/haken")
def haken(monat: str, data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.haken_setzen(db, y, m, str(data.get("key")), bool(data.get("wert", True)), user.id, _wer(db, user)))


@router.post("/{monat}/haken-alle-unauffaellig")
def haken_alle_unauffaellig(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.ma_alle_bestaetigen(db, y, m, user.id, _wer(db, user)))


@router.put("/einstellungen/lohnarten")
def lohnarten(data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    return _fehler(lambda: ma.lohnarten_speichern(db, data, user.id))


@router.get("/{monat}/lexware-vorschau")
def lexware_vorschau(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    z = ma.lexware_zeilen(db, y, m)
    return {"zeilen": [{"personal_nr": p, "name": n, "lohnart": la, "wert": w, "stundensatz": s, "bezeichnung": b} for p, n, la, w, s, b in z],
            "lohnarten": ma.lohnarten(db), "fehlende_lohnarten": ma.fehlende_lohnarten(db, y, m)}


@router.post("/{monat}/erzeugen")
def erzeugen(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.erzeugen(db, y, m, user.id))


@router.get("/{monat}/paket")
def paket(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return Response(ma.paket_zip(db, y, m), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="Monatsabschluss_{monat}_fuer_Lexware.zip"'})


@router.post("/{monat}/lohnabrechnungen")
async def hochladen(monat: str, dateien: List[UploadFile] = File(...), db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    roh = []
    for f in dateien[:300]:
        b = await f.read()
        if len(b) > 60_000_000:
            raise HTTPException(413, f"{f.filename}: zu groß")
        roh.append((f.filename or "datei", b))
    return _fehler(lambda: ma.hochladen(db, y, m, roh, user.id))


@router.put("/{monat}/dokument/{dok_id}")
def zuordnen(monat: str, dok_id: int, data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.dokument_zuordnen(db, y, m, dok_id, int(data["employee_id"]), user.id))


@router.delete("/{monat}/dokument/{dok_id}")
def loeschen(monat: str, dok_id: int, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.dokument_loeschen(db, y, m, dok_id))


@router.get("/{monat}/vorschau")
def vorschau(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return ma.vorschau(db, y, m)


@router.post("/{monat}/versenden")
def versenden(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.versenden(db, y, m, user.id))


@router.post("/{monat}/versenden/{employee_id}")
def erneut_senden(monat: str, employee_id: int, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.erneut_senden(db, y, m, employee_id, user.id))


@router.get("/{monat}/lexware-datei")
def lexware_datei(monat: str, als: str = Query(None), db: Session = Depends(get_db), user=Depends(nur_admin)):
    """Nur die Lexware-Importdatei. als=JJJJ-MM: Werte dieses Monats, aber Jahr/Monat-Spalten fuer einen anderen
    Abrechnungsmonat (Testimport in einer Testfirma, deren offener Monat schon weiter ist)."""
    y, m = _ym(monat)
    b = _fehler(lambda: ma.lexware_datei(db, y, m))
    name = f"Lexware_Lohndaten_{monat}.txt"
    if als:
        y2, m2 = _ym(als)
        alt, neu = f"{y};{m};".encode(), f"{y2};{m2};".encode()
        b = b"\r\n".join(neu + z[len(alt):] if z.startswith(alt) else z for z in b.split(b"\r\n"))
        name = f"Lexware_Lohndaten_{monat}_als_{als}_TEST.txt"
    return Response(b, media_type="text/plain; charset=windows-1252",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{monat}/testversand.zip")
def testversand_zip(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return Response(ma.testversand_zip(y, m), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="Testversand_{monat}.zip"'})


@router.put("/einstellungen/lohnablage")
def lohnablage(data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    from app.services import lohnablage as la
    return _fehler(lambda: la.einstellungen_speichern(db, data, user.id))


@router.put("/einstellungen/microsoft")
def microsoft_zugang(data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    from app.services import lohnversand as lv
    return _fehler(lambda: lv.zugang_speichern(db, data, user.id))


@router.post("/einstellungen/microsoft/test")
def microsoft_test(db: Session = Depends(get_db), user=Depends(nur_admin)):
    from app.services import lohnversand as lv
    return lv.verbindung_testen()


@router.put("/einstellungen/lohnversand")
def lohnversand(data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    from app.services import lohnversand as lv
    return _fehler(lambda: {"einstellungen": lv.einstellungen_speichern(db, data, user.id), "versandweg": lv.status_versand(db)})


@router.post("/{monat}/sperren")
def sperren(monat: str, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.sperren(db, y, m, user.id))


@router.post("/{monat}/wieder-oeffnen")
def wieder_oeffnen(monat: str, data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    y, m = _ym(monat)
    return _fehler(lambda: ma.wieder_oeffnen(db, y, m, user, data.get("grund"), data.get("pin")))


@router.get("/einstellungen/superpin")
def superpin_status(db: Session = Depends(get_db), user=Depends(nur_admin)):
    from app.services import superpin
    return superpin.status(db, user)


@router.put("/einstellungen/superpin")
def superpin_setzen(data: dict, db: Session = Depends(get_db), user=Depends(nur_admin)):
    """Body: pin (neu), passwort (nur beim ersten Mal) oder pin_alt. Antwort ohne Hash."""
    from app.services import superpin
    return _fehler(lambda: superpin.setzen(db, user, data.get("pin"), data.get("passwort"), data.get("pin_alt")))
