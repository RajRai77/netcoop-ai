# Generate one narration WAV per step with the built-in Windows voice (offline).
#   powershell -ExecutionPolicy Bypass -File scripts/demo/tts.ps1 -Out <dir> [-Voice "Microsoft David Desktop"]
param([Parameter(Mandatory = $true)][string]$Out, [string]$Voice = 'Microsoft David Desktop', [int]$Rate = 0)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force $Out | Out-Null
$steps = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'narration.json') | ConvertFrom-Json
foreach ($s in $steps) {
  $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $synth.SelectVoice($Voice)
  $synth.Rate = $Rate
  $text = if ($s.tts) { $s.tts } else { $s.text }
  $synth.SetOutputToWaveFile((Join-Path $Out "$($s.id).wav"))
  $synth.Speak($text)
  $synth.Dispose()
}
"wrote $($steps.Count) files to $Out"
