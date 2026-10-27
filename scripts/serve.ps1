param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$WebPort = 3000,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$virtualPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonExecutable = if (Test-Path -LiteralPath $virtualPython) { $virtualPython } else { (Get-Command python -ErrorAction Stop).Source }
$npmExecutable = (Get-Command npm.cmd -ErrorAction Stop).Source
$logDirectory = Join-Path $projectRoot '.sentinel'
$apiProcess = $null
$previousApiUrl = $env:SENTINEL_API_URL
$previousTelemetry = $env:NEXT_TELEMETRY_DISABLED
$previousCorsOrigins = $env:SENTINEL_CORS_ORIGINS
$previousPort = $env:PORT

if ($ApiPort -eq $WebPort) { throw 'API and web ports must be different.' }
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

Push-Location $projectRoot
try {
    $env:SENTINEL_CORS_ORIGINS = ConvertTo-Json -InputObject @("http://localhost:$WebPort", "http://127.0.0.1:$WebPort") -Compress
    & $pythonExecutable -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    if (-not $SkipBuild) {
        & $npmExecutable run build
        if ($LASTEXITCODE -ne 0) { throw 'Production web build failed.' }
    }
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $ApiPort)
    try { $listener.Start() } finally { $listener.Stop() }
    $apiProcess = Start-Process -FilePath $pythonExecutable `
        -ArgumentList @('-m', 'uvicorn', 'backend.api.main:app', '--host', '127.0.0.1', '--port', "$ApiPort", '--no-access-log') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory 'api-output.log') `
        -RedirectStandardError (Join-Path $logDirectory 'api-error.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $apiProcess.Refresh()
        if ($apiProcess.HasExited) { throw "API exited. Inspect $logDirectory\api-error.log" }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $ready) { throw 'API did not become ready.' }
    $env:SENTINEL_API_URL = "http://127.0.0.1:$ApiPort"
    $env:NEXT_TELEMETRY_DISABLED = '1'
    $env:PORT = "$WebPort"
    Write-Host "SENTINEL production UI: http://127.0.0.1:$WebPort"
    Write-Host "Local AI is available when Ollama is running on the configured loopback URL."
    & $npmExecutable start
} finally {
    if ($null -ne $apiProcess) {
        $apiProcess.Refresh()
        if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id }
    }
    $env:SENTINEL_API_URL = $previousApiUrl
    $env:NEXT_TELEMETRY_DISABLED = $previousTelemetry
    $env:SENTINEL_CORS_ORIGINS = $previousCorsOrigins
    $env:PORT = $previousPort
    Pop-Location
}
