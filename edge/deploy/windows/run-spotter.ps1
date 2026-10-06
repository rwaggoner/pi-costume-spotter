<#
.SYNOPSIS
    Runs the Costume Spotter and restarts it if it crashes - the Windows
    counterpart of the systemd unit's Restart=on-failure / RestartSec=5.

.DESCRIPTION
    Started at login by the scheduled task from install-autostart.ps1 (hidden
    window). Each run logs to its own file, edge\data\logs\spotter-<time>.log
    (the app logs to stderr), and the newest 20 runs are kept - the Windows
    stand-in for `journalctl -u costume-spotter`. A clean exit (code 0) stops
    the loop; a crash waits 5 s and starts again.
#>
$ErrorActionPreference = "Continue"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $EdgeDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $EdgeDir "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# UTF-8 logs (costume names and the API's punctuation are not always ASCII),
# and no output buffering so the log is live.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

while ($true) {
    foreach ($pattern in @("spotter-*.log", "spotter-*.stdout.txt")) {  # keep 20 runs
        Get-ChildItem $LogDir -Filter $pattern | Sort-Object Name -Descending |
            Select-Object -Skip 20 | Remove-Item -Force
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $proc = Start-Process -FilePath $Python -ArgumentList "-m", "costume_spotter" `
        -WorkingDirectory $EdgeDir -NoNewWindow -PassThru `
        -RedirectStandardError (Join-Path $LogDir "spotter-$stamp.log") `
        -RedirectStandardOutput (Join-Path $LogDir "spotter-$stamp.stdout.txt")
    $null = $proc.Handle  # cache the handle so ExitCode is readable after exit (PS 5.1)
    $proc.WaitForExit()
    if ($proc.ExitCode -eq 0) { break }
    Start-Sleep -Seconds 5
}
