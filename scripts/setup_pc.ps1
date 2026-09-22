$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher (py) is required." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js is required. Install Node.js LTS first." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm is required." }

if (-not (Test-Path ".venv")) { py -3.11 -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,needle,voice]"

if (-not (Test-Path "models\needle3.cact")) {
  New-Item -ItemType Directory -Force -Path models | Out-Null
  needle download needle3 --out models
}

Push-Location desktop
npm install
Pop-Location

if (-not (Test-Path "models\wakeword\hey_brainbox.onnx")) {
  Write-Warning "Custom wake word model is not included yet. See docs\WAKE_WORD.md to train/install hey_brainbox.onnx."
}

Write-Host ""
Write-Host "Brainbox OS PC setup complete."
Write-Host "Run: .\scripts\run_pc.ps1"
