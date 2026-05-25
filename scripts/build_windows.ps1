$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DefaultPython = "C:\Users\54782\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $DefaultPython) { $DefaultPython } else { "python" }

Set-Location $Root

$PyDeps = Join-Path $Root ".codex_pydeps"
if (Test-Path $PyDeps) {
    $ExistingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
    if ([string]::IsNullOrWhiteSpace($ExistingPythonPath)) {
        $env:PYTHONPATH = $PyDeps
    } elseif ($ExistingPythonPath -notlike "*$PyDeps*") {
        $env:PYTHONPATH = "$PyDeps;$ExistingPythonPath"
    }
}

Write-Host "Building BrainAlphaOps.exe..."
& $Python -m PyInstaller --noconfirm --clean BrainAlphaOps.spec
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done: $Root\dist\BrainAlphaOps.exe"
Write-Host "The executable starts the local service in a console and opens the browser UI automatically."
