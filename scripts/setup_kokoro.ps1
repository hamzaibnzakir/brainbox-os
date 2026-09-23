$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

. .\.venv\Scripts\Activate.ps1
Write-Host "Installing Kokoro ONNX..."
python -m pip install -U "kokoro-onnx==0.6.1" soundfile

$dir = Join-Path (Get-Location) "models\tts"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$model = Join-Path $dir "kokoro-v1.0.int8.onnx"
$voices = Join-Path $dir "voices-v1.0.bin"

if (-not (Test-Path $model)) {
  Write-Host "Downloading Kokoro int8 model (~114 MB)..."
  Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx" -OutFile $model
}
if (-not (Test-Path $voices)) {
  Write-Host "Downloading Kokoro voice pack (~28 MB)..."
  Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin" -OutFile $voices
}

python -c "from kokoro_onnx import Kokoro; Kokoro(r'models/tts/kokoro-v1.0.int8.onnx', r'models/tts/voices-v1.0.bin'); print('Kokoro model load OK')"
Write-Host "Kokoro is ready. Default Brainbox voice: bm_lewis (British English)."
