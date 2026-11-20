# NEXUS Windows 10/11 Python 3.12+ Environment Setup
$ErrorActionPreference = "Stop"

Write-Host "Checking Python 3.12+ availability..."
python --version

if (-Not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e "./core[dev]"

Write-Host "NEXUS Python environment ready."
