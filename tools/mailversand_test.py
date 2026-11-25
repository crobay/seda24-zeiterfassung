"""NUR DEV: Cockpit › Einstellungen › E-Mail-Versand (Microsoft 365) (Drazen 25.11.2026). Schickt keine Mail und ruft
Microsoft nicht an (kein Verbindungstest). Stellt lohnmail_graph.json + Material-Absender danach wieder her.
Aufruf aus backend/: venv/bin/python ../tools/mailversand_test.py"""
import json, os, subprocess, sys, urllib.request
sys.path.insert(0, os.getcwd())
API = "http://127.0.0.1:8003/api/v1/cockpit"
tok = lambda m: subprocess.run([sys.executable, "../tools/dev_token.py", m], capture_output=True, text=True).stdout.split()[-1]
def sql(q):
    return subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "dev_cockpit", "-X", "-tA", "-c", q], capture_output=True, text=True, cwd="/tmp").stdout.strip()
ADMIN = tok("admin@seda24.de")
OL = tok(sql("SELECT email FROM users WHERE lower(role::text) IN ('objektleiter','objektleitung') AND is_active LIMIT 1"))
def call(m, p, body=None, t=ADMIN):
    r = urllib.request.Request(API + p, method=m, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")
ok = bad = 0
def chk(name, cond, info=""):
    global ok, bad
    print(f"  [{'OK ' if cond else 'XX '}] {name}{' - ' + str(info) if info else ''}"); ok += bool(cond); bad += not cond
from app.services import lohnversand as lv
F = lv.SECRET_FILE
alt = open(F).read() if os.path.exists(F) else None
alt_mat = sql("SELECT value FROM app_settings WHERE key='materialmail'")
START_A = int(sql("SELECT coalesce(max(id),0) FROM audit_log"))
T, C = "49ade56b-d15a-4fdf-a72e-a03c13331855", "6d6bf952-dd2e-4588-91f5-4e5928c1ef04"
try:
    s, d = call("GET", "/abschluss/einstellungen/mailversand")
    chk("Admin: Mandant + Client vorbelegt", s == 200 and d["zugang"]["tenant"] == T and d["zugang"]["client_id"] == C)
    chk("Geheimnis nicht gesetzt, nie im Klartext", d["zugang"]["secret_gesetzt"] is False and "secret" not in d["zugang"])
    chk("noch nicht eingerichtet (kein Graph)", d["status"]["konfiguriert"] is False, d["status"]["weg_test"])
    ab = {a["adresse"]: a for a in d["absender"]}
    chk("Absender Lohn lohn@seda.de, Testmodus", ab.get("lohn@seda.de", {}).get("testmodus") is True, list(ab))
    chk("Absender Material material@seda24.de 'SEDA24 Objektbetreuung', Testmodus",
        ab.get("material@seda24.de", {}).get("name") == "SEDA24 Objektbetreuung" and ab["material@seda24.de"]["testmodus"] is True)
    s, d = call("GET", "/abschluss/einstellungen/mailversand", t=OL)
    chk("Objektleitung: kein Zugriff (403)", s == 403, s)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": T, "client_id": C, "secret": "x"}, t=OL)
    chk("Objektleitung: speichern verboten (403)", s == 403, s)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": T, "client_id": C, "secret": ""})
    chk("ohne Geheimnis speichern -> 409 'fehlt'", s == 409 and "fehlt" in str(d), d)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": T, "client_id": C, "secret": "kurz"})
    chk("zu kurzes Geheimnis -> 409", s == 409, d)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": T, "client_id": C, "secret": "12345678-1234-1234-1234-123456789abc"})
    chk("Geheimnis-ID (GUID) statt Wert -> 409", s == 409, d)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": "abc", "client_id": C, "secret": "y" * 30})
    chk("Mandant keine GUID -> 409", s == 409, d)

    print("Geheimnis bleibt, wenn das Feld leer bleibt (ohne Microsoft-Aufruf)")
    with open(F) as f:
        x = json.load(f)
    x["secret"] = "TEST-NICHT-ECHT-" + "z" * 24
    with open(F, "w") as f:
        json.dump(x, f)
    s, d = call("PUT", "/abschluss/einstellungen/microsoft", {"tenant": T, "client_id": C, "secret": ""})
    with open(F) as f:
        y = json.load(f)
    chk("leer gespeichert -> altes Geheimnis bleibt", s == 200 and y["secret"] == x["secret"] and y["tenant"] == T, d if s != 200 else "")
    chk("Protokoll ohne Werte", sql(f"SELECT count(*) FROM audit_log WHERE id>{START_A} AND action='lohnversand_zugang' AND details LIKE '%Geheimnis gespeichert%' AND details NOT LIKE '%TEST-NICHT%' AND details NOT LIKE '%{T}%'") == "1")
    s, d = call("GET", "/abschluss/einstellungen/mailversand")
    chk("Status: eingerichtet, Geheimnis gesetzt", d["status"]["konfiguriert"] is True and d["zugang"]["secret_gesetzt"] is True and "TEST-NICHT" not in json.dumps(d))

    print("Material-Absender")
    s, d = call("PUT", "/material/mail-einstellungen", {"absender": "x@gmail.com"})
    chk("fremde Domain abgelehnt", s == 400, d)
    s, d = call("PUT", "/material/mail-einstellungen", {"absender": "lohn@seda.de"})
    chk("lohn@ fuer Material abgelehnt", s == 400, d)
finally:
    if alt is None:
        os.path.exists(F) and os.remove(F)
    else:
        with open(F, "w") as f:
            f.write(alt)
        os.chmod(F, 0o600)
    sql(f"UPDATE app_settings SET value = $${alt_mat}$$ WHERE key='materialmail'")
    sql(f"DELETE FROM audit_log WHERE id>{START_A} AND action IN ('lohnversand_zugang','materialmail_einstellung')")
    print("  wiederhergestellt: Zugangsdatei + Material-Absender")
print(f"== {ok} OK, {bad} FAIL"); sys.exit(1 if bad else 0)
