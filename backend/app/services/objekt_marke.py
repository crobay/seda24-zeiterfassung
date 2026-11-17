"""Objekt-Logo und farbiges Kuerzel (nur interne Anzeige: Cockpit + Stempeluhr).

Ohne Logo: 2 Buchstaben (z. B. LI, GE) auf einer Farbe aus der farbenblind-tauglichen Okabe-Ito-Palette,
automatisch je Objekt, aenderbar. Kuerzel/Logo erscheinen immer zusammen mit dem Objektnamen (nie Farbe allein).
Logos werden im Browser auf max. 160 px verkleinert und als PNG gespeichert (Data-URL in der Datenbank):
nichts wird aus dem Internet geladen, und sie sind in der Stempeluhr ohne Netz verfuegbar (Objekt-Cache).
"""
import base64
import re
import struct

from sqlalchemy import text

# Okabe-Ito (farbenblind-tauglich); Reihenfolge = automatische Vergabe nach Objekt-ID
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#000000", "#F0E442"]
LOGO_MAX_PX = 256
LOGO_MAX_BYTES = 150_000


def tabelle(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS objekt_marken (
        object_id integer PRIMARY KEY REFERENCES objects(id) ON DELETE CASCADE,
        kuerzel varchar(3), farbe varchar(7), logo text, updated_at timestamp DEFAULT now(), updated_by integer)"""))


def kuerzel_auto(name: str) -> str:
    woerter = [w for w in re.split(r"[^0-9A-Za-zÄÖÜäöüß]+", name or "") if w]
    if not woerter:
        return "?"
    erstes = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", woerter[0]) or woerter[0]
    if len(erstes) >= 2:
        return erstes[:2].upper()
    return "".join(w[0] for w in woerter[:2]).upper()


def farbe_auto(object_id: int) -> str:
    return PALETTE[int(object_id) % len(PALETTE)]


def text_farbe(farbe: str) -> str:
    """Schwarz oder Weiss auf der Kuerzel-Farbe, je nach besserem Kontrast."""
    r, g, b = (int(farbe[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#000000" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#FFFFFF"


def marke(object_id: int, name: str, zeile=None) -> dict:
    k = (zeile and zeile.get("kuerzel")) or kuerzel_auto(name)
    f = (zeile and zeile.get("farbe")) or farbe_auto(object_id)
    return {"kuerzel": k, "farbe": f, "text": text_farbe(f), "logo": (zeile and zeile.get("logo")) or None,
            "auto": not (zeile and (zeile.get("kuerzel") or zeile.get("farbe")))}


def marken(db, ids=None) -> dict:
    """{object_id: marke} fuer alle (oder die angegebenen) Objekte."""
    tabelle(db)
    flt, p = ("", {}) if ids is None else ("WHERE o.id = ANY(:ids)", {"ids": list(ids)})
    rows = db.execute(text(f"""SELECT o.id, o.name, m.kuerzel, m.farbe, m.logo FROM objects o
                                LEFT JOIN objekt_marken m ON m.object_id = o.id {flt}"""), p).mappings().all()
    return {r["id"]: marke(r["id"], r["name"], dict(r)) for r in rows}


def pruefe_logo(data_url: str) -> str:
    """Nur kleines PNG als Data-URL (im Browser verkleinert). Gibt die bereinigte Data-URL zurueck."""
    m = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=]+)", (data_url or "").strip())
    if not m:
        raise ValueError("Logo bitte als Bild hochladen (PNG, JPG oder SVG)")
    roh = base64.b64decode(m.group(1), validate=True)
    if len(roh) > LOGO_MAX_BYTES:
        raise ValueError("Logo zu gross")
    if roh[:8] != b"\x89PNG\r\n\x1a\n" or roh[12:16] != b"IHDR":
        raise ValueError("Kein gueltiges PNG")
    w, h = struct.unpack(">II", roh[16:24])
    if not (0 < w <= LOGO_MAX_PX and 0 < h <= LOGO_MAX_PX):
        raise ValueError(f"Logo hoechstens {LOGO_MAX_PX} x {LOGO_MAX_PX} Pixel")
    return "data:image/png;base64," + base64.b64encode(roh).decode()
