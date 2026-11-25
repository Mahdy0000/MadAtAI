# One-time setup (Windows PowerShell). Run from the agents\ folder:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
Write-Host ""
Write-Host 'Done. Try it:  .\.venv\Scripts\python.exe -m sphinx1 --task "find the red bottle"'
