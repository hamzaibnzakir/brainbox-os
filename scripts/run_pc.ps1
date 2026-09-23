$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
. .\.venv\Scripts\Activate.ps1

if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
      $name = $matches[1].Trim(); $value = $matches[2].Trim().Trim('"').Trim("'")
      Set-Item -Path "Env:$name" -Value $value
    }
  }
}

# Brainbox voice uses a speaker-reference AEC path on Windows.
# Probe quietly without allowing PowerShell's native stderr handling to abort the launcher.
$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$probeOutput = & $py -c "import pywebrtc_audio, soundcard" 2>&1 | Out-String
$aecReady = ($LASTEXITCODE -eq 0)

if (-not $aecReady) {
  Write-Host "Installing Brainbox AEC audio dependencies..."
  & $py -m pip install "pywebrtc-audio>=0.2,<0.3" "soundcard>=0.4.4"
  if ($LASTEXITCODE -ne 0) { throw "Could not install Brainbox AEC audio dependencies." }

  & $py -c "import pywebrtc_audio, soundcard"
  if ($LASTEXITCODE -ne 0) { throw "Brainbox AEC dependencies installed but could not be imported." }
}

Push-Location desktop
npm start
Pop-Location
