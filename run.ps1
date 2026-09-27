# ==============================================================================
# Autonomous Self-Healing Network Simulator - Single Command Launcher
# Usage: .\run.ps1
# ==============================================================================

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Root) { $Root = (Get-Location).Path }
$FrontendDir = Join-Path $Root "frontend"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " [SIMULATOR] Autonomous Self-Healing Network Simulator Launcher" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Check Python Virtual Environment
$PythonExe = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[!] Virtual environment not found at .\venv. Creating now..." -ForegroundColor Yellow
    & python -m venv (Join-Path $Root "venv")
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $Root "requirements.txt")
}
Write-Host "[OK] Python Environment: $PythonExe" -ForegroundColor Green

# 2. Check ML Models & Artifacts
$ModelPath = Join-Path $Root "data\models\rf.pkl"
if (-not (Test-Path $ModelPath)) {
    Write-Host "[*] ML models not found. Running training pipeline..." -ForegroundColor Yellow
    & $PythonExe -m ml_engine.train_pipeline
}
Write-Host "[OK] ML Models and Artifacts Verified" -ForegroundColor Green

# 3. Check Frontend Dependencies & Production Build
$NodeModules = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "[*] Frontend dependencies missing. Running npm install..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    npm install
    Pop-Location
}
Write-Host "[OK] Frontend Dependencies Verified" -ForegroundColor Green

# 4. Start Backend Server (FastAPI + WebSocket Bridge)
# Note: Using -WorkingDirectory avoids all path-with-spaces and quote-escaping bugs!
Write-Host "[*] Starting FastAPI Backend on http://localhost:8000..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $Root -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe -m uvicorn frontend.bridge_server:app --host 0.0.0.0 --port 8000 --reload"

# 5. Start Frontend Dev Server (Vite)
Write-Host "[*] Starting React Frontend Dev Server on http://localhost:5173..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $FrontendDir -ArgumentList "-NoExit", "-Command", "npm run dev"

# 6. Wait briefly for servers to start listening, then open browser
Write-Host "[*] Waiting for servers to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

$TargetUrl = "http://localhost:5173"
Write-Host "[*] Opening browser at $TargetUrl..." -ForegroundColor Green
Start-Process $TargetUrl

Write-Host "==================================================================" -ForegroundColor Green
Write-Host " [SUCCESS] System Launched Successfully!" -ForegroundColor Green
Write-Host " - Dev Web UI:   http://localhost:5173" -ForegroundColor White
Write-Host " - Prod Web UI:  http://localhost:8000" -ForegroundColor White
Write-Host " - REST API:     http://localhost:8000/api/topology" -ForegroundColor White
Write-Host " - WebSocket:    ws://localhost:8000/ws/events" -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Green
