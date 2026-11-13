<#
SEDA24 Zeiterfassung - monatlicher Export fuer die Buchhaltung nach
  Q:\03_Auswertungen\Kennzahlen\Rohdaten\Zeiterfassung\

Der Server erzeugt am 1. um 03:00 zeiterfassung_JJJJ-MM.csv (Vormonat) und objekte_kunden.csv.
Dieses Skript holt sie per HTTPS ab (eigener Export-Schluessel, gilt nur fuer diese Dateien).
Die Windows-Aufgabe "SEDA24 Zeiterfassung Export" startet es am 1. um 06:00 und zusaetzlich
10 Minuten nach jeder Anmeldung (holt einen verpassten Lauf nach, wenn der PC aus war).
Ist die Datei des Vormonats schon in Q:, endet es sofort ohne Serverzugriff.
Bei Fehlern: Telegram-Meldung ueber den Server; ist der Server nicht erreichbar, ein Hinweisfenster.

Einrichten (einmalig, als der Benutzer, der Q: verbunden hat - keine Admin-Rechte noetig):
  powershell -ExecutionPolicy Bypass -File "<Pfad>\seda24_export_abruf.ps1" -Install
Sofort abrufen (auch geaenderte Dateien):
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_export_abruf.ps1" -Jetzt
Entfernen:
  powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\SEDA24-Export\seda24_export_abruf.ps1" -Uninstall
Protokoll: %LOCALAPPDATA%\SEDA24-Export\abruf.log
#>
param([switch]$Install, [switch]$Uninstall, [switch]$Jetzt)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Fortschrittsbalken bremst Invoke-WebRequest stark
$Base     = 'https://app.seda.de/api/v1/export/zeiterfassung'
$Ziel     = 'Q:\03_Auswertungen\Kennzahlen\Rohdaten\Zeiterfassung'
$AppDir   = Join-Path $env:LOCALAPPDATA 'SEDA24-Export'
$KeyFile  = Join-Path $AppDir 'schluessel.dat'
$LogFile  = Join-Path $AppDir 'abruf.log'
$TaskName = 'SEDA24 Zeiterfassung Export'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

function Write-Log([string]$Text) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Text
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

# Schluessel liegt nur verschluesselt (Windows-DPAPI, nur dieser Benutzer auf diesem PC) in schluessel.dat
function Get-ExportKey {
    $sec = Get-Content -Path $KeyFile | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Send-Fehler([string]$Text) {
    Write-Log "FEHLER: $Text"
    try {
        $body = @{ text = $Text; rechner = $env:COMPUTERNAME } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$Base/fehler" -Headers @{ 'X-Export-Key' = (Get-ExportKey) } `
            -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
            -TimeoutSec 30 | Out-Null
        Write-Log 'Fehler per Telegram gemeldet'
    } catch {
        Write-Log "Telegram-Meldung nicht moeglich: $($_.Exception.Message)"
        $msg = "SEDA24 Zeiterfassungs-Export nach Q: fehlgeschlagen:`n`n$Text`n`nProtokoll: $LogFile"
        (New-Object -ComObject WScript.Shell).Popup($msg, 0, 'SEDA24 Export', 48) | Out-Null
    }
}

function Get-Liste([string]$Key) {
    Invoke-RestMethod -Uri $Base -Headers @{ 'X-Export-Key' = $Key } -TimeoutSec 60
}

function Invoke-Abruf {
    $vormonat = (Get-Date -Day 1).AddMonths(-1).ToString('yyyy-MM')
    $soll = "zeiterfassung_$vormonat.csv"
    if (-not (Test-Path -LiteralPath $Ziel)) {
        if (-not (Test-Path -LiteralPath 'Q:\')) { throw "Laufwerk Q: nicht verbunden ($Ziel nicht erreichbar)" }
        New-Item -ItemType Directory -Force -Path $Ziel | Out-Null
        Write-Log "Zielordner angelegt: $Ziel"
    }
    if ((Test-Path -LiteralPath (Join-Path $Ziel $soll)) -and -not $Jetzt) {
        Write-Log "$soll ist schon in Q:, nichts zu tun"
        return
    }
    $key = Get-ExportKey
    $liste = Get-Liste $key
    if (-not ($liste.files | Where-Object { $_.name -eq $soll })) {
        $jetzt = Get-Date
        if ($jetzt.Day -eq 1 -and $jetzt.Hour -lt 6) { Write-Log "$soll wird erst um 03:00 erzeugt, spaeter erneut"; return }
        throw "$soll liegt auf dem Server nicht vor (Export am 1. um 03:00 gelaufen?)"
    }
    $neu = 0
    foreach ($f in $liste.files) {
        $dst = Join-Path $Ziel $f.name
        if ((Test-Path -LiteralPath $dst) -and ((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -eq $f.sha256)) { continue }
        $tmp = Join-Path $AppDir ($f.name + '.tmp')
        Invoke-WebRequest -UseBasicParsing -Uri "$Base/$($f.name)" -Headers @{ 'X-Export-Key' = $key } -OutFile $tmp -TimeoutSec 120
        if ((Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash -ne $f.sha256) {
            Remove-Item -LiteralPath $tmp -Force
            throw "Pruefsumme stimmt nicht: $($f.name)"
        }
        Copy-Item -LiteralPath $tmp -Destination $dst -Force
        Remove-Item -LiteralPath $tmp -Force
        Write-Log "geholt: $($f.name) ($($f.size) Bytes)"
        $neu++
    }
    Write-Log "fertig: $neu Datei(en) neu oder aktualisiert in $Ziel"
}

function Install-Aufgabe {
    $script = Join-Path $AppDir 'seda24_export_abruf.ps1'
    if ($PSCommandPath -ne $script) { Copy-Item -LiteralPath $PSCommandPath -Destination $script -Force }
    $sec = Read-Host 'Export-Schluessel einfuegen (wird nicht angezeigt), dann Enter' -AsSecureString
    $sec | ConvertFrom-SecureString | Set-Content -Path $KeyFile
    try {
        $n = @((Get-Liste (Get-ExportKey)).files).Count
        Write-Log "Schluessel geprueft: $n Datei(en) auf dem Server"
    } catch {
        Remove-Item -LiteralPath $KeyFile -Force
        throw "Server lehnt ab oder ist nicht erreichbar - Schluessel nicht gespeichert: $($_.Exception.Message)"
    }
    $user = [Security.SecurityElement]::Escape([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    $arg = [Security.SecurityElement]::Escape("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"")
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Holt am 1. den Zeiterfassungs-Export des Vormonats von app.seda.de nach Q: (Buchhaltung). Nach Anmeldung wird ein verpasster Lauf nachgeholt.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-11-01T06:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>1</Day></DaysOfMonth>
        <Months><January /><February /><March /><April /><May /><June /><July /><August /><September /><October /><November /><December /></Months>
      </ScheduleByMonth>
    </CalendarTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$user</UserId>
      <Delay>PT10M</Delay>
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
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
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
    Write-Log "Aufgabe '$TaskName' eingerichtet (am 1. um 06:00 und 10 Min nach Anmeldung)"
}

try {
    if ($Uninstall) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $KeyFile -Force -ErrorAction SilentlyContinue
        Write-Log "Aufgabe '$TaskName' und Schluessel entfernt"
        return
    }
    if ($Install) {
        Install-Aufgabe
        $Jetzt = $true   # erster Lauf: alle vorhandenen Monate holen
    }
    if (-not (Test-Path -LiteralPath $KeyFile)) { throw 'Nicht eingerichtet - zuerst mit -Install starten' }
    Invoke-Abruf
} catch {
    if (Test-Path -LiteralPath $KeyFile) { Send-Fehler $_.Exception.Message }
    else { Write-Log "FEHLER: $($_.Exception.Message)" }
    exit 1
}
