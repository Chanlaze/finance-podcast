param([string]$VideoId)
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
    $syncArgs = @('--limit', '3', '--publish')
    if ($VideoId) { $syncArgs += @('--video-id', $VideoId) }
    $ErrorActionPreference = 'Continue'
    & "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\local_sync.py" @syncArgs *> $log
    $syncExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($syncExit -ne 0) { throw "Sync failed; see $log" }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
