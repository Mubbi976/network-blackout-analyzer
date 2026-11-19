$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$baseUrl = "http://127.0.0.1:8000"

try {
    $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
    if ($health.status -eq "ok") {
        Start-Process $baseUrl
        exit 0
    }
} catch {
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found. Follow the Setup instructions in README.md first."
}

$server = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $projectRoot `
    -PassThru

$deadline = (Get-Date).AddSeconds(60)
do {
    $server.Refresh()
    if ($server.HasExited) {
        throw "The Video Clipper server stopped during startup. Check the server window for details."
    }

    try {
        $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            Start-Process $baseUrl
            exit 0
        }
    } catch {
    }

    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

throw "The Video Clipper server did not become ready within 60 seconds. Check the server window for errors."
