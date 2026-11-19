# Monatsabschluss-Test auf DEV – Do 19.11.2026, ab ca. 21:15

*Für Drazen. Alles läuft auf **dev.seda.de** mit einer frischen Kopie der LIVE-Daten (automatisch um 20:45). An LIVE und an deinen echten Lexware-Abrechnungen ändert sich nichts.*

**Testmonat: Oktober 2026.** Er ist vollständig, und die echten Oktober-Lohnabrechnungen liegen vor. So können wir jede Zahl der Importdatei mit dem vergleichen, was tatsächlich abgerechnet wurde. Ein November „bis heute“ wäre nur halb und mit nichts vergleichbar.

---

## A) Vor dem Termin (ca. 15 Min.)

### 1. Lexware-Datensicherung

1. Lexware lohn+gehalt öffnen, Firma **Seda Consulting GmbH**.
2. **Datei › Datensicherung › Daten sichern**. Der Menüname kann je nach Version leicht abweichen, im Zweifel F1 und „Datensicherung“ suchen.
3. Ziel: ein Ordner **außerhalb** von OneDrive, z. B. `C:\Lexware-Sicherung\2026-11-19_vor_Test`.
4. Prüfen, dass die Sicherungsdatei mit heutigem Datum dort liegt.

### 2. Testfirma anlegen – nur dort wird heute importiert

1. Testfirma als **Kopie** der echten Firma anlegen:
   - entweder über **Datei › Firma kopieren** (falls vorhanden),
   - oder die Sicherung aus Schritt 1 als **neue Firma zurücksichern**.
2. Name: **`TEST Seda Consulting – nicht abrechnen`**.
3. In der Testfirma den **PDF-Ausgabeordner** für Lohnabrechnungen auf einen eigenen Ordner stellen:
   `X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\TEST_Lohnabrechnung`
   So landen Test-PDFs nie zwischen den echten.
4. Vor jedem Import und jedem Druck in der Titelleiste prüfen: **TEST**-Firma geöffnet?

> **Kein Melden, kein Versand an Behörden:** In der Testfirma nichts an Finanzamt oder Krankenkassen senden (ELStAM/SV-Meldungen) und keine Zahlungen erzeugen. Wenn Lexware beim Abschluss danach fragt: abbrechen.

### 3. Upload-Skript auf SEDA2026 installieren

Das machen wir gemeinsam; die Befehle stehen hier zum Nachschlagen.

1. Download: **https://dev.seda.de/downloads/seda24_lohn_upload.ps1**, z. B. nach `Downloads`.
2. PowerShell als **normaler Benutzer** öffnen (derselbe Benutzer wie beim Export-Abruf) und ausführen:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1" -Install `
     -Server https://dev.seda.de `
     -Ordner "X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\TEST_Lohnabrechnung" `
     -Monat 2026-10
   ```
   - Der **Export-Schlüssel** ist schon da (vom Zeiterfassungs-Export); es wird nichts abgefragt.
   - Erwartete Ausgabe: „Server https://dev.seda.de erreichbar, Schluessel ok (2026-10: 0 von 12 da)“.
3. Danach läuft die Windows-Aufgabe **„SEDA24 Lohnabrechnungen Upload“** alle 10 Minuten. Sofort auslösen:
   `powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt`
4. Protokoll: `%LOCALAPPDATA%\SEDA24-Export\lohn_upload.log`. Darin steht je Datei die Quittung des Servers und die Zuordnung.

**Später für LIVE:** dasselbe mit `-Server https://app.seda.de -Ordner "…\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung" -Monat ''`. Ohne festen Monat prüft das Skript dann den aktuellen und den Vormonat.

---

## B) Ablauf heute Abend

| # | Wer | Was | Ergebnis |
|---|---|---|---|
| 1 | Drazen | dev.seda.de/cockpit › **Monatsabschluss › Oktober 2026** | Prüfliste |
| 2 | Drazen | Prüfliste abhaken. **Ein Punkt ist rot:** Azra 03.10., Geiger „Kommen 13:01 / Gehen 10:29“ (alter Überschneidungs-Fehler, berechnet 3,0 Std. = richtig). Auf DEV über den Link in **Zeiten** auf 07:30–10:30 korrigieren. | Auf LIVE bleibt der Eintrag unverändert. Ob er dort korrigiert wird, entscheidest du separat. |
| 3 | gemeinsam | **Schritt 2 › Lohnarten:** die 3 fehlenden Nummern in der Testfirma nachsehen und eintragen: **Stunden**, **Sonderstunden (20 €)**, **KM-Geld (Betrag)**. Die übrigen (13 Sonntag, 11 Nacht, 16 Feiertag, 14 Urlaub) prüfen, dann „Nummern bestätigt“. Dazu das **Personalnummer-Format** wie in Lexware wählen: „D0040“ oder „40“. | Lexware-Vorschau ohne „eintragen“ |
| 4 | Drazen | **Für Lexware erzeugen**, dann **„Nur Importdatei als November 2026 (Testfirma)“**. Die Testfirma steht im Abrechnungsmonat November; die Werte sind die von Oktober. | `Lexware_Lohndaten_2026-10_als_2026-11_TEST.txt`: eine Datei für alle 12 MA |
| 5 | Drazen | Lexware (**TEST**-Firma) › Import-Assistent Lohndaten/Bewegungsdaten: Semikolon, Dezimalkomma, 1 Kopfzeile. Spalten: Jahr; Monat; Personalnummer; Lohnart; Wert; Stundensatz. | Import ohne Fehler |
| 6 | gemeinsam | **Vergleich** je MA: Testfirma-Abrechnung gegen die echte Oktober-Abrechnung (Stunden, Zuschläge, Urlaub, KM-Geld). Ruzica D0002: kein KM-Geld. | gleiche Beträge |
| 7 | Drazen | In der Testfirma die Lohnabrechnungen als PDF erzeugen, in den Ordner `TEST_Lohnabrechnung`. Eine Sammel-PDF oder einzelne Dateien gehen beides. | Das Skript lädt sie innerhalb von 10 Min. hoch (oder sofort mit `-Jetzt`) |
| 8 | Drazen | Cockpit **Schritt 3**: „**12 von 12 Lohnabrechnungen da ✓**“. Nicht zugeordnete Dateien hier per Auswahl zuordnen. | |
| 9 | Drazen | **Schritt 4 Vorschau** je MA: Anrede, Mail-Adresse, 3 Anhänge (D0002 ohne KM-Journal) | 12 von 12 bereit |
| 10 | Drazen | **Schritt 5 Testversand.** Der Testmodus bleibt an. Die Mails gehen nur an die Test-Adresse (siehe C). | Status je MA „Test“ |
| 11 | Drazen | **Super-PIN einrichten:** Schritt 5 › „Super-PIN einrichten“. Erst dein Login-Passwort zur Bestätigung, dann eine eigene PIN mit 6–10 Ziffern, zweimal. Nicht das Login-Passwort, keine Zahlenreihe; die PIN nie aufschreiben oder in den Chat. | „Super-PIN gespeichert“ |
| 12 | Drazen | **Sperre testen:** „Monat sperren“. Dann „Wieder öffnen“ mit Grund und Super-PIN, einmal absichtlich mit falscher PIN. Eine kleine Korrektur machen, z. B. eine Notiz in **Zeiten**, und wieder sperren. | Unten „Nachträgliche Änderungen“: Öffnung mit Grund, Änderung alt → neu, wer/wann, „Wieder gesperrt“; „Protokoll unverändert ✓“ |

**Super-PIN, Regeln:**
- Nur du als Inhaber; die Objektleitung sieht den Knopf nicht.
- Nach 5 Fehlversuchen ist die PIN 15 Minuten gesperrt, nach 10 dauerhaft. Zurücksetzen nur auf dem Server (`tools/superpin_reset.sh`), danach richtest du sie mit dem Login-Passwort neu ein.
- Die DEV-PIN bleibt beim Refresh erhalten. Für LIVE richtest du sie später einmal neu ein.

Nach dem Test: Testfirma in Lexware löschen oder deutlich als „TEST“ liegen lassen. Die Aufgabe „SEDA24 Lohnabrechnungen Upload“ bleibt bis zum LIVE-Umzug auf DEV gerichtet. Danach mit `-Install -Server https://app.seda.de …` umstellen oder mit `-Uninstall` entfernen.

---

## C) Testversand – welcher Weg?

Die Mails gehen nur an die Test-Adresse, in keinem Fall an Mitarbeiter.

| Weg | Wann | Was passiert |
|---|---|---|
| **Microsoft Graph** | Entra-App eingerichtet und im Cockpit eingetragen (Anleitung `anleitung_entra_lohnversand.md`) | Echte Mail an die Test-Adresse aus lohn@seda.de („SEDA24 Lohnbuchhaltung“), Kopie in „Gesendete Elemente“ von lohn@, Antworten dorthin. Das ist der Weg für den Betrieb. |
| **.eml-Dateien** (Standard ohne Microsoft-Freigabe) | sofort, nichts nötig | Jede Mail als Datei; Knopf „Testmails herunterladen (.eml)“. In Outlook öffnen: Absender „SEDA24 Lohnbuchhaltung“ <lohn@seda.de>, Antworten-an, Betreff, Text und Anhänge genau wie beim echten Versand. **Nichts verlässt den Server.** |
| SMTP-Zugang des Servers | nur auf deinen ausdrücklichen Wunsch | Der Server hat für Passwort-Mails einen Office-365-SMTP-Zugang (Absender dsertic@seda.de). Damit ginge eine echte Test-Mail an dich, gesperrt auf die Test-Adresse. Dafür würde ich den Zugang von LIVE nach DEV übernehmen (von Datei zu Datei, nie im Chat). |

**Mein Vorschlag für heute Abend:** **.eml-Dateien**. Damit siehst du jede Mail vollständig, und kein Weg nach außen ist offen. Sobald die Entra-App eingerichtet ist, folgt der erste echte Testversand über Graph an dich, nach deinem OK.
