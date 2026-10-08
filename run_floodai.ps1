$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "        FloodAI Local Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Starting FloodAI Docker services..." -ForegroundColor Yellow

docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Compose failed to start." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Waiting for FloodAI API..." -ForegroundColor Yellow

$healthy = $false

for ($i = 1; $i -le 30; $i++) {
    try {
        $response = Invoke-WebRequest `
            -Uri "http://localhost:8000/api/health" `
            -UseBasicParsing `
            -TimeoutSec 3

        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }

    Start-Sleep -Seconds 1
}

if (-not $healthy) {
    Write-Host ""
    Write-Host "FloodAI API did not become healthy within the expected time." -ForegroundColor Red
    Write-Host ""
    docker compose ps
    exit 1
}

Write-Host ""
Write-Host "FloodAI API is healthy." -ForegroundColor Green
Write-Host ""

Write-Host "Opening FloodAI dashboard..." -ForegroundColor Yellow

Start-Process "http://localhost:8000/"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "FloodAI is running." -ForegroundColor Green
Write-Host "Dashboard : http://localhost:8000/" -ForegroundColor Green
Write-Host "Prometheus: http://localhost:9090/" -ForegroundColor Green
Write-Host "Grafana   : http://localhost:3000/" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Use 'docker compose down' to stop the services." -ForegroundColor DarkGray