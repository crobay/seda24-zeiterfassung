# Microsoft-Zugang für den Lohnversand einrichten

*Für Drazen, Stand 19.11.2026. Dauer etwa 20 Minuten, dazu bis zu 1 Stunde Wartezeit, bis Microsoft die Beschränkung übernommen hat.*

**Ziel:** Das Cockpit verschickt die Lohn-Mails aus **buchhaltung@seda.de**. Jede Mail liegt danach in „Gesendete Elemente“ dieses Postfachs; es gibt kein BCC. Die App darf **nur** aus buchhaltung@seda.de senden, aus keinem anderen Postfach.

**Was du brauchst:**
- Anmeldung als globaler Administrator von Microsoft 365 (seda.de).
- Einen Windows-PC mit PowerShell (für Schritt 5).

> **Geheimnisse nicht weitergeben:** Den geheimen Clientschlüssel (Schritt 4) trägst du nur im Cockpit ein (Schritt 6), nirgends sonst. Nicht in den Chat, nicht in eine Mail, nicht auf Papier.

---

## 1. App registrieren

1. Öffne **https://entra.microsoft.com** und melde dich als Administrator an.
2. Klicke links **Anwendungen › App-Registrierungen › Neue Registrierung**.
3. Fülle die Felder aus:
   - **Name:** `SEDA24 Lohnversand`
   - **Unterstützte Kontotypen:** *Nur Konten in diesem Organisationsverzeichnis (nur SEDA – einzelner Mandant)*
   - **Umleitungs-URI:** leer lassen
4. Klicke **Registrieren**.
5. Auf der Übersichtsseite stehen zwei Werte. Lass die Seite offen, du brauchst sie in Schritt 5 und 6:
   - **Anwendungs-ID (Client)**
   - **Verzeichnis-ID (Mandant)**

## 2. Berechtigung „Mail.Send“ geben

1. Klicke in der App auf **API-Berechtigungen › Berechtigung hinzufügen › Microsoft Graph › Anwendungsberechtigungen**.
2. Suche `Mail.Send`, setze den Haken und klicke **Berechtigungen hinzufügen**.
3. Klicke **Administratorzustimmung für SEDA erteilen › Ja**.
4. Prüfe: Der Status zeigt ein grünes Häkchen „Gewährt für SEDA“.

> **Wichtig:** Ohne Schritt 5 dürfte die App aus **jedem** Postfach senden. Schritt 5 ist deshalb Pflicht, bevor der Zugang ins Cockpit kommt.

## 3. Mail-aktivierte Sicherheitsgruppe nur mit buchhaltung@ anlegen

1. Öffne **https://admin.exchange.microsoft.com** und klicke **Empfänger › Gruppen › Gruppe hinzufügen**.
2. Fülle die Gruppe aus:
   - **Typ:** *E-Mail-aktivierte Sicherheitsgruppe*
   - **Name:** `SEDA24 Lohnversand Postfach`
   - **E-Mail-Adresse:** `lohnversand-postfach@seda.de`
3. **Mitglied:** nur **buchhaltung@seda.de**.
4. Klicke **Erstellen**.

## 4. Geheimen Clientschlüssel erzeugen

1. Klicke in der App (entra.microsoft.com) auf **Zertifikate & Geheimnisse › Geheime Clientschlüssel › Neuer geheimer Clientschlüssel**.
2. Fülle die Felder aus:
   - **Beschreibung:** `Cockpit app.seda.de`
   - **Gültig bis:** 24 Monate
3. Kopiere den **Wert** sofort, er wird nur einmal angezeigt. Nicht die „Geheimnis-ID“ nehmen.
4. Trag dir das Ablaufdatum in den Kalender ein, mit Erinnerung 1 Monat vorher.

## 5. Zugriff auf buchhaltung@ beschränken (Application Access Policy)

Am PC: PowerShell **als Administrator** öffnen und die folgenden Befehle ausführen. `<Anwendungs-ID>` ersetzt du durch den Wert aus Schritt 1.

```powershell
Install-Module ExchangeOnlineManagement -Scope CurrentUser   # nur beim ersten Mal, Rückfragen mit J bestätigen
Connect-ExchangeOnline                                        # Anmeldefenster: Administrator

New-ApplicationAccessPolicy -AppId <Anwendungs-ID> `
  -PolicyScopeGroupId lohnversand-postfach@seda.de `
  -AccessRight RestrictAccess `
  -Description "SEDA24 Lohnversand: nur buchhaltung@seda.de"
```

Prüfen, frühestens 30–60 Minuten danach (vorher kann das Ergebnis noch falsch sein):

```powershell
Test-ApplicationAccessPolicy -Identity buchhaltung@seda.de -AppId <Anwendungs-ID>   # erwartet: AccessCheckResult = Granted
Test-ApplicationAccessPolicy -Identity dsertic@seda.de     -AppId <Anwendungs-ID>   # erwartet: AccessCheckResult = Denied
Disconnect-ExchangeOnline
```

> **Hinweis:** Microsoft empfiehlt inzwischen als Nachfolger „RBAC für Anwendungen“ in Exchange Online. Die Application Access Policy funktioniert weiterhin und ist für einen einzelnen Absender der einfachere Weg. Bei einem späteren Umstieg schreibe ich die Befehle dafür.

## 6. Im Cockpit eintragen

1. Öffne **Cockpit › Monatsabschluss › Schritt 5 „Versenden & sperren“ › „Microsoft-Zugang eintragen“**.
2. Trag die drei Werte ein. Die Felder sind verdeckt, und nichts wird je wieder angezeigt:
   - **Verzeichnis-ID (Mandant)** (Schritt 1)
   - **Anwendungs-ID (Client)** (Schritt 1)
   - **Geheimer Clientschlüssel – Wert** (Schritt 4)
3. Klicke **Speichern**, dann **Verbindung testen (ohne Mail)**. Erwartet: „Anmeldung bei Microsoft erfolgreich …“.
4. Der **erste echte Testversand** geht nur an dich (Testmodus „alles an die Test-Adresse“), und erst nach deinem ausdrücklichen OK.
5. Prüfe danach in Outlook: Liegt die Mail in „Gesendete Elemente“ von buchhaltung@seda.de?

Gespeichert wird nur auf dem Server, in `backend/secrets/` (nur für den Server-Benutzer lesbar, nicht im Git). Im Änderungsprotokoll steht nur, *dass* der Zugang eingetragen wurde, ohne die Werte.

**Wenn etwas nicht klappt:**

| Meldung | Ursache |
|---|---|
| HTTP 401 | Geheimnis falsch, abgelaufen oder die „Geheimnis-ID“ statt des Werts eingetragen |
| HTTP 403 „Access is denied“ | Administratorzustimmung fehlt (Schritt 2), oder die Beschränkung (Schritt 5) wirkt noch nicht bzw. buchhaltung@ ist nicht in der Gruppe |
