<#
SEDA24 - Lohnabrechnungen aus Lexware automatisch an den Monatsabschluss im Cockpit uebergeben (Drazen 19.11.2026)

Ueberwacht den Lexware-Ausgabeordner
  X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung\
(aktueller Monat und Vormonat) und laedt jede neue oder geaenderte Lohnabrechnung_*.pdf per HTTPS hoch.
- Gleicher Export-Schluessel wie der Zeiterfassungs-Export (schluessel.dat in %LOCALAPPDATA%\SEDA24-Export,
  nur fuer diesen Windows-Benutzer lesbar). Ist der Export schon eingerichtet, wird nichts neu abgefragt.
- Pruefsumme (SHA-256) geht mit; der Server prueft sie, speichert verschluesselt, ordnet nach PersNr/Name zu und
  schickt eine Quittung zurueck (steht im Protokoll). Was der Server schon hat, wird nicht noch einmal geschickt.
- Eine Datei wird erst hochgeladen, wenn sie 1 Minute nicht mehr veraendert wurde (Lexware schreibt fertig).
- Windows-Aufgabe "SEDA24 Lohnabrechnungen Upload": vom 1. bis 15. jedes Monats stuendlich 07-22 Uhr, an allen
  anderen Tagen einmal um 12 Uhr (Lebenszeichen); verpasste Laeufe werden nachgeholt, und 2 Minuten nach der
  Anmeldung (Drazen 26.11.2026 07:45). Start ohne Fenster (conhost.exe --headless; geht das nicht, PowerShell versteckt).
- Jeder Lauf meldet sich beim Server (Lebenszeichen, Anzeige im Monatsabschluss Schritt 3). Faellt eine Datei durch,
  laufen die anderen weiter; Fehler gehen gesammelt an den Server (Telegram, gleicher Fehler hoechstens 1x in 6 Std.).
  Ist der Server nicht erreichbar, erscheint hoechstens einmal am Tag ein Hinweisfenster (Drazen 26.11.2026).

Einrichten (einmalig, als der Benutzer mit Laufwerk X: - keine Admin-Rechte noetig):
  powershell -ExecutionPolicy Bypass -File "<Pfad>\seda24_lohn_upload.ps1" -Install
  Test gegen DEV:  ... -Install -Server https://dev.seda.de
  Lexware-Ordner:  ... -Install -Basis "X:\...\Lohnabrechnungen"   (sucht Seda_Consulting_GmbH_{Jahr}_{Monatsname}\Lohnabrechnung,
                   Vormonat und laufender Monat, Maerz auch mit Umlaut)
  Anderer Ordner:  ... -Install -Ordner "X:\...\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung"
  Testlauf:        ... -Install -Server https://dev.seda.de -Ordner "X:\...\TEST_Lohnabrechnung" -Monat 2026-10
                   (fester Ordner ohne {Jahr}/{Monat}, alles zaehlt fuer den angegebenen Monat)
  Andere Dateinamen: ... -Filter "*.pdf"
Sofort pruefen und hochladen:
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt
Entfernen (Export-Schluessel bleibt fuer den Zeiterfassungs-Export):
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Uninstall
Protokoll: %LOCALAPPDATA%\SEDA24-Export\lohn_upload.log
#>
param([switch]$Install, [switch]$Uninstall, [switch]$Jetzt, [string]$Server = '', [string]$Basis = '', [string]$Ordner = '', [string]$Monat = '', [string]$Filter = '')

$MonatGesetzt = $PSBoundParameters.ContainsKey('Monat')   # -Monat '' = festen Monat wieder entfernen
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$AppDir    = Join-Path $env:LOCALAPPDATA 'SEDA24-Export'
$KeyFile   = Join-Path $AppDir 'schluessel.dat'           # gemeinsam mit seda24_export_abruf.ps1
$CfgFile   = Join-Path $AppDir 'lohn_upload.cfg'          # Server <TAB> Ordner-Muster <TAB> fester Monat <TAB> Dateifilter
$LogFile   = Join-Path $AppDir 'lohn_upload.log'
$StandFile = Join-Path $AppDir 'lohn_upload_stand.txt'    # je Datei: Pfad <TAB> SHA-256 der hochgeladenen Version
$HinweisFile = Join-Path $AppDir 'lohn_upload_hinweis.txt'   # Datum des letzten Hinweisfensters (hoechstens 1x am Tag)
$TaskName  = 'SEDA24 Lohnabrechnungen Upload'
$Version   = '2026-11-26b'
$StandardOrdner = 'X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung'
$UnterOrdner = 'Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung'   # unter -Basis (Ordner wie bei Lexware: ..._2026_Oktober)
# Datei bleibt ASCII (PowerShell 5.1 liest .ps1 ohne BOM als ANSI): Umlaut als Zeichencode
$MonatsNamen = @('', 'Januar', 'Februar', ('M' + [char]0x00E4 + 'rz'), 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

function Write-Log([string]$Text) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Text
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-ExportKey {
    $sec = Get-Content -Path $KeyFile | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-Cfg {
    $c = @{ Server = 'https://app.seda.de'; Ordner = $StandardOrdner; Monat = ''; Filter = 'Lohnabrechnung_*.pdf' }
    if (Test-Path -LiteralPath $CfgFile) {
        $t = (Get-Content -LiteralPath $CfgFile -Encoding UTF8 | Select-Object -First 1) -split "`t"
        if ($t.Count -ge 2) { $c.Server = $t[0]; $c.Ordner = $t[1] }
        if ($t.Count -ge 4) { $c.Monat = $t[2]; if ($t[3]) { $c.Filter = $t[3] } }
    }
    $c
}

function Get-Stand {
    $s = @{}
    if (Test-Path -LiteralPath $StandFile) {
        foreach ($z in Get-Content -LiteralPath $StandFile -Encoding UTF8) {
            $t = $z -split "`t"
            if ($t.Count -eq 2) { $s[$t[0]] = $t[1] }
        }
    }
    $s
}

function Save-Stand($S) {
    $S.Keys | Sort-Object | ForEach-Object { "$_`t$($S[$_])" } | Set-Content -LiteralPath $StandFile -Encoding UTF8
}

function Send-Json([string]$Uri, $Daten) {
    $body = $Daten | ConvertTo-Json -Depth 4
    Invoke-RestMethod -Method Post -Uri $Uri -Headers @{ 'X-Export-Key' = (Get-ExportKey); 'X-Rechner' = $env:COMPUTERNAME } `
        -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 30 | Out-Null
}

# Fehler an den Server (Telegram, dort entprellt). Server nicht erreichbar -> Hinweisfenster, hoechstens einmal am Tag.
function Send-Fehler([string]$Text, $Cfg) {
    Write-Log "FEHLER: $Text"
    try {
        try { Send-Json "$($Cfg.Server)/api/v1/export/lohn-pc/fehler" @{ text = $Text; rechner = $env:COMPUTERNAME } }
        catch {
            if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) {   # Server noch ohne lohn-pc
                Send-Json "$($Cfg.Server)/api/v1/export/zeiterfassung/fehler" @{ text = "Lohnabrechnung-Upload: $Text"; rechner = $env:COMPUTERNAME }
            } else { throw }
        }
    } catch {
        Write-Log "Server nicht erreichbar fuer die Fehlermeldung: $($_.Exception.Message)"
        $heute = (Get-Date).ToString('yyyy-MM-dd')
        $zuletzt = if (Test-Path -LiteralPath $HinweisFile) { (Get-Content -LiteralPath $HinweisFile | Select-Object -First 1) } else { '' }
        if ($zuletzt -eq $heute) { Write-Log 'Hinweisfenster heute schon gezeigt'; return }
        Set-Content -LiteralPath $HinweisFile -Value $heute
        $msg = "SEDA24 Lohnabrechnungen konnten nicht hochgeladen werden:`n`n$Text`n`nProtokoll: $LogFile`n`n(Dieser Hinweis kommt hoechstens einmal am Tag.)"
        (New-Object -ComObject WScript.Shell).Popup($msg, 3000, 'SEDA24 Lohnabrechnungen', 48) | Out-Null
    }
}

function ConvertTo-Vergleich([string]$T) {
    $T.Normalize([Text.NormalizationForm]::FormC).ToLowerInvariant()
}

# Schreibweisen eines Monats im Ordner-/Dateinamen: 10, 1, Oktober; Maerz auch als Maerz/Marz
function Get-MonatsVarianten([int]$M) {
    $v = @($M.ToString('00'), "$M", $MonatsNamen[$M])
    if ($M -eq 3) { $v += @('Maerz', 'Marz') }
    $v
}

# Ordner eines Monats: {Jahr} und {Monat} (zweistellig, einstellig oder Monatsname - was es gibt).
# Pfadteile mit Platzhalter werden mit den vorhandenen Unterordnern verglichen (Unicode-normalisiert, ohne
# Gross/Klein), damit Maerz mit Umlaut auch bei anderer Kodierung (OneDrive/Mac: a + Trema) gefunden wird.
function Get-MonatsOrdner($Muster, [datetime]$Tag) {
    foreach ($mo in (Get-MonatsVarianten $Tag.Month)) {
        $p = $Muster.Replace('{Jahr}', $Tag.ToString('yyyy')).Replace('{Monat}', $mo)
        if (Test-Path -LiteralPath $p) { return $p }
        $teile = [regex]::Split($p, '[\\/]')
        $pfad = $teile[0] + [IO.Path]::DirectorySeparatorChar   # X:\ (bzw. / beim Test unter Linux)
        for ($i = 1; $i -lt $teile.Count -and $pfad; $i++) {
            $direkt = Join-Path $pfad $teile[$i]
            if (Test-Path -LiteralPath $direkt) { $pfad = $direkt; continue }
            $soll = ConvertTo-Vergleich $teile[$i]
            $treffer = @(Get-ChildItem -LiteralPath $pfad -Directory -ErrorAction SilentlyContinue | Where-Object { (ConvertTo-Vergleich $_.Name) -eq $soll })
            $pfad = if ($treffer.Count) { $treffer[0].FullName } else { $null }
        }
        if ($pfad) { return $pfad }
    }
    $null
}

# Monat aus dem Dateinamen (Lohnabrechnung_2026_Oktober_D0039_... oder _2026_10_), sonst $null
function Get-DateiMonat([string]$Name) {
    $n = ConvertTo-Vergleich $Name
    if ($n -notmatch '_(\d{4})_([^_]+)_') { return $null }
    $j = [int]$Matches[1]; $mo = $Matches[2]
    for ($m = 1; $m -le 12; $m++) {
        if ((Get-MonatsVarianten $m | ForEach-Object { ConvertTo-Vergleich $_ }) -contains $mo) { return ('{0:0000}-{1:00}' -f $j, $m) }
    }
    $null
}

function Invoke-Upload {
    $cfg = Get-Cfg
    $key = Get-ExportKey
    $stand = Get-Stand
    $erster = (Get-Date -Day 1).Date
    $neu = 0
    $fehler = @()
    $tage = if ($cfg.Monat) { @([datetime]::ParseExact($cfg.Monat + '-01', 'yyyy-MM-dd', $null)) } else { @($erster.AddMonths(-1), $erster) }
    $liste = @()
    $gesehen = [ordered]@{}
    foreach ($tag in $tage) {
        $monat = $tag.ToString('yyyy-MM')
        $ordner = Get-MonatsOrdner $cfg.Ordner $tag
        if (-not $ordner) { $gesehen[$monat] = 'Ordner fehlt'; continue }
        $dateien = @(Get-ChildItem -LiteralPath $ordner -Filter $cfg.Filter -File)
        $gesehen[$monat] = "$($dateien.Count) Dateien"
        if ($dateien.Count) { $liste += , @($monat, $dateien) }
    }
    # Lebenszeichen bei jedem Lauf, auch wenn es nichts hochzuladen gibt (Server nicht erreichbar -> Fehler unten)
    try { Send-Json "$($cfg.Server)/api/v1/export/lohn-pc/lebenszeichen" @{ rechner = $env:COMPUTERNAME; version = $Version; ordner = $gesehen } }
    catch { if (-not ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404)) { throw } }   # Server noch ohne lohn-pc
    foreach ($eintrag in $liste) {
        $monat = $eintrag[0]; $dateien = $eintrag[1]
        $url = "$($cfg.Server)/api/v1/export/lohnabrechnungen/$monat"
        try { $srv = Invoke-RestMethod -Uri $url -Headers @{ 'X-Export-Key' = $key; 'X-Rechner' = $env:COMPUTERNAME } -TimeoutSec 60 }
        catch { $fehler += "Stand $monat`: $($_.Exception.Message)"; continue }
        if ($srv.gesperrt) { continue }   # Monat abgeschlossen: nichts mehr hochladen
        $neuMonat = 0
        foreach ($f in $dateien) {
            if ($f.LastWriteTime -gt (Get-Date).AddMinutes(-1)) { Write-Log "$($f.Name): wird noch geschrieben, spaeter"; continue }
            $dm = Get-DateiMonat $f.Name
            if ($dm -and $dm -ne $monat) { if ($Jetzt) { Write-Log "$($f.Name): Dateiname sagt $dm, Ordner $monat - uebersprungen" }; continue }
            try {   # eine Datei faellt durch -> die anderen laufen weiter, Fehler gesammelt am Ende
                $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
                if ($stand[$f.FullName] -eq $sha -or @($srv.sha256) -contains $sha) { $stand[$f.FullName] = $sha; continue }
                $h = @{ 'X-Export-Key' = $key; 'X-Dateiname' = [uri]::EscapeDataString($f.Name); 'X-SHA256' = $sha; 'X-Rechner' = $env:COMPUTERNAME }
                $r = Invoke-RestMethod -Method Post -Uri $url -Headers $h -InFile $f.FullName -ContentType 'application/pdf' -TimeoutSec 120
                if ($r.quittung.sha256 -ne $sha) { throw "Quittung passt nicht" }
                $wer = (@($r.quittung.teile) | ForEach-Object { if ($_.name) { $_.name } else { 'NICHT ZUGEORDNET' } }) -join ', '
                Write-Log "hochgeladen $monat`: $($f.Name) ($($r.quittung.status)) -> $wer"
                $stand[$f.FullName] = $sha
                Save-Stand $stand
                $neu++; $neuMonat++
                $srv = @{ sha256 = @($srv.sha256) + $sha; erwartet = $r.stand.erwartet; da = $r.stand.da; nicht_zugeordnet = $r.stand.nicht_zugeordnet }
            } catch {
                $fehler += "$($f.Name): $($_.Exception.Message)"
                Write-Log "FEHLER $($f.Name): $($_.Exception.Message) - naechster Lauf versucht es wieder"
            }
        }
        if ($neuMonat) { Write-Log "Stand $monat`: $($srv.da) von $($srv.erwartet) Lohnabrechnungen da, $($srv.nicht_zugeordnet) ohne Zuordnung" }
    }
    Save-Stand $stand
    if ($Jetzt -and -not $neu -and -not $fehler.Count) { Write-Log 'nichts Neues' }
    if ($fehler.Count) {
        $text = "nicht alles hochgeladen ($($fehler.Count) Fehler): " + (($fehler | Select-Object -First 5) -join ' | ')
        if ($fehler.Count -gt 5) { $text += " | ... und $($fehler.Count - 5) weitere" }
        Send-Fehler $text $cfg
    }
}

# Start ohne Fenster: conhost.exe --headless (Windows 10 ab 2019 / Windows 11). Einmal ausprobieren, sonst PowerShell versteckt.
function Test-Headless {
    if (-not $env:SystemRoot) { return $null }
    $conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
    if (-not (Test-Path -LiteralPath $conhost)) { return $null }
    $probe = Join-Path $AppDir 'headless_test.txt'
    Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    $cmd = "Set-Content -LiteralPath '$($probe.Replace("'", "''"))' -Value ok"
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
    try { Start-Process -FilePath $conhost -ArgumentList "--headless powershell.exe -NoProfile -EncodedCommand $enc" -WindowStyle Hidden | Out-Null }
    catch { return $null }
    for ($i = 0; $i -lt 30 -and -not (Test-Path -LiteralPath $probe); $i++) { Start-Sleep -Milliseconds 500 }
    $ok = Test-Path -LiteralPath $probe
    Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
    if ($ok) { $conhost } else { $null }
}

function Install-Aufgabe {
    $script = Join-Path $AppDir 'seda24_lohn_upload.ps1'
    if ($PSCommandPath -ne $script) { Copy-Item -LiteralPath $PSCommandPath -Destination $script -Force }
    $cfg = Get-Cfg
    if ($Server) { $cfg.Server = $Server.TrimEnd('/') }
    if ($Basis) {
        $cfg.Ordner = (Join-Path $Basis.TrimEnd('\') $UnterOrdner)
        if (-not $MonatGesetzt) { $cfg.Monat = '' }   # -Basis: immer Vormonat und laufender Monat
    }
    if ($Ordner) { $cfg.Ordner = $Ordner.TrimEnd('\') }
    if ($MonatGesetzt) { $cfg.Monat = $Monat }
    if ($Filter) { $cfg.Filter = $Filter }
    if ($cfg.Monat -and $cfg.Monat -notmatch '^\d{4}-(0[1-9]|1[0-2])$') { throw "-Monat als JJJJ-MM angeben" }
    if (-not $cfg.Monat -and $cfg.Ordner -notmatch '\{Monat\}') { throw "Ordner ohne {Jahr}/{Monat}: bitte -Monat JJJJ-MM angeben" }
    "$($cfg.Server)`t$($cfg.Ordner)`t$($cfg.Monat)`t$($cfg.Filter)" | Set-Content -LiteralPath $CfgFile -Encoding UTF8
    if (-not (Test-Path -LiteralPath $KeyFile)) {
        $sec = Read-Host 'Export-Schluessel einfuegen (wird nicht angezeigt), dann Enter' -AsSecureString
        $sec | ConvertFrom-SecureString | Set-Content -Path $KeyFile
    }
    Write-Log "Ordner: $($cfg.Ordner)$(if ($cfg.Monat) { "  (fester Monat $($cfg.Monat))" })  Dateien: $($cfg.Filter)"
    $erster = (Get-Date -Day 1).Date
    $tage = if ($cfg.Monat) { @([datetime]::ParseExact($cfg.Monat + '-01', 'yyyy-MM-dd', $null)) } else { @($erster.AddMonths(-1), $erster) }
    foreach ($tag in $tage) {
        $monat = $tag.ToString('yyyy-MM')
        $st = Invoke-RestMethod -Uri "$($cfg.Server)/api/v1/export/lohnabrechnungen/$monat" -Headers @{ 'X-Export-Key' = (Get-ExportKey); 'X-Rechner' = $env:COMPUTERNAME } -TimeoutSec 60
        $o = Get-MonatsOrdner $cfg.Ordner $tag
        Write-Log "Server $($cfg.Server) erreichbar, Schluessel ok ($monat`: $($st.da) von $($st.erwartet) da)  Ordner: $(if ($o) { $o } else { 'noch nicht vorhanden' })"
    }
    $user = [Security.SecurityElement]::Escape([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $ps = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
    $conhost = Test-Headless
    if ($conhost) { $cmd = $conhost; $arg = "--headless powershell.exe $ps"; $wie = 'ohne Fenster (conhost --headless)' }
    else { $cmd = 'powershell.exe'; $arg = $ps; $wie = 'PowerShell versteckt (conhost --headless geht hier nicht, kurzes Aufblitzen moeglich)' }
    $cmd = [Security.SecurityElement]::Escape($cmd)
    $arg = [Security.SecurityElement]::Escape($arg)
    $tage = -join (1..15 | ForEach-Object { "<Day>$_</Day>" })
    $monate = -join ('January','February','March','April','May','June','July','August','September','October','November','December' | ForEach-Object { "<$_ />" })
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Laedt neue Lohnabrechnungen aus dem Lexware-Ausgabeordner an den SEDA24-Monatsabschluss hoch (1.-15. stuendlich 07-22 Uhr, sonst taeglich 12 Uhr, verpasste Laeufe nachholen, und nach der Anmeldung).</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition><Interval>PT1H</Interval><Duration>PT15H1M</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-11-01T07:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth><DaysOfMonth>$tage</DaysOfMonth><Months>$monate</Months></ScheduleByMonth>
    </CalendarTrigger>
    <CalendarTrigger>
      <StartBoundary>2026-11-01T12:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$user</UserId>
      <Delay>PT2M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$cmd</Command>
      <Arguments>$arg</Arguments>
    </Exec>
  </Actions>
</Task>
"@
    Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
    Write-Log "Aufgabe '$TaskName' eingerichtet (1.-15. stuendlich 07-22 Uhr, sonst taeglich 12 Uhr, verpasste Laeufe nachholen, 2 Min nach Anmeldung), Start $wie"
}

try {
    if ($Uninstall) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $CfgFile, $StandFile, $HinweisFile -Force -ErrorAction SilentlyContinue
        Write-Log "Aufgabe '$TaskName' entfernt (Export-Schluessel bleibt)"
        return
    }
    if ($Install) { Install-Aufgabe; $Jetzt = $true }
    if (-not (Test-Path -LiteralPath $KeyFile)) { throw 'Nicht eingerichtet - zuerst mit -Install starten' }
    Invoke-Upload
} catch {
    if (Test-Path -LiteralPath $KeyFile) { Send-Fehler $_.Exception.Message (Get-Cfg) }
    else { Write-Log "FEHLER: $($_.Exception.Message)" }
    exit 1
}
