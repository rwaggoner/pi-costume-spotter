<#
.SYNOPSIS
    One-shot Windows setup for the Costume Spotter edge app (docs/setup-windows.md).

.DESCRIPTION
    Idempotent: safe to re-run after a git pull. Steps:
      1. Check Python 3.11+ (via the py launcher or python on PATH).
      2. Create edge\.venv and install the [windows] extra (webcam + ONNX + Piper).
         -Gpu swaps the CPU ONNX Runtime for DirectML (any DirectX 12 GPU).
      3. Create edge\.env from .env.example with the windows profile settings
         (an existing .env is never overwritten).
      4. Download the Piper voice into edge\models\voices.
      5. Build the dashboard (web\dist) if Node.js is installed.
      6. Report whether the YOLO model is present (export-model.ps1 makes it).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup.ps1 -Gpu
#>
[CmdletBinding()]
param(
    # Use onnxruntime-directml (GPU) instead of the CPU onnxruntime.
    [switch]$Gpu,
    # Piper voice to download (see https://rhasspy.github.io/piper-samples/).
    [string]$Voice = "en_US-lessac-medium",
    # Skip building the dashboard even if npm is available.
    [switch]$SkipDashboard
)

$ErrorActionPreference = "Stop"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoDir = Split-Path $EdgeDir -Parent
$VenvPython = Join-Path $EdgeDir ".venv\Scripts\python.exe"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    !!  $text" -ForegroundColor Yellow }

function Invoke-Checked {
    # Run a native command and stop on a non-zero exit code (PowerShell 5.1
    # does not do this for external programs by itself).
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed (exit $LASTEXITCODE)" }
}

# --- 1. Python ---------------------------------------------------------------
Step "Checking for Python 3.11+"
$Python = $null
foreach ($candidate in @(@("py", "-3"), @("python"))) {
    $exe = $candidate[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $pyArgs = @($candidate | Select-Object -Skip 1)
    # The Microsoft Store "python" alias exists but fails; treat any error as "not this one".
    try {
        $version = & $exe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    } catch {
        continue
    }
    if ($LASTEXITCODE -eq 0 -and $version -and ([version]$version -ge [version]"3.11")) {
        $Python = $candidate
        Ok "Python $version ($($candidate -join ' '))"
        break
    }
}
if (-not $Python) {
    throw "Python 3.11+ not found. Install it from https://www.python.org/downloads/windows/ " +
          "(tick 'Add python.exe to PATH'), then re-run this script."
}

# --- 2. Virtual environment + packages -----------------------------------------
Step "Creating the virtual environment (edge\.venv)"
if (-not (Test-Path $VenvPython)) {
    $pyExe = $Python[0]
    $pyArgs = @($Python | Select-Object -Skip 1) + @("-m", "venv", (Join-Path $EdgeDir ".venv"))
    Invoke-Checked $pyExe $pyArgs
    Ok "created"
} else {
    Ok "already exists"
}

Step "Installing packages (a few minutes the first time)"
Push-Location $EdgeDir
try {
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
    Invoke-Checked $VenvPython @("-m", "pip", "install", "-e", ".[windows,dev]", "--quiet")
    if ($Gpu) {
        # piper-tts pulls in the CPU onnxruntime; the two packages share the
        # `onnxruntime` module name, so the CPU one must go before DirectML lands.
        Invoke-Checked $VenvPython @("-m", "pip", "uninstall", "-y", "onnxruntime", "--quiet")
        Invoke-Checked $VenvPython @("-m", "pip", "install", "-e", ".[directml]", "--quiet")
        Ok "installed (DirectML GPU runtime)"
    } else {
        Ok "installed (CPU runtime)"
    }
} finally {
    Pop-Location
}

# --- 3. .env -------------------------------------------------------------------
Step "Writing edge\.env"
$EnvFile = Join-Path $EdgeDir ".env"
if (Test-Path $EnvFile) {
    Ok ".env already exists - left untouched (compare with .env.example after pulls)"
} else {
    $provider = "cpu"
    if ($Gpu) { $provider = "directml" }
    $settings = [ordered]@{
        "EDGE_PROFILE"     = "windows"
        "TTS_ENGINE"       = "piper"
        "PIPER_VOICE_PATH" = "./models/voices/$Voice.onnx"
        "ONNX_MODEL_PATH"  = "./models/yolov8n.onnx"
        "ONNX_PROVIDER"    = $provider
    }
    $lines = Get-Content -Encoding UTF8 (Join-Path $EdgeDir ".env.example")
    $out = foreach ($line in $lines) {
        $key = ($line -replace '^#?\s*([A-Z_]+)=.*$', '$1')
        if ($settings.Contains($key)) {
            "$key=$($settings[$key])"
            $settings.Remove($key)
        } else {
            $line
        }
    }
    foreach ($key in $settings.Keys) { $out += "$key=$($settings[$key])" }
    # UTF-8 without BOM: pydantic-settings reads the file as plain UTF-8.
    [System.IO.File]::WriteAllLines($EnvFile, [string[]]$out, (New-Object System.Text.UTF8Encoding $false))
    Ok "created with EDGE_PROFILE=windows - add ANTHROPIC_API_KEY to identify real costumes"
}

# --- 4. Piper voice --------------------------------------------------------------
Step "Downloading the Piper voice ($Voice)"
$VoiceDir = Join-Path $EdgeDir "models\voices"
New-Item -ItemType Directory -Force -Path $VoiceDir | Out-Null
if (Test-Path (Join-Path $VoiceDir "$Voice.onnx")) {
    Ok "already downloaded"
} else {
    Invoke-Checked $VenvPython @("-m", "piper.download_voices", $Voice, "--download-dir", $VoiceDir)
    Ok "saved to models\voices"
}

# --- 5. Dashboard -----------------------------------------------------------------
Step "Building the dashboard (web\dist)"
if ($SkipDashboard) {
    Warn "skipped (-SkipDashboard)"
} elseif (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Warn "Node.js not found - install it from https://nodejs.org and re-run to get the dashboard"
} else {
    Push-Location (Join-Path $RepoDir "web")
    try {
        Invoke-Checked "npm.cmd" @("ci", "--no-audit", "--no-fund")
        Invoke-Checked "npm.cmd" @("run", "build")
        Ok "built - served by the app at http://localhost:8000"
    } finally {
        Pop-Location
    }
}

# --- 6. YOLO model ------------------------------------------------------------------
Step "Checking for the YOLO model"
if (Test-Path (Join-Path $EdgeDir "models\yolov8n.onnx")) {
    Ok "models\yolov8n.onnx present"
} else {
    Warn "models\yolov8n.onnx is missing. Create it once with:"
    Warn "  powershell -ExecutionPolicy Bypass -File edge\deploy\windows\export-model.ps1"
}

Write-Host "`nDone. Start the app from the edge folder with:" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\python.exe -m costume_spotter"
Write-Host "Autostart at login: edge\deploy\windows\install-autostart.ps1"
