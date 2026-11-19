# Monatsabschluss-Test auf DEV – Do 19.11.2026, ab ca. 21:15 – Checkliste

*Für Drazen. Alles läuft auf **dev.seda.de** mit einer frischen Kopie der LIVE-Daten (automatisch um 20:45). An LIVE und an deinen echten Lexware-Abrechnungen ändert sich nichts. Es geht keine Mail und keine Telegram-Nachricht an Mitarbeiter.*

**Testmonat: Oktober 2026.** Er ist vollständig, und die echten Oktober-Lohnabrechnungen liegen vor. So können wir jede Zahl der Importdatei mit dem vergleichen, was tatsächlich abgerechnet wurde.

**Zeitplan:**

| Wann | Wer | Was |
|---|---|---|
| bis 20:45 | Drazen | Teil A: Lexware sichern, Testfirma, 3 Lohnart-Nummern heraussuchen, Upload-Skript installieren |
| 20:45 | automatisch | DEV holt eine frische LIVE-Kopie, Teil B |
| ca. 21:00 | Claude | Refresh-Protokoll prüfen, Ergebnis in den Chat |
| ab 21:15 | gemeinsam | Teil C: Durchlauf Oktober |

---

## A) Vor dem Termin – Drazen (ca. 30 Min.)

### A1. Lexware-Datensicherung (zuerst!)

- [ ] Lexware lohn+gehalt öffnen, Firma **Seda Consulting GmbH**.
- [ ] **Datei › Datensicherung › Daten sichern**. Der Menüname kann je nach Version leicht abweichen, im Zweifel F1 und „Datensicherung“ suchen.
- [ ] Ziel: ein Ordner **außerhalb** von OneDrive, z. B. `C:\Lexware-Sicherung\2026-11-19_vor_Test`.
- [ ] Prüfen, dass die Sicherungsdatei mit heutigem Datum dort liegt und nicht 0 KB groß ist.

### A2. Testfirma – nur dort wird heute importiert

- [ ] Testfirma als **Kopie** der echten Firma anlegen:
  - entweder über **Datei › Firma kopieren** (falls vorhanden),
  - oder die Sicherung aus A1 als **neue Firma zurücksichern**.
- [ ] Name: **`TEST Seda Consulting – nicht abrechnen`**.
- [ ] In der Testfirma den **PDF-Ausgabeordner** für Lohnabrechnungen auf einen eigenen Ordner stellen und den Ordner anlegen:
      `X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\TEST_Lohnabrechnung`
      So landen Test-PDFs nie zwischen den echten.
- [ ] Merken: vor jedem Import und jedem Druck in der Titelleiste prüfen, ob die **TEST**-Firma offen ist.

> **Kein Melden, kein Versand an Behörden:** In der Testfirma nichts an Finanzamt oder Krankenkassen senden (ELStAM/SV-Meldungen) und keine Zahlungen erzeugen. Wenn Lexware danach fragt: abbrechen.

### A3. Die 3 fehlenden Lohnart-Nummern heraussuchen

Das Cockpit braucht für die Importdatei die Lexware-Nummer je Lohnart. Bekannt sind schon 13 Sonntag, 11 Nacht, 16 Feiertag und 14 Urlaub. **Es fehlen drei:**

| Cockpit | Was in Lexware | Nummer |
|---|---|---|
| **Stunden** | Stundenlohn, normale Arbeitsstunden (Menge = Stunden) | ______ |
| **Sonderstunden (20 €)** | eigene Lohnart für Sonderstunden mit 20 €/Std. | ______ |
| **KM-Geld** | Fahrtkosten-/Kilometergeld als **Betrag** in € (nicht als Stunden) | ______ |

**Wo du sie findest**, am einfachsten in dieser Reihenfolge:
1. **Echte Oktober-Lohnabrechnung** eines Mitarbeiters mit allen drei Arten, z. B. Lara D0040 oder Helena D0039 (PDF im echten Oktober-Ordner). Vor jeder Zeile unter „Bezüge“ steht die Lohnart-Nummer.
2. **Lexware › Firma › Lohnarten** (je nach Version auch „Firmenstammdaten › Lohnarten“ oder „Verwaltung › Lohnarten“). Das ist die Liste aller Lohnarten mit Nummer und Bezeichnung; dort kannst du auch prüfen, ob die Art als Menge × Satz oder als Betrag angelegt ist.
3. **Mitarbeiter öffnen › Bezüge** (bzw. „Lohnarten“/„Bewegungsdaten“). Dort steht, mit welchen Nummern der Mitarbeiter abgerechnet wird.

- [ ] Die drei Nummern oben eintragen; bei 13/11/16/14 kurz prüfen, ob sie stimmen.
- [ ] Ebenfalls nachsehen: In welchem **Format** steht die Personalnummer in Lexware, „D0040“ oder „40“?
- [ ] Prüfen, ob KM-Geld bei dir eine eigene Lohnart ist oder über die Reisekosten läuft. Ist es nicht als Lohnart drin, sag es heute Abend, dann lassen wir KM-Geld aus der Importdatei.

### A4. Upload-Skript auf SEDA2026 installieren

Die ausführliche Anleitung steht in `anleitung_lohn_upload.md`. Kurz:

- [ ] Download: **https://dev.seda.de/downloads/seda24_lohn_upload.ps1**, nach `Downloads`.
- [ ] PowerShell als **normaler Benutzer** öffnen (derselbe Benutzer wie beim Export-Abruf) und ausführen:
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1" -Install `
    -Server https://dev.seda.de `
    -Ordner "X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\TEST_Lohnabrechnung" `
    -Monat 2026-10
  ```
- [ ] Erwartete Ausgabe: „Server https://dev.seda.de erreichbar, Schluessel ok (2026-10: 0 von 12 da)“. Der Export-Schlüssel ist schon da, es wird nichts abgefragt.
- [ ] Danach läuft die Windows-Aufgabe **„SEDA24 Lohnabrechnungen Upload“** alle 10 Minuten. Sofort auslösen:
  `powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt`
- Protokoll: `%LOCALAPPDATA%\SEDA24-Export\lohn_upload.log`.

> Am Server ist der Upload heute um 14:15 über https://dev.seda.de geprüft:
> - Eine Testdatei wurde gespeichert und über die Personalnummer Lara zugeordnet („1 von 12“).
> - Eine falsche Prüfsumme wird abgelehnt.
> - Der Refresh um 20:45 räumt die Testdatei wieder weg.

---

## B) 20:45 – DEV-Refresh (automatisch)

Ablauf des Refreshs:
1. DEV wird gesichert.
2. LIVE wird nur gelesen.
3. dev_cockpit wird neu aufgebaut, dazu Cockpit-Tabellen, Monatssperre und Super-PIN-Schutz.
4. DEV-Einstellungen kommen zurück: Lohnarten, Testmodus, Absender lohn@.
5. Alle Telegram-Chat-IDs und Push-Abos werden auf der Kopie abgeschaltet.
6. Die Vorlage bekommt den Startbestand KW 48 (23 Einträge).

**Generalprobe heute 14:09:** fehlerfrei in 9 Sekunden. Kontrollzeile: 1476 Zeiten, **0 Chat-IDs**, 10 Sperr-Trigger, Super-PIN-Inhaber = dein Admin-Login, Vorlage 23 Einträge.

- [ ] ca. 21:00 – Claude: Protokoll `backups/refresh_20261119_2045.log` prüfen, „REFRESH OK“ und die Kontrollzeile melden.
- **Falls der Refresh scheitert:** DEV bleibt auf der Kopie von 14:09. Für Oktober ist sie gleichwertig, denn seitdem kommen nur November-Buchungen dazu. Der Test kann trotzdem laufen.

---

## C) Durchlauf ab 21:15 – gemeinsam

- [ ] **1 – Drazen:** dev.seda.de/cockpit › **Monatsabschluss › Oktober 2026**. Ergebnis: Prüfliste.
- [ ] **2 – Drazen:** Prüfliste abhaken.
  - Ein Punkt ist rot: Azra 03.10., Geiger „Kommen 13:01 / Gehen 10:29“. Das ist der alte Überschneidungs-Fehler; berechnet sind 3,0 Std., das ist richtig.
  - Auf DEV über den Link in **Zeiten** auf 07:30–10:30 korrigieren.
  - Auf LIVE bleibt der Eintrag unverändert. Ob er dort korrigiert wird, entscheidest du separat.
- [ ] **3 – gemeinsam: Schritt 2 › Lohnarten.**
  - Die 3 Nummern aus A3 eintragen; 13/11/16/14 prüfen, dann „Nummern bestätigt“.
  - **Personalnummer-Format** wie in Lexware wählen.
  - Ergebnis: Lexware-Vorschau ohne „eintragen“.
- [ ] **4 – Drazen:** **Für Lexware erzeugen**, dann **„Nur Importdatei als November 2026 (Testfirma)“**.
  - Die Testfirma steht im Abrechnungsmonat November; die Werte sind die von Oktober.
  - Ergebnis: `Lexware_Lohndaten_2026-10_als_2026-11_TEST.txt`, eine Datei für alle 12 MA.
- [ ] **5 – Drazen:** Lexware (**TEST**-Firma) › Import-Assistent Lohndaten/Bewegungsdaten.
  - Einstellungen: Semikolon, Dezimalkomma, 1 Kopfzeile.
  - Spalten: Jahr; Monat; Personalnummer; Lohnart; Wert; Stundensatz.
  - Ergebnis: Import ohne Fehler.
- [ ] **6 – gemeinsam:** **Vergleich** je MA, Testfirma-Abrechnung gegen die echte Oktober-Abrechnung: Stunden, Zuschläge, Urlaub, KM-Geld. Ruzica D0002 bekommt kein KM-Geld. Ergebnis: gleiche Beträge.
- [ ] **7 – Drazen:** In der Testfirma die Lohnabrechnungen als PDF erzeugen, in den Ordner `TEST_Lohnabrechnung`.
  - Eine Sammel-PDF oder einzelne Dateien gehen beides.
  - Das Skript lädt sie innerhalb von 10 Min. hoch, sofort mit `-Jetzt`.
- [ ] **8 – Drazen:** Cockpit **Schritt 3** zeigt „**12 von 12 Lohnabrechnungen da ✓**“. Nicht zugeordnete Dateien hier per Auswahl zuordnen.
- [ ] **9 – Drazen:** **Schritt 4 Vorschau** je MA: Anrede, Mail-Adresse, 3 Anhänge (D0002 ohne KM-Journal). Ergebnis: 12 von 12 bereit.
- [ ] **10 – Drazen:** **Schritt 5 Testversand.**
  - Absender prüfen: „SEDA24 Lohnbuchhaltung“ <lohn@seda.de>, Antworten an lohn@.
  - Der Testmodus bleibt an. Die Mails werden als **.eml** erzeugt (siehe D); keine geht an Mitarbeiter.
  - Ergebnis: Status je MA „Test“.
- [ ] **11 – Drazen: Super-PIN einrichten.**
  - Schritt 5 › „Super-PIN einrichten“.
  - Zuerst dein Login-Passwort zur Bestätigung, dann eine eigene PIN mit 6–10 Ziffern, zweimal.
  - Nicht das Login-Passwort, keine Zahlenreihe. Die PIN nie aufschreiben und nie in den Chat.
  - Ergebnis: „Super-PIN gespeichert“.
- [ ] **12 – Drazen: Sperre testen.**
  - „Monat sperren“.
  - Dann „Wieder öffnen“ mit Grund und Super-PIN, einmal absichtlich mit falscher PIN.
  - Eine kleine Korrektur machen, z. B. eine Notiz in **Zeiten**, und wieder sperren.
  - Ergebnis unten unter „Nachträgliche Änderungen“: Öffnung mit Grund, Änderung alt → neu, wer/wann, „Wieder gesperrt“, „Protokoll unverändert ✓“.
- [ ] **13 – Drazen, optional: Dienstplan › KW 48.**
  - Die festen Schichten tragen die Stecknadel „fix“.
  - In KW 49 sind samstags Matej und Ljubica **nicht** in der Vorlage, in KW 50 wieder (lange Woche).
  - Ein Häkchen „fix“ an einer Schicht setzen oder entfernen, dann unter **Vorlage** nachsehen.

**Super-PIN, Regeln:**
- Nur du als Inhaber; die Objektleitung sieht den Knopf nicht.
- Nach 5 Fehlversuchen ist die PIN 15 Minuten gesperrt, nach 10 dauerhaft. Zurücksetzen geht nur auf dem Server (`tools/superpin_reset.sh`); danach richtest du sie mit dem Login-Passwort neu ein.
- Die DEV-PIN bleibt bei späteren Refreshs erhalten. Für LIVE richtest du sie später einmal neu ein.

**Nach dem Test:**
- [ ] Testfirma in Lexware löschen oder deutlich als „TEST“ liegen lassen.
- [ ] Die Aufgabe „SEDA24 Lohnabrechnungen Upload“ bleibt bis zum LIVE-Umzug auf DEV gerichtet. Danach mit `-Install -Server https://app.seda.de -Monat ''` umstellen oder mit `-Uninstall` entfernen.
- [ ] Entscheidungen für danach:
  - Eintrag 2065 auf LIVE korrigieren?
  - Entra-App einrichten (Anleitung `anleitung_entra_lohnversand.md`, Postfach lohn@ ist da)
  - GO für den LIVE-Umzug des Cockpits

---

## D) Testversand – welcher Weg?

Die Mails gehen nur an die Test-Adresse, in keinem Fall an Mitarbeiter.

| Weg | Wann | Was passiert |
|---|---|---|
| **.eml-Dateien** (heute Abend) | sofort, nichts nötig | Jede Mail als Datei; Knopf „Testmails herunterladen (.eml)“. In Outlook öffnen: Absender „SEDA24 Lohnbuchhaltung“ <lohn@seda.de>, Antworten-an, Betreff, Text und Anhänge genau wie beim echten Versand. **Nichts verlässt den Server.** |
| **Microsoft Graph** (Betrieb) | nach Einrichtung der Entra-App (Anleitung `anleitung_entra_lohnversand.md`; das Postfach lohn@ ist schon angelegt) | Echte Mail an die Test-Adresse aus lohn@seda.de, Kopie in „Gesendete Elemente“ von lohn@, Antworten dorthin. Der erste echte Testversand geht nur an dich und nur nach deinem OK. |
| SMTP-Zugang des Servers | nur auf deinen ausdrücklichen Wunsch | Absender wäre das Server-Konto (Microsoft erlaubt dort kein lohn@), Antworten-an lohn@. Nur an die Test-Adresse. |
