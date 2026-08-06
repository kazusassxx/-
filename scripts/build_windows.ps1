<#
.SYNOPSIS
    Build meeting-transcriber Windows distribution (phase 9.1/9.2).

.DESCRIPTION
    - PyInstaller onedir bundle, entry = gui/app.py
    - Collect sherpa_onnx / soundfile fully; hidden-import sounddevice / PyAudioWPatch
    - Models built into ./models/ next to the exe (runtime lookup: exe-adjacent first,
      then ~/.meeting-transcriber/models/)
    - Auto-invokes scripts/download_models.py when models are missing (use -SkipModels to bypass)
    - Compresses the bundle into a zip archive

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -SkipModels
#>
param(
    [string]$Name = "meeting-transcriber",
    [string]$Version = "0.1.0",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    # ---------- 1/6 dependency check ----------
    Write-Host "[1/6] Checking PyInstaller ..."
    python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        python -m pip install pyinstaller
    }

    # ---------- 2/6 model check (source = user cache) ----------
    $SourceModels = Join-Path $env:USERPROFILE ".meeting-transcriber\models"
    $HaveModels = $false
    if (Test-Path $SourceModels) {
        $Count = (Get-ChildItem $SourceModels -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 0 } | Measure-Object).Count
        $HaveModels = $Count -gt 0
    }
    if (-not $HaveModels) {
        if ($SkipModels) {
            Write-Host "[2/6] WARNING: no model cache found and -SkipModels given; bundle will contain no models."
        } else {
            Write-Host "[2/6] Models missing; invoking scripts/download_models.py ..."
            python scripts/download_models.py
            if ($LASTEXITCODE -ne 0) { throw "Model download failed. Check network/proxy and retry." }
        }
    } else {
        Write-Host "[2/6] Model cache found: $SourceModels"
    }

    # ---------- 3/6 clean previous artifacts ----------
    Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

    # ---------- 4/6 PyInstaller onedir bundle ----------
    Write-Host "[3/6] Running PyInstaller (onedir) ..."
    python -m PyInstaller --noconfirm --clean --onedir --name $Name `
        --paths src `
        --collect-all sherpa_onnx `
        --collect-all soundfile `
        --hidden-import sounddevice `
        --hidden-import PyAudioWPatch `
        --collect-submodules meeting_transcriber `
        src/meeting_transcriber/gui/app.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    # ---------- 5/6 embed models next to the exe ----------
    $DistDir = Join-Path $Root "dist\$Name"
    $DistModels = Join-Path $DistDir "models"
    if ($HaveModels) {
        Write-Host "[4/6] Copying models into $DistModels"
        New-Item -ItemType Directory -Force -Path $DistModels | Out-Null
        Copy-Item -Recurse -Force (Join-Path $SourceModels "*") $DistModels
        $checks = @(
            "models\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\model.int8.onnx",
            "models\3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
            "models\sherpa-onnx-pyannote-segmentation-3-0\model.int8.onnx"
        )
        $missing = $checks | Where-Object { -not (Test-Path (Join-Path $DistDir $_)) }
        if ($missing) {
            Write-Host "[4/6] WARNING: models missing (run scripts/download_models.py on the target machine):"
            $missing | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Host "[4/6] All three models present."
        }
    } else {
        Write-Host "[4/6] Skipping model embedding (no model cache)."
    }

    # ---------- 6/6 zip distribution ----------
    $ZipPath = Join-Path $Root "dist\$Name-$Version-win64.zip"
    Write-Host "[5/6] Compressing: $ZipPath"
    Compress-Archive -Path $DistDir -DestinationPath $ZipPath -Force

    Write-Host "[6/6] Done."
    Write-Host "       Dir: $DistDir"
    Write-Host "       Zip: $ZipPath"
} finally {
    Pop-Location
}
