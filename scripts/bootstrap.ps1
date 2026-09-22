$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
  py -3.11 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

Write-Host "Brainbox OS environment ready."
