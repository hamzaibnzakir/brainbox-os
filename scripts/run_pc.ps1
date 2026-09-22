$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
. .\.venv\Scripts\Activate.ps1

Write-Host "Starting Brainbox orb and live voice runtime..."
Push-Location desktop
npm start
Pop-Location
