$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "Brainbox OS" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Brainbox OS startup task removed."
