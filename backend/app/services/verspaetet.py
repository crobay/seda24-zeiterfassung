"""Verspaetet uebertragene Stempel (Drazen 24.11.2026): Eingang am Server > 5 Min nach der Handy-Zeit (offline nachgereicht).

Grundlage: time_entries.kommen_handy/kommen_eingang und gehen_handy/gehen_eingang (migrations/verspaetet.sql).
Sauber gestempelte (auch Terminal) haben Eingang = Handy-Zeit und bekommen keinen Hinweis.
"""
GRENZE_MIN = 5


def _dauer(minuten):
    h, m = divmod(minuten, 60)
    return f"{h}:{m:02d} h" if h else f"{m} Min"


def _zeit(t, bezug):
    return t.strftime("%H:%M") if t.date() == bezug.date() else t.strftime("%d.%m. %H:%M")


def stempel(art, handy, eingang):
    """{art, minuten, handy, server, text} oder None (nicht verspaetet / unbekannt)."""
    if not handy or not eingang:
        return None
    minuten = int((eingang - handy).total_seconds() // 60)
    if minuten <= GRENZE_MIN:
        return None
    return {"art": art, "minuten": minuten, "handy": handy.strftime("%H:%M"), "server": _zeit(eingang, handy),
            "text": f"📶 {_dauer(minuten)} verspätet übertragen (Handy {handy:%H:%M}, Server {_zeit(eingang, handy)})"}


def hinweise(r):
    """Liste fuer eine Zeile mit den vier Spalten (dict oder ORM-Objekt)."""
    g = r.get if isinstance(r, dict) else (lambda k: getattr(r, k, None))
    return [x for x in (stempel("kommen", g("kommen_handy"), g("kommen_eingang")),
                        stempel("gehen", g("gehen_handy"), g("gehen_eingang"))) if x]
