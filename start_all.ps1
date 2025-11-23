# ============================
# A.I.N.D.Y. Unified Startup Script (Safe ASCII)
# ============================

Write-Host ""
Write-Host "=== Starting A.I.N.D.Y. Multi-Service Environment ===" -ForegroundColor Cyan

# Step 1: Activate Python Virtual Environment
Write-Host "Activating Python venv..." -ForegroundColor Yellow
Set-Location "C:\Users\world\OneDrive\Documents\A.I.N.D.Y"
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Host "No venv found. Creating one..." -ForegroundColor Red
    python -m venv venv
    & "venv\Scripts\Activate.ps1"
    pip install -r requirements.txt
}

# Step 2: Start FastAPI (A.I.N.D.Y.)
Write-Host "Starting A.I.N.D.Y. backend on port 8000..." -ForegroundColor Green
Start-Job -ScriptBlock { uvicorn main:app --reload --port 8000 }
Start-Sleep -Seconds 3
Write-Host "A.I.N.D.Y. backend running at http://127.0.0.1:8000"

# Step 3: Start Node Bridge
Write-Host "Starting Node Bridge (Infinite Network backend)..." -ForegroundColor Green
Start-Job -ScriptBlock { node server.js }
Start-Sleep -Seconds 2
Write-Host "Node Bridge running at http://127.0.0.1:5000"

# Step 4: Start React Client (if folder exists)
if (Test-Path "client") {
    Write-Host "Starting React Client..." -ForegroundColor Green
    Start-Job -ScriptBlock { Set-Location client; npm run dev }
    Start-Sleep -Seconds 5
    Write-Host "React client available at http://127.0.0.1:5173"
} else {
    Write-Host "React client folder not found -- skipping frontend start." -ForegroundColor Yellow
}

# Final Summary
Write-Host ""
Write-Host "=== All systems online ===" -ForegroundColor Cyan
Write-Host "A.I.N.D.Y. API:      http://127.0.0.1:8000"
Write-Host "Node Bridge:         http://127.0.0.1:5000"
Write-Host "React Frontend:      http://127.0.0.1:5173"
Write-Host ""
Write-Host 'To view running jobs:  Get-Job'
Write-Host 'To stop all jobs:     Get-Job ^| Stop-Job ^| Remove-Job'
