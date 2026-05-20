$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DefaultPython = "C:\Users\54782\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $DefaultPython) { $DefaultPython } else { "python" }

Set-Location $Root

Write-Host "Building BrainAlphaOps.exe..."
& $Python -m PyInstaller --noconfirm --clean BrainAlphaOps.spec

Write-Host ""
Write-Host "Done: $Root\dist\BrainAlphaOps.exe"
Write-Host "The executable starts the local service in a console and opens the browser UI automatically."
