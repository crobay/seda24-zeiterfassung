"""SEDA24-Mail-Signatur (Lohn-Mail, Material-Mail an Kunden) im Layout von Drazens Outlook-Signatur, ohne Foto und
ohne Personenname. HTML 1:1 von Drazen (28.11.2026 08:29), nur Titel und Mail-Adresse wechseln je Absender
(Lohn: "SEDA24 Lohnbuchhaltung" / lohn@seda.de, Material: "SEDA24 Objektbetreuung" / material@seda24.de).
Bilder (Logo, Icons) werden wie in Outlook vom emailacademy-CDN geladen, nichts mehr eingebettet."""
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
F = "font-family:Arial,Helvetica,sans-serif;"
NAVY, HELL, INK, GRAU = "#1E537C", "#8EC1E6", "#1C2B38", "#8A8F98"
BODY = '<body style="margin:0;padding:16px;">'


def bilder():
    """Eingebettete Signatur-Bilder: keine mehr (Bilder kommen per Link wie in Outlook, Drazen 28.11.2026)."""
    return []


def text(titel, mail):
    """Signatur fuer den Text-Teil (Ausweichversion)."""
    return "\n".join([titel, FIRMA, f"Tel. {TEL_TEXT}", mail, WEB, ", ".join(ADRESSE), ", ".join(REGISTER).replace("HRB:", "HRB")]) \
        + "\n\n" + DISCLAIMER


# Drazen 28.11.2026 08:29, wortlich; @@TITEL@@ / @@MAIL@@ werden ersetzt (Tel-Link korrigiert auf tel:+4972251804970)
SIGNATUR_HTML = (
    '<table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,Helvetica,sans-serif;border-collapse:collapse;"><tr><td style="background-color:#2d5277;width:3px;padding:0;"></td><td style="padding:0 0 0 10px;">'
    '<table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,Helvetica,sans-serif;border-collapse:collapse;">'
    '<tr><td style="padding:0 0 8px 0;"><img src="@@CDN@@logo2024_10_27_18_20_29.png" width="117" height="36" alt="SEDA24" border="0" style="display:block;"></td></tr>'
    '<tr><td style="font-size:18px;line-height:20px;font-weight:700;color:#2d5277;">@@TITEL@@</td></tr>'
    '<tr><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 10px 0;">Seda Consulting GmbH</td></tr></table>'
    '<table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,Helvetica,sans-serif;border-collapse:collapse;">'
    '<tr><td style="padding:0 10px 4px 0;width:24px;vertical-align:middle;"><img src="@@CDN@@p2024_10_27_18_20_29.png" width="24" height="24" alt="" border="0" style="display:block;"></td><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 4px 0;vertical-align:middle;"><a href="tel:+4972251804970" style="color:#000001;text-decoration:none;">+49 (0) 72 25 - 180 49 70</a></td></tr>'
    '<tr><td style="padding:0 10px 4px 0;width:24px;vertical-align:middle;"><img src="@@CDN@@m2024_10_27_18_20_29.png" width="24" height="24" alt="" border="0" style="display:block;"></td><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 4px 0;vertical-align:middle;"><a href="mailto:@@MAIL@@" style="color:#000001;text-decoration:none;">@@MAIL@@</a></td></tr>'
    '<tr><td style="padding:0 10px 4px 0;width:24px;vertical-align:middle;"><img src="@@CDN@@w2024_10_27_18_20_29.png" width="24" height="24" alt="" border="0" style="display:block;"></td><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 4px 0;vertical-align:middle;"><a href="https://www.seda24.de" style="color:#000001;text-decoration:none;">www.seda24.de</a></td></tr>'
    '<tr><td style="padding:0 10px 6px 0;width:24px;vertical-align:middle;"><img src="@@CDN@@gm2024_10_27_18_20_29.png" width="24" height="24" alt="" border="0" style="display:block;"></td><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 6px 0;vertical-align:middle;"><a href="https://maps.app.goo.gl/YCviBt3UEaC8TAQZ8" style="color:#000001;text-decoration:none;">Zeppelinstr. 42<br>76571 Gaggenau</a></td></tr>'
    '<tr><td style="padding:0 10px 8px 0;width:24px;vertical-align:middle;"><img src="@@CDN@@law2024_10_26_17_53_55.png" width="16" height="16" alt="" border="0" style="display:block;"></td><td style="font-size:14px;line-height:16px;color:#000001;padding:0 0 8px 0;vertical-align:middle;">Amtsgericht Mannheim<br>HRB: 739405</td></tr></table>'
    '</td></tr><tr><td colspan="2" style="font-size:8px;line-height:10px;color:#afafaf;padding:10px 0 0 0;max-width:440px;">@@DISCLAIMER@@</td></tr></table>'
).replace("@@CDN@@", "https://cdn.emailacademy.com/user/17187e6d04791d2e5725ca8e4f31900966ab9130d1e80060569bcfb3e1e023d9/")


def html(titel, mail):
    """Signatur-Tabelle mit Haftungsausschluss (HTML-Teil), Drazens HTML 1:1."""
    return (SIGNATUR_HTML.replace("@@TITEL@@", escape(titel)).replace("@@MAIL@@", escape(mail))
            .replace("@@DISCLAIMER@@", DISCLAIMER))


def absatz(t, html_inhalt=None):
    return f'<p style="{F}font-size:14px;line-height:1.45;color:{INK};margin:0 0 14px;">{html_inhalt or escape(t)}</p>'


def dokument(inhalt_html, titel, mail, vorspann=""):
    """Ganze HTML-Mail: (Testmodus-Vorspann), Inhalt, "Mit freundlichen Grüßen", Signatur."""
    teile = [f'<p style="{F}font-size:14px;color:#b45309;margin:0 0 14px;"><b>{escape(vorspann)}</b></p>'] if vorspann else []
    teile += [inhalt_html, f'<p style="{F}font-size:14px;color:{INK};margin:0 0 16px;">Mit freundlichen Grüßen</p>', html(titel, mail)]
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">'
            '<meta name="supported-color-schemes" content="light dark"></head>' + BODY + "".join(teile) + "</body></html>")
