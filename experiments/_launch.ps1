$env:PYTHONUNBUFFERED = "1"
if (-not $env:BRAIN_USERNAME -or -not $env:BRAIN_PASSWORD) {
    throw "Set BRAIN_USERNAME and BRAIN_PASSWORD in your shell before running this experiment launcher."
}
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = "D:\Works\WorldQuant BRAIN Alpha\experiments\experiment_100c_$ts.log"
Write-Output "=== Launch at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
C:\Users\54782\.workbuddy\binaries\python\versions\3.14.3\python.exe -u D:\Works\WorldQuant BRAIN Alpha\experiments\run.py --candidates 100 *> $logFile
