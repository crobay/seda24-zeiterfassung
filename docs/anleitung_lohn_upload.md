# Lohnabrechnungen automatisch ins Cockpit – Upload-Skript installieren

*Für Drazen, Stand 26.11.2026 (Zeitplan 07:45). Dauer etwa 5 Minuten. Rechner: **SEDA2026**, derselbe Windows-Benutzer wie beim Zeiterfassungs-Export.*

**So funktioniert es:**
- Das Skript **`seda24_lohn_upload.ps1`** überwacht den Lexware-Ausgabeordner. Jede neue oder geänderte `Lohnabrechnung_*.pdf` lädt es per HTTPS in den Monatsabschluss des Cockpits.
- Es benutzt **denselben Export-Schlüssel** wie der Zeiterfassungs-Export. Ist der Export schon eingerichtet, wird nichts abgefragt.
- Eine Datei wird erst hochgeladen, wenn Lexware sie 1 Minute lang nicht mehr verändert hat.
- Jede Datei geht mit einer Prüfsumme (SHA-256) an den Server. Der Server prüft sie, speichert die Datei **verschlüsselt** und ordnet sie über Personalnummer bzw. Name zu. Sammel-PDFs teilt er je Mitarbeiter auf.
- Was der Server schon hat, wird nicht noch einmal geschickt. Ein abgeschlossener Monat nimmt nichts mehr an.
- Eine Windows-Aufgabe startet das Skript **vom 1. bis 15. jedes Monats stündlich von 07 bis 22 Uhr**, an allen anderen Tagen **einmal um 12 Uhr** (Lebenszeichen), dazu 2 Minuten nach der Anmeldung. War der Laptop aus, holt Windows den verpassten Lauf nach.
- Das Skript startet **ohne Fenster** (`conhost.exe --headless`). Kann Windows das nicht, läuft PowerShell versteckt, und das Fenster kann kurz aufblitzen. Was gilt, steht beim Einrichten in der Ausgabe.
- Admin-Rechte brauchst du dafür nicht.

**Was du mitbekommst:**

| Wann | Wo | Text |
|---|---|---|
| Ein Monat ist vollständig | Telegram | 📄 Lohnabrechnungen Oktober 2026: 12 von 12 da |
| Eine oder mehrere Dateien gingen nicht hoch | Telegram, gleicher Fehler höchstens 1× in 6 Std. | ⚠️ Lohnabrechnung-Upload fehlgeschlagen (SEDA2026): … |
| Der Laptop meldet sich nicht | Telegram, höchstens 1× am Tag | ⚠️ Lohnabrechnung-Upload: SEDA2026 meldet sich nicht – … |
| Der Server ist nicht erreichbar | Hinweisfenster auf dem Laptop, höchstens 1× am Tag | SEDA24 Lohnabrechnungen konnten nicht hochgeladen werden … |
| Immer | Cockpit › Monatsabschluss › Schritt 3 | Upload-PC SEDA2026 zuletzt gemeldet: heute 09:00 · was im Lexware-Ordner liegt · letzter Fehler |

- **„Meldet sich nicht“** kommt nach 24 Std. ohne Meldung. Es zählen nur Werktage, das Wochenende zählt also nicht.
- Vom Exporttag (1. Werktag des Monats) bis zum Abschluss des Vormonats kommt die Meldung schon nach **3 Std.**, aber nur bis zum 15. (solange das Skript stündlich läuft). Dabei zählt nur die Zeit an Werktagen von 07 bis 22 Uhr ab Exporttag 07:00.
- Fällt eine Datei durch, laufen die anderen trotzdem weiter. Die fehlerhafte Datei versucht das Skript beim nächsten Lauf wieder.

---

## Umstellen auf den Echtbetrieb (https://app.seda.de)

**Voraussetzung:** Das Update ist auf app.seda.de eingespielt.

PowerShell **als normaler Benutzer** öffnen (Start › „PowerShell“, nicht „Als Administrator“). Die Befehle einzeln kopieren:

**1. Neues Skript herunterladen**
```powershell
Invoke-WebRequest https://app.seda.de/downloads/seda24_lohn_upload.ps1 -OutFile "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1"
```

**2. Alte Einrichtung entfernen.** Das entfernt die Aufgabe, die Einstellungen und den gemerkten Stand vom Test auf dev.seda.de. Der Export-Schlüssel bleibt.
```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Uninstall
```
> Wichtig: Ohne diesen Schritt merkt sich das Skript die schon an DEV geschickten Dateien und würde sie nie an app.seda.de schicken.

**3. Neu einrichten auf app.seda.de**
```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1" -Install -Server https://app.seda.de -Basis "X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen"
```
Erwartete Ausgabe, ungefähr:
```
Ordner: X:\...\Lohnabrechnungen\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung  Dateien: Lohnabrechnung_*.pdf
Server https://app.seda.de erreichbar, Schluessel ok (2026-10: 0 von 12 da)  Ordner: X:\...\Seda_Consulting_GmbH_2026_Oktober\Lohnabrechnung
Server https://app.seda.de erreichbar, Schluessel ok (2026-11: 0 von 12 da)  Ordner: noch nicht vorhanden
Aufgabe 'SEDA24 Lohnabrechnungen Upload' eingerichtet (1.-15. stuendlich 07-22 Uhr, sonst taeglich 12 Uhr, verpasste Laeufe nachholen, 2 Min nach Anmeldung), Start ohne Fenster (conhost --headless)
hochgeladen 2026-10: Lohnabrechnung_2026_Oktober_D0001_... (gespeichert) -> Drazen Sertic
...
Stand 2026-10: 12 von 12 Lohnabrechnungen da, 0 ohne Zuordnung
```
Danach kannst du die Datei in `Downloads` löschen. Das Skript liegt jetzt in `%LOCALAPPDATA%\SEDA24-Export\`.

**4. Prüfen**
- Cockpit › Monatsabschluss › Schritt 3: Dort steht „Upload-PC SEDA2026 zuletzt gemeldet: heute …“.
- Aufgabe ansehen:
  ```powershell
  Get-ScheduledTask 'SEDA24 Lohnabrechnungen Upload' | Select-Object -ExpandProperty Triggers | Format-List StartBoundary, Repetition
  ```

## Sofort hochladen (-Jetzt)

Nach einem neuen Lexware-Lauf musst du nicht auf den nächsten Lauf warten (volle Stunde bzw. nach dem 15. erst 12 Uhr am nächsten Tag):
```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt
```
- Protokoll: `%LOCALAPPDATA%\SEDA24-Export\lohn_upload.log`. Je Datei steht dort: „hochgeladen 2026-10: Lohnabrechnung_… (gespeichert) -> Name“, danach der Stand „x von 12“.
- „wird noch geschrieben, spaeter“ ist normal, wenn Lexware gerade erst gespeichert hat. Nach 1 Minute noch einmal `-Jetzt`.

## Andere Dateinamen, Entfernen

- **Andere Dateinamen:** Lexware speichert eine Sammel-PDF unter anderem Namen? Dann beim Einrichten zusätzlich `-Filter "*.pdf"` angeben.
- **Entfernen:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Uninstall
  ```
  Das entfernt die Aufgabe und die Einstellungen. Der Export-Schlüssel bleibt für den Zeiterfassungs-Export.
- **Test gegen DEV** (nur auf Anweisung): `-Install -Server https://dev.seda.de`, fester Testordner mit `-Ordner "X:\...\TEST_Lohnabrechnung" -Monat 2026-10`. Zurück auf app.seda.de immer mit Schritt 2 und 3 von oben.

**Wenn etwas nicht klappt:**

| Meldung im Protokoll | Ursache / Abhilfe |
|---|---|
| „Kein Zugriff“ (403) | Export-Schlüssel falsch oder fehlt. Ist der Zeiterfassungs-Export auf diesem Benutzer eingerichtet? |
| „Nur ueber HTTPS“ | Server-Adresse mit `https://` angeben |
| „Pruefsumme stimmt nicht“ (422) | Übertragung gestört; wird beim nächsten Lauf automatisch wiederholt |
| „(413) Request Entity Too Large“ | PDF größer als 10 MB. Die anderen Dateien gehen trotzdem hoch. |
| „nichts Neues“, obwohl PDFs da sind | Ordner nicht gefunden (Laufwerk X: nicht verbunden, OneDrive noch nicht synchronisiert), Dateiname passt nicht zum Filter, oder der Monat ist im Cockpit gesperrt. Was das Skript im Ordner sieht, steht in Schritt 3 unter „Lexware-Ordner“. |
| „Hinweisfenster heute schon gezeigt“ | Der Server war nicht erreichbar; das Fenster kommt nur einmal am Tag. Internet bzw. app.seda.de prüfen. |
| „Ordner ohne {Jahr}/{Monat}: bitte -Monat JJJJ-MM angeben“ | Fester Ordner ohne Monatsmuster braucht `-Monat` |

**Sicherheit:**
- Der Schlüssel liegt nur verschlüsselt für deinen Windows-Benutzer auf dem PC.
- Jeder Upload, jeder Fehler und jede Ablehnung steht im Änderungsprotokoll, mit Rechnername und Prüfsumme.
- Die Lohnabrechnungen liegen auf dem Server verschlüsselt. Die Löschfrist stellst du im Monatsabschluss ein.
