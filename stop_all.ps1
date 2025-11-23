# ============================
# A.I.N.D.Y. Stop-All Script (Safe ASCII)
# ============================

Write-Host ""
Write-Host "=== Stopping all A.I.N.D.Y. background jobs ===" -ForegroundColor Cyan

# Step 1: Check running jobs
$jobs = Get-Job
if ($jobs) {
    Write-Host "Stopping running jobs..." -ForegroundColor Yellow
    $jobs | Stop-Job
    $jobs | Remove-Job
    Write-Host "All jobs stopped successfully." -ForegroundColor Green
} else {
    Write-Host "No active background jobs found." -ForegroundColor Yellow
}

# Step 2: Check for Python (uvicorn) and Node processes just in case
Write-Host "Checking for stray processes..." -ForegroundColor Yellow
$pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
$nodeProcs = Get-Process -Name "node" -ErrorAction SilentlyContinue

if ($pythonProcs) {
    $pythonProcs | Stop-Process -Force
    Write-Host "Stopped Python/Uvicorn processes." -ForegroundColor Green
}

if ($nodeProcs) {
    $nodeProcs | Stop-Process -Force
    Write-Host "Stopped Node processes." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== All services have been stopped. ===" -ForegroundColor Cyan
