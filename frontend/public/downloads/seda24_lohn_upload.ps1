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
- Windows-Aufgabe "SEDA24 Lohnabrechnungen Upload": alle 10 Minuten und 2 Minuten nach der Anmeldung.

Einrichten (einmalig, als der Benutzer mit Laufwerk X: - keine Admin-Rechte noetig):
  powershell -ExecutionPolicy Bypass -File "<Pfad>\seda24_lohn_upload.ps1" -Install
  Test gegen DEV:  ... -Install -Server https://dev.seda.de
  Anderer Ordner:  ... -Install -Ordner "X:\...\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung"
Sofort pruefen und hochladen:
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Jetzt
Entfernen (Export-Schluessel bleibt fuer den Zeiterfassungs-Export):
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_lohn_upload.ps1" -Uninstall
Protokoll: %LOCALAPPDATA%\SEDA24-Export\lohn_upload.log
#>
param([switch]$Install, [switch]$Uninstall, [switch]$Jetzt, [string]$Server = '', [string]$Ordner = '')

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$AppDir    = Join-Path $env:LOCALAPPDATA 'SEDA24-Export'
$KeyFile   = Join-Path $AppDir 'schluessel.dat'           # gemeinsam mit seda24_export_abruf.ps1
$CfgFile   = Join-Path $AppDir 'lohn_upload.cfg'          # Server <TAB> Ordner-Muster
$LogFile   = Join-Path $AppDir 'lohn_upload.log'
$StandFile = Join-Path $AppDir 'lohn_upload_stand.txt'    # je Datei: Pfad <TAB> SHA-256 der hochgeladenen Version
$TaskName  = 'SEDA24 Lohnabrechnungen Upload'
$StandardOrdner = 'X:\OneDrive - Seda GmbH\4 Buchhaltung\2 Lohnbuchhaltung\Lohnabrechnungen\Seda_Consulting_GmbH_{Jahr}_{Monat}\Lohnabrechnung'
$MonatsNamen = @('', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')
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
    $c = @{ Server = 'https://app.seda.de'; Ordner = $StandardOrdner }
    if (Test-Path -LiteralPath $CfgFile) {
        $t = (Get-Content -LiteralPath $CfgFile -Encoding UTF8 | Select-Object -First 1) -split "`t"
        if ($t.Count -eq 2) { $c.Server = $t[0]; $c.Ordner = $t[1] }
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

function Send-Fehler([string]$Text, $Cfg) {
    Write-Log "FEHLER: $Text"
    try {
        $body = @{ text = "Lohnabrechnung-Upload: $Text"; rechner = $env:COMPUTERNAME } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$($Cfg.Server)/api/v1/export/zeiterfassung/fehler" -Headers @{ 'X-Export-Key' = (Get-ExportKey) } `
            -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 30 | Out-Null
    } catch {
        $msg = "SEDA24 Lohnabrechnungen konnten nicht hochgeladen werden:`n`n$Text`n`nProtokoll: $LogFile"
        (New-Object -ComObject WScript.Shell).Popup($msg, 0, 'SEDA24 Lohnabrechnungen', 48) | Out-Null
    }
}

# Ordner eines Monats: {Jahr} und {Monat} (zweistellig, einstellig oder Monatsname - was es gibt)
function Get-MonatsOrdner($Muster, [datetime]$Tag) {
    foreach ($mo in @($Tag.ToString('MM'), "$($Tag.Month)", $MonatsNamen[$Tag.Month])) {
        $p = $Muster.Replace('{Jahr}', $Tag.ToString('yyyy')).Replace('{Monat}', $mo)
        if (Test-Path -LiteralPath $p) { return $p }
    }
    $null
}

function Invoke-Upload {
    $cfg = Get-Cfg
    $key = Get-ExportKey
    $stand = Get-Stand
    $erster = (Get-Date -Day 1).Date
    $neu = 0
    foreach ($tag in @($erster.AddMonths(-1), $erster)) {
        $monat = $tag.ToString('yyyy-MM')
        $ordner = Get-MonatsOrdner $cfg.Ordner $tag
        if (-not $ordner) { continue }
        $dateien = @(Get-ChildItem -LiteralPath $ordner -Filter 'Lohnabrechnung_*.pdf' -File)
        if (-not $dateien.Count) { continue }
        $url = "$($cfg.Server)/api/v1/export/lohnabrechnungen/$monat"
        $srv = Invoke-RestMethod -Uri $url -Headers @{ 'X-Export-Key' = $key } -TimeoutSec 60
        if ($srv.gesperrt) { continue }   # Monat abgeschlossen: nichts mehr hochladen
        foreach ($f in $dateien) {
            if ($f.LastWriteTime -gt (Get-Date).AddMinutes(-1)) { Write-Log "$($f.Name): wird noch geschrieben, spaeter"; continue }
            $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
            if ($stand[$f.FullName] -eq $sha -or @($srv.sha256) -contains $sha) { $stand[$f.FullName] = $sha; continue }
            $h = @{ 'X-Export-Key' = $key; 'X-Dateiname' = [uri]::EscapeDataString($f.Name); 'X-SHA256' = $sha; 'X-Rechner' = $env:COMPUTERNAME }
            $r = Invoke-RestMethod -Method Post -Uri $url -Headers $h -InFile $f.FullName -ContentType 'application/pdf' -TimeoutSec 120
            if ($r.quittung.sha256 -ne $sha) { throw "Quittung passt nicht zu $($f.Name)" }
            $wer = (@($r.quittung.teile) | ForEach-Object { if ($_.name) { $_.name } else { 'NICHT ZUGEORDNET' } }) -join ', '
            Write-Log "hochgeladen $monat`: $($f.Name) ($($r.quittung.status)) -> $wer"
            $stand[$f.FullName] = $sha
            Save-Stand $stand
            $neu++
            $srv = @{ sha256 = @($srv.sha256) + $sha; erwartet = $r.stand.erwartet; da = $r.stand.da; nicht_zugeordnet = $r.stand.nicht_zugeordnet }
        }
        if ($neu) { Write-Log "Stand $monat`: $($srv.da) von $($srv.erwartet) Lohnabrechnungen da, $($srv.nicht_zugeordnet) ohne Zuordnung" }
    }
    Save-Stand $stand
    if ($Jetzt -and -not $neu) { Write-Log 'nichts Neues' }
}

function Install-Aufgabe {
    $script = Join-Path $AppDir 'seda24_lohn_upload.ps1'
    if ($PSCommandPath -ne $script) { Copy-Item -LiteralPath $PSCommandPath -Destination $script -Force }
    $cfg = Get-Cfg
    if ($Server) { $cfg.Server = $Server.TrimEnd('/') }
    if ($Ordner) { $cfg.Ordner = $Ordner.TrimEnd('\') }
    "$($cfg.Server)`t$($cfg.Ordner)" | Set-Content -LiteralPath $CfgFile -Encoding UTF8
    if (-not (Test-Path -LiteralPath $KeyFile)) {
        $sec = Read-Host 'Export-Schluessel einfuegen (wird nicht angezeigt), dann Enter' -AsSecureString
        $sec | ConvertFrom-SecureString | Set-Content -Path $KeyFile
    }
    $monat = (Get-Date).ToString('yyyy-MM')
    $st = Invoke-RestMethod -Uri "$($cfg.Server)/api/v1/export/lohnabrechnungen/$monat" -Headers @{ 'X-Export-Key' = (Get-ExportKey) } -TimeoutSec 60
    Write-Log "Server $($cfg.Server) erreichbar, Schluessel ok ($monat`: $($st.da) von $($st.erwartet) da)"
    Write-Log "Ordner-Muster: $($cfg.Ordner)"
    $user = [Security.SecurityElement]::Escape([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $arg = [Security.SecurityElement]::Escape("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"")
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Laedt neue Lohnabrechnungen aus dem Lexware-Ausgabeordner an den SEDA24-Monatsabschluss hoch (alle 10 Minuten und nach der Anmeldung).</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2026-11-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
    </TimeTrigger>
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
      <Command>powershell.exe</Command>
      <Arguments>$arg</Arguments>
    </Exec>
  </Actions>
</Task>
"@
    Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
    Write-Log "Aufgabe '$TaskName' eingerichtet (alle 10 Minuten und 2 Min nach Anmeldung)"
}

try {
    if ($Uninstall) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $CfgFile, $StandFile -Force -ErrorAction SilentlyContinue
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
