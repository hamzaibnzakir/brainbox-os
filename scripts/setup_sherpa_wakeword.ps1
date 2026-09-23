$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$root = (Get-Location).Path
$dir = Join-Path $root "models\wakeword\sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
$archive = Join-Path $root "models\wakeword\sherpa-kws.tar.bz2"
New-Item -ItemType Directory -Force (Join-Path $root "models\wakeword") | Out-Null
if (-not (Test-Path $dir)) {
  Invoke-WebRequest -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2" -OutFile $archive
  tar -xjf $archive -C (Join-Path $root "models\wakeword")
  Remove-Item $archive -Force
}
$keywordsRaw = Join-Path $dir "brainbox_keywords_raw.txt"
"HEY BRAINBOX @HEY_BRAINBOX" | Set-Content -Encoding UTF8 $keywordsRaw
$keywords = Join-Path $dir "brainbox_keywords.txt"
& ".venv\Scripts\sherpa-onnx-cli.exe" text2token --tokens (Join-Path $dir "tokens.txt") --tokens-type bpe --bpe-model (Join-Path $dir "bpe.model") $keywordsRaw $keywords
Write-Host "Sherpa wake word model ready: $dir"
Write-Host "Keyword file: $keywords"
Write-Host "Set BRAINBOX_WAKEWORD_BACKEND=sherpa to test it."
