<#
.SYNOPSIS
    One-time setup of the Chatterbox voice (NVIDIA GPU) - docs/setup-windows.md section 9.

.DESCRIPTION
    Builds edge\.venv-chatterbox, a separate Python environment for the
    Chatterbox voice server. It is separate from edge\.venv because Chatterbox
    needs PyTorch (about 3 GB with CUDA) and exact library versions that would
    conflict with the app's own packages.

    Steps:
      1. Find 64-bit Python 3.11-3.14 (3.11 or 3.12 preferred: the versions
         Chatterbox was tested on).
      2. Create edge\.venv-chatterbox.
      3. Install PyTorch built for CUDA 12.8 (RTX 50-series cards need it),
         then Chatterbox and its libraries.
      4. Check that PyTorch can use the GPU.
      5. Download the model (about 1.5 GB, once) and time a few porch lines,
         saving a sample to edge\chatterbox-sample.wav so you can hear it.

    Then set TTS_ENGINE=chatterbox and CHATTERBOX_PYTHON in edge\.env (the
    script prints the lines) and run update.cmd.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup-chatterbox.ps1
.EXAMPLE
    # Re-run only the timing test
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup-chatterbox.ps1 -BenchOnly
#>
[CmdletBinding()]
param(
    # Skip installing; just check the GPU and time the voice again.
    [switch]$BenchOnly
)

$ErrorActionPreference = "Stop"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvDir = Join-Path $EdgeDir ".venv-chatterbox"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Server = Join-Path $EdgeDir "costume_spotter\speech\chatterbox_server.py"

# Versions: chatterbox-tts 0.1.7 asks for torch 2.6, which has no kernels for
# RTX 50-series GPUs (sm_120). torch 2.9 + CUDA 12.8 does, so chatterbox is
# installed without its own pins (--no-deps) and its libraries are listed here.
$TorchIndex = "https://download.pytorch.org/whl/cu128"
$TorchPackages = @("torch==2.9.0", "torchaudio==2.9.0")
$ChatterboxPackage = "chatterbox-tts==0.1.7"
# numpy: <2 on Python 3.11/3.12 (what Chatterbox was tested with); 3.13+ has
# no numpy 1.x, so >=2 there (chatterbox_server.py works around the one bug).
# setuptools: the watermark library imports pkg_resources, which venvs on
# Python 3.12+ no longer include and setuptools 81+ dropped.
$ChatterboxLibraries = @(
    "setuptools<81", "librosa==0.11.0", "s3tokenizer", "transformers==5.2.0",
    "diffusers==0.29.0", "resemble-perth>=1.0.0", "conformer==0.3.2",
    "safetensors==0.5.3", "pyloudnorm", "omegaconf", "einops", "huggingface_hub"
)

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

function Get-PythonMinor {
    # The 3.x minor version of a 64-bit CPython 3 at `$Exe $Prefix`, or $null.
    # No double quotes in the -c code: Windows PowerShell 5.1 mangles them.
    param([string]$Exe, [string[]]$Prefix)
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return $null }
    try {
        $out = & $Exe @Prefix -c "import sys, struct; print(sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8)" 2>$null
    } catch {
        return $null  # e.g. the Microsoft Store "python" alias
    }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $parts = "$out".Trim().Split(" ")
    if ($parts.Count -ne 3 -or $parts[0] -ne "3" -or $parts[2] -ne "64") { return $null }
    return [int]$parts[1]
}

if (-not $BenchOnly) {
    # --- 1. Python ---------------------------------------------------------------
    # 3.11/3.12 first: what Chatterbox was tested on. 3.13/3.14 also work.
    # Plain `python` last, for installs without the py launcher.
    Step "Checking for 64-bit Python 3.11-3.14"
    $Python = $null
    $candidates = @()
    foreach ($m in 11, 12, 13, 14) { $candidates += , @("py", "-3.$m") }
    $candidates += , @("python")
    foreach ($candidate in $candidates) {
        $prefix = @($candidate | Select-Object -Skip 1)
        $minor = Get-PythonMinor $candidate[0] $prefix
        if ($minor -ge 11 -and $minor -le 14) {
            $Python = $candidate
            Ok "Python 3.$minor ($($candidate -join ' '))"
            break
        }
    }
    if (-not $Python) {
        throw "No 64-bit Python 3.11-3.14 found (Python 3.15 is too new for PyTorch). " +
              "Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/ " +
              "and re-run this script. It installs next to your other Pythons; nothing else changes."
    }

    # --- 2. Virtual environment -----------------------------------------------------
    Step "Creating edge\.venv-chatterbox"
    if (Test-Path $VenvPython) {
        Ok "already exists"
    } else {
        $pyArgs = @($Python | Select-Object -Skip 1) + @("-m", "venv", $VenvDir)
        Invoke-Checked $Python[0] $pyArgs
        Ok "created"
    }
    $VenvMinor = Get-PythonMinor $VenvPython @()
    if (-not ($VenvMinor -ge 11 -and $VenvMinor -le 14)) {
        throw "edge\.venv-chatterbox uses an unsupported Python. Delete it " +
              "(Remove-Item -Recurse -Force edge\.venv-chatterbox) and re-run this script."
    }
    if ($VenvMinor -le 12) {
        $ChatterboxLibraries += "numpy>=1.24,<2"
    } else {
        $ChatterboxLibraries += "numpy>=2"
    }

    # --- 3. Packages ---------------------------------------------------------------
    Step "Installing PyTorch for CUDA 12.8 (about 3 GB; several minutes the first time)"
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip", "--quiet",
                                 "--disable-pip-version-check")
    Invoke-Checked $VenvPython (@("-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                                  "--index-url", $TorchIndex) + $TorchPackages)
    Ok "installed"

    Step "Installing Chatterbox"
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                                 "--no-deps", $ChatterboxPackage)
    # torch is already satisfied, so pip leaves the CUDA build alone.
    Warn "pip may print 'ERROR: ... chatterbox-tts requires torch==2.6.0, gradio ...'."
    Warn "That is expected (newer PyTorch on purpose; the web demo isn't needed) - ignore it."
    Invoke-Checked $VenvPython (@("-m", "pip", "install", "--quiet",
                                  "--disable-pip-version-check") + $ChatterboxLibraries)
    Ok "installed"
}

if (-not (Test-Path $VenvPython)) {
    throw "edge\.venv-chatterbox not found - run this script without -BenchOnly first"
}

# --- 4. GPU check ----------------------------------------------------------------
Step "Checking the GPU"
Invoke-Checked $VenvPython @($Server, "--check")

# --- 5. Download + timing --------------------------------------------------------
Step "Downloading the voice model (first time only) and timing some lines"
Push-Location $EdgeDir
try {
    Invoke-Checked $VenvPython @($Server, "--bench")
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. To use Chatterbox, set these in edge\.env (keep PIPER_VOICE_PATH as it is:" -ForegroundColor Cyan
Write-Host "Piper speaks while Chatterbox loads, or if it's ever down or slow):" -ForegroundColor Cyan
Write-Host "    TTS_ENGINE=chatterbox"
Write-Host "    CHATTERBOX_PYTHON=.venv-chatterbox\Scripts\python.exe"
Write-Host "then run update.cmd from the repo folder." -ForegroundColor Cyan
