$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

function Ok($m){ Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m){ Write-Host "[FAIL] $m" -ForegroundColor Red; $script:failed = $true }

$failed = $false
if ($env:OS -notlike "*Windows*") { Fail "This preflight is for Windows." } else { Ok "Windows detected" }

if (Get-Command py -ErrorAction SilentlyContinue) { Ok "Python launcher found" } else { Fail "Python launcher 'py' not found" }
if (Get-Command node -ErrorAction SilentlyContinue) { Ok "Node.js found: $((node --version).Trim())" } else { Fail "Node.js not found" }
if (Get-Command npm -ErrorAction SilentlyContinue) { Ok "npm found: $((npm --version).Trim())" } else { Fail "npm not found" }

if (Test-Path ".venv\Scripts\python.exe") { Ok ".venv exists" } else { Fail ".venv is missing. Run .\scripts\setup_pc.ps1" }
if (Test-Path "models\needle3.cact") { Ok "Needle 3 model found" } else { Fail "models\needle3.cact is missing" }
if (Test-Path "desktop\node_modules\electron\dist\electron.exe") { Ok "Electron installed" } else { Fail "Electron is missing. Run .\scripts\setup_pc.ps1" }

if (Test-Path ".env") {
  $envLines = Get-Content ".env"
  $api = $envLines | Where-Object { $_ -match '^\s*OPENAI_API_KEY\s*=\s*.+$' -and $_ -notmatch '^\s*OPENAI_API_KEY\s*=\s*$' }
  if ($api) { Ok "OPENAI_API_KEY is configured" } else { Warn "OPENAI_API_KEY is empty. Local tests still work, agentic voice will not." }
} else { Warn ".env is missing. Create it from .env.example before agentic testing." }

try {
  & .\.venv\Scripts\python.exe -c "import sounddevice, faster_whisper, numpy, pyttsx3; print('voice imports ok')" | Out-Null
  Ok "Voice Python dependencies import"
} catch { Fail "Voice dependencies failed to import: $($_.Exception.Message)" }

try {
  & .\.venv\Scripts\python.exe -c "import mss, PIL, pywinauto, rapidocr_onnxruntime; print('vision imports ok')" | Out-Null
  Ok "Vision Python dependencies import"
} catch { Fail "Vision dependencies failed to import: $($_.Exception.Message)" }

try {
  & .\.venv\Scripts\python.exe -m brainbox_os.cli "Hey Brainbox" | Out-Null
  Ok "Brainbox CLI starts"
} catch { Fail "Brainbox CLI failed to start: $($_.Exception.Message)" }

$mic = Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'OK' }
if ($mic) { Ok "Windows sound devices detected" } else { Warn "No Windows sound device reported by WMI. Check microphone permissions/device settings." }

if ($failed) {
  Write-Host "`nPreflight FAILED. Fix the items marked [FAIL], then run this again." -ForegroundColor Red
  exit 1
}
Write-Host "`nPreflight PASSED. The PC is ready for the official Brainbox test." -ForegroundColor Green
exit 0
