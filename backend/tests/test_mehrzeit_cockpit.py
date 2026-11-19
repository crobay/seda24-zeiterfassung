"""Cockpit: Zaehler "Mehrzeit-Antraege diese Woche" + Einstellung "Frage ab ... Min" (nur DEV/Cockpit)."""
from datetime import datetime, timedelta

from tests.test_stempel_toleranz import db, client, telegram, ma, schicht, stempeln, TAG  # noqa: F401

URL = "/api/v1/time-entries/{}/mehrzeit-antrag"


def test_cockpit_zaehler_diese_woche(client, db, telegram):
    import os
    from jose import jwt
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:30")
    assert client.post(URL.format(r["id"]), headers=h, json={"grund": "Kundenraum nach Besprechung gereinigt"}).status_code == 200
    tk = jwt.encode({"sub": "admin@seda24.de", "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    ad = {"Authorization": f"Bearer {tk}"}
    ls = client.get("/api/v1/cockpit/leitstelle", headers=ad).json()["mehrzeit"]
    montag = datetime.now().date() - timedelta(days=datetime.now().weekday())
    if TAG >= montag:  # Testtag (gestern) liegt in dieser Woche
        p = [x for x in ls["personen"] if x["employee_id"] == eid][0]
        assert p["anzahl"] >= 1 and p["offen"] >= 1
    assert ls["frage_ab_min"] == 15
    assert client.put("/api/v1/cockpit/einstellungen/mehrzeit", headers=ad, json={"frage_ab_min": 20}).json() == {"frage_ab_min": 20}
    assert client.put("/api/v1/cockpit/einstellungen/mehrzeit", headers=ad, json={"frage_ab_min": 200}).status_code == 400
    assert client.put("/api/v1/cockpit/einstellungen/mehrzeit", headers=h, json={"frage_ab_min": 20}).status_code in (401, 403)
