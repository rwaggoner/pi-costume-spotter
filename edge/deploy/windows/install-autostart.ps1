<#
.SYNOPSIS
    Start the Costume Spotter automatically when you log in (docs/setup-windows.md section 6).

.DESCRIPTION
    Registers a Task Scheduler task, "Costume Spotter", that runs run-spotter.ps1
    in a hidden window at logon of the current user. A logon task (rather than a
    Windows service) runs in your desktop session, so the webcam and the default
    speaker work exactly as they do when you start the app by hand. For a
    dedicated porch PC, pair it with automatic sign-in.

    -Uninstall removes the task. No administrator rights needed either way.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\install-autostart.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\install-autostart.ps1 -Uninstall
#>
[CmdletBinding()]
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$TaskName = "Costume Spotter"
$Runner = Join-Path $PSScriptRoot "run-spotter.ps1"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed the '$TaskName' task." -ForegroundColor Green
    } else {
        Write-Host "No '$TaskName' task to remove."
    }
    exit 0
}

if (-not (Test-Path (Join-Path $EdgeDir ".venv\Scripts\python.exe"))) {
    throw "edge\.venv not found - run setup.ps1 first."
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $EdgeDir `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
# Interactive = runs in the user's desktop session (camera + speaker access).
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force `
    -Description "Costume Spotter edge app (pi-costume-spotter). Logs: edge\data\logs\spotter-*.log" | Out-Null
Write-Host "Registered '$TaskName' - it starts at your next login." -ForegroundColor Green
Write-Host "Start it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Logs:          Get-ChildItem '$EdgeDir\data\logs\spotter-*.log' | Sort-Object Name | Select-Object -Last 1 | Get-Content -Wait -Tail 30"
