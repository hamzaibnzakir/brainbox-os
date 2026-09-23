$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

. .\.venv\Scripts\Activate.ps1
Write-Host "Installing Pocket TTS..."
python -m pip install -U "pocket-tts>=3.1"

if (Test-Path ".env") {
  $envText = Get-Content ".env" -Raw
  if ($envText -match "(?m)^BRAINBOX_TTS_BACKEND=") {
    $envText = [regex]::Replace($envText, "(?m)^BRAINBOX_TTS_BACKEND=.*$", "BRAINBOX_TTS_BACKEND=pocket")
  } else {
    $envText += "`r`nBRAINBOX_TTS_BACKEND=pocket`r`n"
  }
  Set-Content ".env" $envText -NoNewline
}

python -c "from pocket_tts import TTSModel; m=TTSModel.load_model(language='english', quantize=True); m.get_state_for_audio_prompt('george'); print('Pocket TTS model load OK')"
Write-Host "Pocket TTS is ready. Brainbox default voice: george."
