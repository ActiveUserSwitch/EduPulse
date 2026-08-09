# EduPulse capture launcher (Windows PowerShell)
# Usage:
#   .\hardware\capture\edupulse-record.ps1 -Device 1 -Session "work-test"
#   .\hardware\capture\edupulse-record.ps1 -ListDevices
#   .\hardware\capture\edupulse-record.ps1 -Device 1 -MaxDuration 120 -NoTranscribe

param(
    [int]$Device = -1,
    [string]$Session = "",
    [string]$DataDir = "",
    [string]$Model = "tiny",
    [double]$MaxDuration = 0,
    [switch]$ListDevices,
    [switch]$NoTranscribe,
    [switch]$SkipCalibration
)

$ErrorActionPreference = "Stop"

# Repo root = parent of hardware/
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $RepoRoot

# Activate venv if present
$venvActivate = Join-Path $RepoRoot "edupulse-env\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

if (-not $DataDir) {
    $DataDir = Join-Path $env:USERPROFILE "edupulse\captures"
}

$py = "python"
$script = Join-Path $RepoRoot "hardware\capture\record_with_transcribe.py"

if ($ListDevices) {
    & $py $script --list-devices
    exit $LASTEXITCODE
}

$argsList = @(
    $script,
    "--data-dir", $DataDir,
    "--model", $Model
)

if ($Device -ge 0) {
    $argsList += @("--device", "$Device")
}
if ($Session) {
    $argsList += @("--session", $Session)
}
if ($MaxDuration -gt 0) {
    $argsList += @("--max-duration", "$MaxDuration")
}
if ($NoTranscribe) {
    $argsList += "--no-transcribe"
}
if ($SkipCalibration) {
    $argsList += "--skip-calibration"
}

$staff = Join-Path $RepoRoot "hardware\capture\staff_names.txt"
$words = Join-Path $RepoRoot "hardware\capture\common_words.txt"
if (Test-Path $staff) {
    $argsList += @("--known-staff-file", $staff)
}
if (Test-Path $words) {
    $argsList += @("--common-words-file", $words)
}

Write-Host "EduPulse capture → $DataDir"
Write-Host "python $($argsList -join ' ')"
& $py @argsList
exit $LASTEXITCODE
