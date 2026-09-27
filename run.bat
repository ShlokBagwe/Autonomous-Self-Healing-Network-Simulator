@echo off
setlocal enabledelayedexpansion
title Autonomous Self-Healing Network Simulator Launcher

echo ==================================================================
echo  Autonomous Self-Healing Network Simulator Launcher
echo ==================================================================

cd /d "%~dp0"
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\venv\Scripts\python.exe" (
    echo [!] Virtual environment not found at .\venv. Creating now...
    python -m venv venv
    call "%ROOT%\venv\Scripts\pip.exe" install --upgrade pip
    call "%ROOT%\venv\Scripts\pip.exe" install -r requirements.txt
)
echo [OK] Python Environment Ready

if not exist "%ROOT%\data\models\rf.pkl" (
    echo [*] ML models not found. Running training pipeline...
    call "%ROOT%\venv\Scripts\python.exe" -m ml_engine.train_pipeline
)
echo [OK] ML Models Verified

if not exist "%ROOT%\frontend\node_modules" (
    echo [*] Frontend dependencies missing. Running npm install...
    cd /d "%ROOT%\frontend"
    call npm install
    cd /d "%ROOT%"
)
echo [OK] Frontend Dependencies Ready

echo [*] Starting FastAPI Backend on http://localhost:8000...
start "Backend (FastAPI)" /D "%ROOT%" cmd /k "venv\Scripts\python.exe -m uvicorn frontend.bridge_server:app --host 0.0.0.0 --port 8000 --reload"

echo [*] Starting React Frontend Dev Server on http://localhost:5173...
start "Frontend (Vite)" /D "%ROOT%\frontend" cmd /k "npm run dev"

echo [*] Waiting for servers to initialize...
timeout /t 4 /nobreak >nul

echo [*] Opening browser at http://localhost:5173...
start http://localhost:5173

echo ==================================================================
echo  [SUCCESS] System Launched Successfully!
echo  - Dev Web UI:   http://localhost:5173
echo  - Prod Web UI:  http://localhost:8000
echo ==================================================================
