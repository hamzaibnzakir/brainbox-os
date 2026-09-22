$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$root = (Get-Location).Path
$electron = Join-Path $root "desktop\node_modules\electron\dist\electron.exe"
if (-not (Test-Path $electron)) { throw "Electron is not installed. Run .\scripts\setup_pc.ps1 first." }
$task = "Brainbox OS"
$action = New-ScheduledTaskAction -Execute $electron -Argument "`"$root\desktop`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Brainbox OS startup task installed. Reboot Windows, then say Hey Brainbox."
