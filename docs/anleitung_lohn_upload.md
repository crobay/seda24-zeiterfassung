# Lohnabrechnungen automatisch ins Cockpit – Upload-Skript installieren

*Für Drazen, Stand 19.11.2026. Dauer etwa 5 Minuten. Rechner: **SEDA2026**, derselbe Windows-Benutzer wie beim Zeiterfassungs-Export.*

**So funktioniert es:**
- Das Skript **`seda24_lohn_upload.ps1`** überwacht den Lexware-Ausgabeordner. Jede neue oder geänderte `Lohnabrechnung_*.pdf` lädt es per HTTPS in den Monatsabschluss des Cockpits.
- Es ist das Gegenstück zum Export-Abruf und benutzt **denselben Export-Schlüssel**. Ist der Export schon eingerichtet, wird nichts abgefragt.
- Eine Datei wird erst hochgeladen, wenn Lexware sie 1 Minute lang nicht mehr verändert hat.
- Jede Datei geht mit einer Prüfsumme (SHA-256) an den Server. Der Server prüft sie, speichert die Datei **verschlüsselt** und ordnet sie über Personalnummer bzw. Name zu. Danach schickt er eine Quittung zurück. Sammel-PDFs teilt er je Mitarbeiter auf.
- Was der Server schon hat, wird nicht noch einmal geschickt.
- Ist ein Monat abgeschlossen (gesperrt), lädt das Skript für ihn nichts mehr hoch, und der Server würde auch nichts annehmen.
- Eine Windows-Aufgabe startet das Skript **alle 10 Minuten** und 2 Minuten nach der Anmeldung.
- Admin-Rechte brauchst du dafür nicht.

**Im Cockpit:** Monatsabschluss › Schritt 3 zeigt „*x* von 12 Lohnabrechnungen da“. Nicht zugeordnete Dateien ordnest du dort per Auswahl zu.

---

## 1. Herunterladen

- Heute Abend (Test): **https://dev.seda.de/downloads/seda24_lohn_upload.ps1**
- Später (Betrieb): **https://app.seda.de/downloads/seda24_lohn_upload.ps1**, erst nach dem LIVE-Umzug

Speichern zum Beispiel unter `Downloads`.

## 2. Einrichten

PowerShell **als normaler Benutzer** öffnen (Start › „PowerShell“, nicht „Als Administrator“).

**Test heute Abend** – DEV-Server, fester Testordner, alles zählt für Oktober:
```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1" -Install `
  -Server https://dev.seda.de `
  -Ordner "X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\TEST_Lohnabrechnung" `
  -Monat 2026-10
```

**Betrieb (erst nach dem LIVE-Umzug):**
```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\seda24_lohn_upload.ps1" -Install `
  -Server https://app.seda.de -Monat ''
```
- Ohne `-Ordner` gilt der Standard `X:\…\Lohnabrechnungen\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung`. Das Skript prüft dann den aktuellen Monat und den Vormonat.
- `-Monat ''` entfernt den festen Testmonat.

**Erwartete Ausgabe:**
```
Server https://dev.seda.de erreichbar, Schluessel ok (2026-10: 0 von 12 da)
Ordner: X:\...\TEST_Lohnabrechnung  (fester Monat 2026-10)  Dateien: Lohnabrechnung_*.pdf
Aufgabe 'SEDA24 Lohnabrechnungen Upload' eingerichtet (alle 10 Minuten und 2 Min nach Anmeldung)
```

Das Skript kopiert sich dabei nach `%LOCALAPPDATA%\SEDA24-Export\`. Die Datei in `Downloads` kannst du danach löschen.

## 3. Sofort hochladen und Protokoll ansehen

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt
```
- Protokoll: `%LOCALAPPDATA%\SEDA24-Export\lohn_upload.log`. Je Datei steht dort: „hochgeladen 2026-10: Lohnabrechnung_… (gespeichert) -> Name“, danach der Stand „x von 12“.
- „wird noch geschrieben, spaeter“ ist normal, wenn Lexware gerade erst gespeichert hat. Nach 1 Minute noch einmal `-Jetzt`.

## 4. Andere Dateinamen, Entfernen

- **Andere Dateinamen:** Lexware speichert eine Sammel-PDF unter anderem Namen? Dann beim Einrichten zusätzlich `-Filter "*.pdf"` angeben.
- **Entfernen:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Uninstall
  ```
  Das entfernt nur die Aufgabe. Der Export-Schlüssel bleibt für den Zeiterfassungs-Export.
- **Umstellen von DEV auf LIVE:** einfach noch einmal `-Install` mit den Betriebs-Werten aus Schritt 2 aufrufen.

**Wenn etwas nicht klappt:**

| Meldung im Protokoll | Ursache / Abhilfe |
|---|---|
| „Kein Zugriff“ (403) | Export-Schlüssel falsch oder fehlt. Ist der Zeiterfassungs-Export auf diesem Benutzer eingerichtet? |
| „Nur ueber HTTPS“ | Server-Adresse mit `https://` angeben |
| „Pruefsumme stimmt nicht“ (422) | Übertragung gestört; wird beim nächsten Lauf automatisch wiederholt |
| „nichts Neues“, obwohl PDFs da sind | Ordner nicht gefunden (Laufwerk X: nicht verbunden, OneDrive noch nicht synchronisiert, Tippfehler im Pfad), Dateiname passt nicht zum Filter, oder der Monat ist im Cockpit gesperrt. Ein gesperrter Monat nimmt nur nach „Wieder öffnen“ mit Super-PIN wieder etwas an. |
| „Ordner ohne {Jahr}/{Monat}: bitte -Monat JJJJ-MM angeben“ | Fester Ordner ohne Monatsmuster braucht `-Monat` |

**Sicherheit:**
- Der Schlüssel liegt nur verschlüsselt für deinen Windows-Benutzer auf dem PC.
- Jeder Upload und jede Ablehnung steht im Änderungsprotokoll, mit Rechnername und Prüfsumme.
- Die Lohnabrechnungen liegen auf dem Server verschlüsselt. Die Löschfrist stellst du im Monatsabschluss ein.
