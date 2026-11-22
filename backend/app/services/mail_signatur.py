"""SEDA24-Mail-Signatur (Lohn-Mail, Material-Mail an Kunden) im Stil von Drazens Outlook-Signatur, ohne Foto und
ohne Personenname: Tabelle mit schmaler hellblauer Linie, Logo, Titel/Firma, Zeilen mit Icons, Haftungsausschluss.
Bilder liegen in app/assets/lohnmail und werden als CID eingebettet (kein externer Abruf, kein Tracker).
Nur Tabellen + Inline-Styles + width/height-Attribute: Outlook (auch Dunkelmodus) und Gmail zeigen es gleich."""
import os
from html import escape

FIRMA = "Seda Consulting GmbH"
TEL_TEXT, TEL_URI = "+49 (0) 72 25 - 180 49 70", "tel:+4972251804970"
WEB = "www.seda24.de"
ADRESSE = ("Zeppelinstr. 42", "76571 Gaggenau")
REGISTER = ("Amtsgericht Mannheim", "HRB: 739405")
DISCLAIMER = ("HAFTUNGSAUSSCHLUSS: Diese E-Mail-Nachricht, einschließlich aller Anhänge, ist ausschließlich für den/die "
              "beabsichtigten Empfänger bestimmt und kann vertrauliche und privilegierte Informationen enthalten, die "
              "gesetzlich geschützt sind. Jede unbefugte Überprüfung, Verwendung oder Verbreitung ist untersagt. Wenn Sie "
              "nicht der beabsichtigte Empfänger sind, wenden Sie sich bitte per Antwort-E-Mail an den Absender und "
              "vernichten Sie alle Kopien der ursprünglichen Nachricht.")
BILDER = {"logo": "logo.png", "tel": "tel.png", "mail": "mail.png", "web": "web.png", "pin": "pin.png", "recht": "recht.png"}
BILD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "lohnmail")
F = "font-family:Arial,Helvetica,sans-serif;"
NAVY, HELL, INK, GRAU = "#1E537C", "#8EC1E6", "#1C2B38", "#8A8F98"
BODY = '<body style="margin:0;padding:16px;">'


def bilder():
    """[(content_id, dateiname, bytes)] fuer die eingebetteten Signatur-Bilder."""
    out = []
    for cid, datei in BILDER.items():
        with open(os.path.join(BILD_DIR, datei), "rb") as f:
            out.append((f"{cid}@seda24", f"sig_{datei}", f.read()))
    return out


def text(titel, mail):
    """Signatur fuer den Text-Teil (Ausweichversion)."""
    return "\n".join([titel, FIRMA, f"Tel. {TEL_TEXT}", mail, WEB, ", ".join(ADRESSE), ", ".join(REGISTER).replace("HRB:", "HRB")]) \
        + "\n\n" + DISCLAIMER


def html(titel, mail):
    """Signatur-Tabelle + Haftungsausschluss (HTML-Teil)."""
    a = f'style="{F}color:{NAVY};text-decoration:none;"'
    zeilen = [("tel", f'<a href="{TEL_URI}" {a}>{escape(TEL_TEXT)}</a>'),
              ("mail", f'<a href="mailto:{escape(mail)}" {a}>{escape(mail)}</a>'),
              ("web", f'<a href="https://{WEB}" {a}>{WEB}</a>'),
              ("pin", "<br>".join(escape(z) for z in ADRESSE)),
              ("recht", "<br>".join(escape(z) for z in REGISTER))]
    reihen = "".join(
        f'<tr><td width="18" valign="top" style="width:18px;padding:0 8px 6px 0;">'
        f'<img src="cid:{cid}@seda24" width="18" height="18" alt="" style="display:block;width:18px;height:18px;border:0;"></td>'
        f'<td valign="middle" style="{F}font-size:12px;line-height:16px;color:{INK};padding:1px 0 6px 0;">{inhalt}</td></tr>'
        for cid, inhalt in zeilen)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 16px;">'
        f'<tr><td width="3" bgcolor="{HELL}" style="width:3px;min-width:3px;background-color:{HELL};font-size:1px;line-height:1px;">&nbsp;</td>'
        '<td width="14" style="width:14px;font-size:1px;line-height:1px;">&nbsp;</td>'
        '<td valign="top" style="padding:2px 0;">'
        '<img src="cid:logo@seda24" width="120" height="40" alt="SEDA24" style="display:block;width:120px;height:40px;border:0;margin:0 0 10px;">'
        f'<div style="{F}font-size:15px;line-height:19px;font-weight:bold;color:{NAVY};">{escape(titel)}</div>'
        f'<div style="{F}font-size:13px;line-height:18px;color:{INK};margin:0 0 10px;">{FIRMA}</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">{reihen}</table>'
        '</td></tr></table>'
        f'<p style="{F}font-size:9px;line-height:12px;color:{GRAU};margin:0;max-width:600px;">{escape(DISCLAIMER)}</p>')


def absatz(t, html_inhalt=None):
    return f'<p style="{F}font-size:14px;line-height:1.45;color:{INK};margin:0 0 14px;">{html_inhalt or escape(t)}</p>'


def dokument(inhalt_html, titel, mail, vorspann=""):
    """Ganze HTML-Mail: (Testmodus-Vorspann), Inhalt, "Mit freundlichen Grüßen", Signatur."""
    teile = [f'<p style="{F}font-size:14px;color:#b45309;margin:0 0 14px;"><b>{escape(vorspann)}</b></p>'] if vorspann else []
    teile += [inhalt_html, f'<p style="{F}font-size:14px;color:{INK};margin:0 0 16px;">Mit freundlichen Grüßen</p>', html(titel, mail)]
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">'
            '<meta name="supported-color-schemes" content="light dark"></head>' + BODY + "".join(teile) + "</body></html>")
