# One-time EduPulse bootstrap on Windows
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File path\to\EduPulse\hardware\capture\Setup-EduPulseWindows.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $RepoRoot

Write-Host "=== EduPulse Windows setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "python not on PATH. Install Python 3.11+ from python.org and check 'Add to PATH'."
}

Write-Host "Python: $(python --version)"

$venv = Join-Path $RepoRoot "edupulse-env"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "Creating venv edupulse-env ..."
    python -m venv edupulse-env
}

. (Join-Path $venv "Scripts\Activate.ps1")
python -m pip install --upgrade pip
pip install -r (Join-Path $RepoRoot "requirements.txt")

$cap = Join-Path $env:USERPROFILE "edupulse\captures"
New-Item -ItemType Directory -Force -Path $cap | Out-Null
Write-Host "Captures dir: $cap"

$staffEx = Join-Path $RepoRoot "hardware\capture\staff_names.example.txt"
$wordsEx = Join-Path $RepoRoot "hardware\capture\common_words.example.txt"
$staff = Join-Path $RepoRoot "hardware\capture\staff_names.txt"
$words = Join-Path $RepoRoot "hardware\capture\common_words.txt"
if (-not (Test-Path $staff)) { Copy-Item $staffEx $staff; Write-Host "Created staff_names.txt (edit me)" }
if (-not (Test-Path $words)) { Copy-Item $wordsEx $words; Write-Host "Created common_words.txt (edit me)" }

Write-Host ""
Write-Host "Import smoke test..."
python -c "import sounddevice, soundfile, numpy; from edupulse.analysis import categorize_transmission; print('ok', categorize_transmission('need nurse')['category'][:40])"

Write-Host ""
Write-Host "Devices:"
python (Join-Path $RepoRoot "hardware\capture\check_audio_environment.py") --list-devices

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Next: edit staff_names.txt / common_words.txt"
Write-Host "      .\hardware\capture\edupulse-record.ps1 -ListDevices"
Write-Host "      .\hardware\capture\edupulse-record.ps1 -Device N -Session test1 -MaxDuration 60"
Write-Host "Docs: hardware\capture\WINDOWS_QUICKSTART.md"
