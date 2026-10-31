<#
.SYNOPSIS
    Update, rebuild and restart the Costume Spotter in one step (docs/setup-windows.md section 8).

.DESCRIPTION
    Run it after pulling new code, changing settings, or any time the app needs
    a clean restart. Steps:
      1. git pull (fast-forward only; skipped with -NoPull, or when you have
         uncommitted changes, so your edits are never touched).
      2. Stop the running app: the "Costume Spotter" autostart task and any
         copy started by hand from this folder. Windows locks files that are in
         use, so this must happen before packages are reinstalled.
      3. Update Python packages in edge\.venv (keeps the DirectML GPU runtime
         if that's what is installed).
      4. Rebuild the dashboard (web\dist). npm packages are reinstalled only
         when package-lock.json changed. Skipped with -SkipDashboard, or when
         Node.js isn't installed.
      5. Report whether the AI is on (your API key is loaded) or in pretend mode.
      6. Start the app again: through the autostart task if it's installed (then
         wait until it answers on http://localhost:8000), otherwise right here
         in this window (Ctrl+C stops it). -NoStart skips this step.

    No edge\.venv yet? Run setup.ps1 first; this script tells you so.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\update.ps1
.EXAMPLE
    # Restart only: no pull, no dashboard rebuild
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\update.ps1 -NoPull -SkipDashboard
#>
[CmdletBinding()]
param(
    # Don't run git pull.
    [switch]$NoPull,
    # Don't rebuild the dashboard.
    [switch]$SkipDashboard,
    # Update and rebuild, but leave the app stopped.
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoDir = Split-Path $EdgeDir -Parent
$WebDir = Join-Path $RepoDir "web"
$VenvPython = Join-Path $EdgeDir ".venv\Scripts\python.exe"
$TaskName = "Costume Spotter"
$HealthUrl = "http://localhost:8000/api/health"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    !!  $text" -ForegroundColor Yellow }

function Invoke-Checked {
    # Run a native command and stop on a non-zero exit code (Windows
    # PowerShell 5.1 does not do this for external programs by itself).
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed (exit $LASTEXITCODE)" }
}

function Invoke-Quiet {
    # Run a native command, capture its output, and return the exit code.
    # Windows PowerShell 5.1 turns redirected stderr into errors, which
    # $ErrorActionPreference = "Stop" makes fatal; pip writes harmless warnings
    # there ("Package(s) not found"), so relax it just for this call.
    param([string]$Exe, [string[]]$Arguments)
    $ErrorActionPreference = "Continue"
    $script:QuietOutput = (& $Exe @Arguments 2>&1 | ForEach-Object { "$_" })
    return $LASTEXITCODE
}

if (-not (Test-Path $VenvPython)) {
    throw "edge\.venv not found. Run the one-time setup first:`n" +
          "  powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup.ps1"
}

# --- 1. Pull -----------------------------------------------------------------------
Step "Getting the latest code"
if ($NoPull) {
    Warn "skipped (-NoPull)"
} elseif (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Warn "git not found - skipping the pull"
} else {
    Push-Location $RepoDir
    try {
        $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
        $dirty = & git status --porcelain --untracked-files=no
        if ($dirty) {
            Warn "you have uncommitted changes on '$branch' - not pulling, so nothing of yours is touched"
        } else {
            & git pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                Warn "git pull failed (see above) - continuing with the code you have"
            } else {
                Ok "'$branch' is up to date"
            }
        }
    } finally {
        Pop-Location
    }
}

# --- 2. Stop the running app ----------------------------------------------------------
Step "Stopping the running app"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task -and $task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
    Ok "stopped the '$TaskName' autostart task"
}
# Any python running this folder's app, started by hand or left behind by the
# task (stopping a task doesn't always stop the process it launched).
$venvDir = Join-Path $EdgeDir ".venv"
$running = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*costume_spotter*" -and
                   $_.ExecutablePath -and $_.ExecutablePath.StartsWith($venvDir, "OrdinalIgnoreCase") })
foreach ($proc in $running) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}
if ($running.Count -gt 0) {
    Start-Sleep -Seconds 2  # let Windows release file locks before pip runs
    Ok "stopped $($running.Count) running copy(ies)"
} elseif (-not ($task -and $task.State -eq "Running")) {
    Ok "nothing was running"
}

# --- 3. Python packages -------------------------------------------------------------------
Step "Updating Python packages"
Push-Location $EdgeDir
try {
    $gpu = (Invoke-Quiet $VenvPython @("-m", "pip", "show", "onnxruntime-directml")) -eq 0
    Invoke-Checked $VenvPython @("-m", "pip", "install", "-e", ".[windows,dev]", "--quiet",
                                 "--disable-pip-version-check")
    if ($gpu) {
        # The [windows] extra (and piper-tts) pull the CPU onnxruntime back in.
        # It shares the `onnxruntime` folder with the DirectML build, so remove
        # it, then reinstall DirectML to restore the files that removal deleted.
        $null = Invoke-Quiet $VenvPython @("-m", "pip", "uninstall", "-y", "onnxruntime")
        Invoke-Checked $VenvPython @("-m", "pip", "install", "--force-reinstall", "--no-deps",
                                     "--quiet", "--disable-pip-version-check",
                                     "onnxruntime-directml")
        Ok "up to date (DirectML GPU runtime kept)"
    } else {
        Ok "up to date"
    }
} finally {
    Pop-Location
}

# --- 4. Dashboard ---------------------------------------------------------------------------
Step "Rebuilding the dashboard"
if ($SkipDashboard) {
    Warn "skipped (-SkipDashboard)"
} elseif (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Warn "Node.js not found - the dashboard was not rebuilt (install it from https://nodejs.org)"
} else {
    Push-Location $WebDir
    try {
        # npm ci wipes and reinstalls node_modules: only worth it when the
        # lockfile changed since the last install.
        $installed = Join-Path $WebDir "node_modules\.package-lock.json"
        $lock = Join-Path $WebDir "package-lock.json"
        if (-not (Test-Path $installed) -or
            (Get-Item $lock).LastWriteTime -gt (Get-Item $installed).LastWriteTime) {
            Invoke-Checked "npm.cmd" @("ci", "--no-audit", "--no-fund")
        }
        Invoke-Checked "npm.cmd" @("run", "build")
        Ok "built (served at http://localhost:8000)"
    } finally {
        Pop-Location
    }
}

# --- 5. Settings check -----------------------------------------------------------------------
Step "Checking settings"
Push-Location $EdgeDir
try {
    # Loads settings exactly as the app will; a bad value in edge\.env is
    # reported by name (e.g. "TRACKER_MIN_HITS: Input should be a valid integer").
    $check = @'
from costume_spotter.config import Settings
try:
    s = Settings()
except Exception as e:
    errs = e.errors() if hasattr(e, "errors") else None
    print("BAD " + ("; ".join(".".join(map(str, x["loc"])).upper() + ": " + x["msg"]
                              for x in errs) if errs else str(e)))
    raise SystemExit(1)
print(("on: " + s.claude_model) if s.anthropic_api_key else "OFF")
'@
    $code = Invoke-Quiet $VenvPython @("-c", $check)
    $ai = $script:QuietOutput | Select-Object -Last 1
    if ($code -ne 0) {
        throw "edge\.env has a setting the app can't use: $("$ai" -replace '^BAD ', '')"
    }
    if ("$ai".StartsWith("on")) {
        Ok "AI costume identification $ai"
    } else {
        Warn "AI is OFF: no ANTHROPIC_API_KEY, so costumes will be canned 'pretend' answers."
        Warn "Add your key on the ANTHROPIC_API_KEY= line in edge\.env (no # in front)."
    }
} finally {
    Pop-Location
}

# --- 6. Start -------------------------------------------------------------------------------------
if ($NoStart) {
    Write-Host "`nDone. The app is stopped (-NoStart)." -ForegroundColor Cyan
    exit 0
}

if ($task) {
    Step "Starting the '$TaskName' task"
    Start-ScheduledTask -TaskName $TaskName
    $deadline = (Get-Date).AddSeconds(60)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $null = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
            $healthy = $true
            break
        } catch {
            # not up yet: the voice and detection model take a few seconds to load
        }
    }
    if ($healthy) {
        Ok "running: open http://localhost:8000"
    } else {
        Warn "no answer from $HealthUrl after 60 s. Check the newest log in edge\data\logs"
        exit 1
    }
} else {
    Step "Starting the app in this window (Ctrl+C to stop)"
    Write-Host "    Open http://localhost:8000 once it says it's up." -ForegroundColor Green
    Set-Location $EdgeDir
    & $VenvPython -m costume_spotter
}
