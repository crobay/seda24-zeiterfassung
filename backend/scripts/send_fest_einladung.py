#!/usr/bin/env python3
"""
SEDA24 Sommerfest - Einladungs-Mailer

Testmodus (Standard):
  python3 send_fest_einladung.py
  -> Sendet NUR 1 Test-Mail an mail.sertic@gmail.com

Echtversand:
  python3 send_fest_einladung.py --live
  -> Sendet an alle aktiven MAs (ausser D0001, D0002, D0032)
"""

import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === SMTP-KONFIGURATION ===
SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = "dsertic@seda.de"
SMTP_PASSWORD = "Miroso46761:"
FROM_NAME = "Drazen Sertic"
FROM_EMAIL = "dsertic@seda.de"

# === DATENBANK ===
import psycopg2
DB_HOST = "localhost"
DB_NAME = "seda24_zeiterfassung"
DB_USER = "seda24_user"
DB_PASS = "SedaDev2025"

# === AUSSCHLUSS-LISTE ===
EXCLUDE = {'A0001'}

# D0001 bekommt Mail an Gmail statt an dsertic@sertic.de (gleicher SMTP)
EMAIL_OVERRIDES = {'D0001': 'mail.sertic@gmail.com'}

BASE_URL = "https://app.seda.de/fest"

# Test-Empfaenger
TEST_EMAIL = "mail.sertic@gmail.com"
TEST_NAME = "Ljubica"
TEST_PNR = "D0004"


def get_employees():
    """Alle aktiven MAs mit Email laden (ausser Ausschluss-Liste)."""
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    cur.execute("""
        SELECT e.personal_nr, e.first_name, e.last_name, u.email
        FROM employees e
        JOIN users u ON u.id = e.user_id
        WHERE e.is_active = true AND e.personal_nr NOT LIKE 'A%%'
        ORDER BY e.personal_nr
    """)
    rows = cur.fetchall()
    conn.close()
    return [(r[0], r[1], r[2], r[3]) for r in rows if r[0] not in EXCLUDE]


def build_html(first_name, personal_nr):
    link = f"{BASE_URL}?id={personal_nr}"
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>
<body style="margin:0; padding:0; background:#fffbeb; font-family:Arial,sans-serif;">
<div style="max-width:560px; margin:20px auto; background:white; border-radius:16px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">

  <div style="background:linear-gradient(135deg,#fbbf24,#d97706); padding:36px 30px; text-align:center; color:white;">
    <p style="font-size:52px; margin:0;">&#9728;&#65039;&#127866;&#127807;</p>
    <h1 style="margin:10px 0 0; font-size:24px; letter-spacing:0.5px;">SEDA24 Sommerfest 2026</h1>
  </div>

  <div style="padding:32px 28px;">
    <p style="color:#374151; font-size:15px; line-height:1.8; margin:0 0 16px 0;">
      Hallo <strong>{first_name}</strong>,
    </p>
    <p style="color:#374151; font-size:15px; line-height:1.8; margin:0 0 16px 0;">
      es ist wieder so weit &ndash; wir schmeißen ein Sommerfest, und du gehörst dazu!
    </p>
    <p style="color:#374151; font-size:15px; line-height:1.8; margin:0 0 16px 0;">
      Nach dem tollen Fest vor zwei Jahren wird es Zeit, dass wir alle mal wieder zusammenkommen.
      Der Garten der Firmenzentrale wird zur Festwiese: der Grill läuft heiß, es gibt frische
      Salate, kühle Getränke und vor allem gute Gesellschaft. Wir haben in letzter Zeit ein paar
      neue Gesichter im Team &ndash; das ist die perfekte Gelegenheit, sich in entspannter Runde
      kennenzulernen.
    </p>
    <p style="color:#374151; font-size:15px; line-height:1.8; margin:0 0 16px 0;">
      Bring gerne deinen Partner oder deine Partnerin mit &ndash; je mehr, desto schöner.
    </p>
    <p style="color:#374151; font-size:15px; line-height:1.8; margin:0 0 24px 0;">
      Damit wir planen können, sag uns kurz Bescheid, welcher Samstag dir passt. Es geht am
      späten Nachmittag los, so ab 17 bis 18 Uhr (je nach Wetter), und dann sitzen wir zusammen,
      solange es schön ist &ndash; open end.
    </p>

    <div style="text-align:center; margin:28px 0;">
      <a href="{link}"
         style="display:inline-block; padding:16px 40px; background:linear-gradient(135deg,#f59e0b,#d97706);
                color:white; text-decoration:none; border-radius:14px; font-size:17px; font-weight:bold;
                box-shadow:0 4px 15px rgba(245,158,11,0.4); letter-spacing:0.3px;">
        Jetzt kurz antworten
      </a>
    </div>

    <p style="color:#374151; font-size:15px; line-height:1.8; margin:24px 0 8px 0; text-align:center;">
      Wir freuen uns riesig auf dich!
    </p>
    <p style="color:#374151; font-size:15px; line-height:1.6; margin:0; text-align:center;">
      Liebe Grüße<br>
      <strong>Drazen</strong>
    </p>

    <p style="color:#b0b0b0; font-size:12px; text-align:center; margin-top:28px;">
      Oder öffne diesen Link direkt:<br>
      <a href="{link}" style="color:#d97706;">{link}</a>
    </p>
  </div>

  <div style="background:#f9fafb; padding:16px; text-align:center; border-top:1px solid #e5e7eb;">
    <p style="color:#9ca3af; font-size:11px; margin:0;">
      SEDA24 GmbH &middot; Sommerfest 2026
    </p>
  </div>

</div>
</body>
</html>
"""


def send_email(to_email, to_name, personal_nr):
    """Eine Einladungs-Mail versenden."""
    msg = MIMEMultipart('alternative')
    msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg['To'] = to_email
    msg['Subject'] = "Unser SEDA24 Sommerfest – du bist eingeladen!"

    first_name = to_name.split()[0] if ' ' in to_name else to_name
    html = build_html(first_name, personal_nr)
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        print(f"  OK: {personal_nr} - {to_name} <{to_email}>")
        return True
    except Exception as e:
        print(f"  FEHLER: {personal_nr} - {to_name} <{to_email}> -> {e}")
        return False


def main():
    live_mode = '--live' in sys.argv

    if live_mode:
        print("=== ECHTVERSAND ===")
        employees = get_employees()
        print(f"{len(employees)} Mitarbeiter gefunden\n")

        ok = 0
        fail = 0
        for pnr, first, last, email in employees:
            email = EMAIL_OVERRIDES.get(pnr, email)
            if send_email(email, f"{first} {last}", pnr):
                ok += 1
            else:
                fail += 1

        print(f"\nFertig: {ok} gesendet, {fail} fehlgeschlagen")
    else:
        print("=== TESTMODUS ===")
        print(f"Sende Test-Mail an {TEST_EMAIL}...\n")
        send_email(TEST_EMAIL, TEST_NAME, TEST_PNR)
        print(f"\nTest abgeschlossen. Fuer Echtversand: python3 {sys.argv[0]} --live")


if __name__ == '__main__':
    main()
