$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
  py -3.11 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,needle]"
New-Item -ItemType Directory -Force -Path "models" | Out-Null
needle download needle3 --out models

Write-Host "Brainbox OS + Needle 3 is ready. Model: models\\needle3.cact"
