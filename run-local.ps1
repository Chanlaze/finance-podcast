$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$mutex = New-Object System.Threading.Mutex($false, 'Local\FinancePodcastSync')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { exit 0 }
    New-Item -ItemType Directory -Force logs | Out-Null
    $log = Join-Path $PSScriptRoot ('logs\sync-' + (Get-Date -Format 'yyyy-MM-dd-HHmmss') + '.log')
    & "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\local_sync.py" --limit 3 --publish *> $log
    if ($LASTEXITCODE -ne 0) { throw "Sync failed; see $log" }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
