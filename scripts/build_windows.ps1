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

$OfficialContextFiles = @(
    "official_fields.json",
    "official_fields.meta.json",
    "official_operators.json",
    "official_operators.meta.json",
    "official_datasets.json",
    "official_datasets.meta.json",
    "official_context_refresh_status.json"
)
$DistData = Join-Path $Root "dist\data"
New-Item -ItemType Directory -Path $DistData -Force | Out-Null
foreach ($Name in $OfficialContextFiles) {
    $Source = Join-Path $Root "data\$Name"
    if (-not (Test-Path $Source)) {
        Write-Error "Missing required official context release file: $Source"
        exit 1
    }
    Copy-Item -Path $Source -Destination (Join-Path $DistData $Name) -Force
}

$HypothesisSource = Join-Path $Root "brain_alpha_ops\research\hypotheses"
$HypothesisTarget = Join-Path $Root "dist\brain_alpha_ops\research\hypotheses"
if (-not (Test-Path $HypothesisSource)) {
    Write-Error "Missing required hypothesis library release directory: $HypothesisSource"
    exit 1
}
New-Item -ItemType Directory -Path $HypothesisTarget -Force | Out-Null
Copy-Item -Path (Join-Path $HypothesisSource "*") -Destination $HypothesisTarget -Recurse -Force

$PromptSource = Join-Path $Root "brain_alpha_ops\research\prompts"
$PromptTarget = Join-Path $Root "dist\brain_alpha_ops\research\prompts"
if (-not (Test-Path $PromptSource)) {
    Write-Error "Missing required assistant prompt template directory: $PromptSource"
    exit 1
}
New-Item -ItemType Directory -Path $PromptTarget -Force | Out-Null
Copy-Item -Path (Join-Path $PromptSource "*") -Destination $PromptTarget -Recurse -Force

Write-Host ""
Write-Host "Copied official context files to $DistData"
Write-Host "Copied hypothesis library files to $HypothesisTarget"
Write-Host "Copied assistant prompt template files to $PromptTarget"
Write-Host "Done: $Root\dist\BrainAlphaOps.exe"
Write-Host "The executable starts the local service in a console and opens the browser UI automatically."
