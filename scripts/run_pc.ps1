$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
. .\.venv\Scripts\Activate.ps1

Write-Host "Starting Brainbox desktop orb..."
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command','Set-Location "$PWD"; .\.venv\Scripts\python.exe -m brainbox_os.cli'
Push-Location desktop
npm start
Pop-Location
