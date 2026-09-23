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
# Install the AEC dependencies idempotently instead of probing imports through
# PowerShell's native stderr pipeline, which can terminate this script before
# Python gets a chance to report the real result.
$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
Write-Host "Checking Brainbox AEC audio dependencies..."
& $py -m pip install --disable-pip-version-check --quiet "pywebrtc-audio>=0.2,<0.3" "soundcard>=0.4.4"
if ($LASTEXITCODE -ne 0) {
  throw "Could not install Brainbox AEC audio dependencies."
}

Push-Location desktop
npm start
Pop-Location
