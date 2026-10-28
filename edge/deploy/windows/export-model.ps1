<#
.SYNOPSIS
    Export YOLOv8n to ONNX once, into edge\models\yolov8n.onnx (docs/setup-windows.md section 3).

.DESCRIPTION
    The model is not in git: the YOLOv8 weights are licensed by Ultralytics under
    AGPL-3.0, while this repo is MIT (docs/decisions/010-windows-target.md). So
    each machine makes its own copy:

      1. creates a throwaway venv in %TEMP% (keeps PyTorch, ~1 GB, out of the
         app's venv - the app only needs ONNX Runtime),
      2. installs ultralytics with the CPU build of PyTorch,
      3. downloads yolov8n.pt and exports it to ONNX (opset 17, 640x640),
      4. copies the .onnx into edge\models and deletes the throwaway venv.

    Alternative: copy a yolov8n.onnx you already have into edge\models.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\export-model.ps1
.EXAMPLE
    # The small model: more accurate, roughly 3x slower. Then set
    # ONNX_MODEL_PATH=./models/yolov8s.onnx in edge\.env
    powershell -ExecutionPolicy Bypass -File edge\deploy\windows\export-model.ps1 -Model yolov8s
#>
[CmdletBinding()]
param(
    [ValidateSet("yolov8n", "yolov8s", "yolo11n", "yolo11s")]
    [string]$Model = "yolov8n"
)

$ErrorActionPreference = "Stop"
$EdgeDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ModelsDir = Join-Path $EdgeDir "models"
$Target = Join-Path $ModelsDir "$Model.onnx"
$Work = Join-Path $env:TEMP "costume-spotter-export"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed (exit $LASTEXITCODE)" }
}

if (Test-Path $Target) {
    Write-Host "$Target already exists - delete it first to re-export." -ForegroundColor Green
    exit 0
}

$Python = $null
foreach ($candidate in @("py", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { $Python = $candidate; break }
}
if (-not $Python) { throw "Python not found - run setup.ps1 first." }

Write-Host "==> Creating a throwaway export environment in $Work" -ForegroundColor Cyan
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$pyArgs = @()
if ($Python -eq "py") { $pyArgs = @("-3") }
Invoke-Checked $Python ($pyArgs + @("-m", "venv", (Join-Path $Work "venv")))
$WorkPython = Join-Path $Work "venv\Scripts\python.exe"

try {
    Write-Host "==> Installing ultralytics + CPU PyTorch (large download, one time only)" -ForegroundColor Cyan
    Invoke-Checked $WorkPython @("-m", "pip", "install", "--quiet", "torch", "torchvision",
                                 "--index-url", "https://download.pytorch.org/whl/cpu")
    Invoke-Checked $WorkPython @("-m", "pip", "install", "--quiet", "ultralytics", "onnx", "onnxslim")

    Write-Host "==> Exporting $Model to ONNX" -ForegroundColor Cyan
    Push-Location $Work
    try {
        $export = "from ultralytics import YOLO; YOLO('$Model.pt').export(format='onnx', imgsz=640, opset=17)"
        Invoke-Checked $WorkPython @("-c", $export)
    } finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    Copy-Item (Join-Path $Work "$Model.onnx") $Target
    Write-Host "==> Saved $Target" -ForegroundColor Green
} finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
