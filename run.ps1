# ============================================================
#  PROTACTICS — Arranque local (SQLite, sin PostgreSQL ni Docker)
#  Uso:  powershell -ExecutionPolicy Bypass -File run.ps1
#
#  La app usa SQLite por defecto (backend\protactics.db) cuando
#  DATABASE_URL no está definida. Para usar PostgreSQL, define
#  $env:DATABASE_URL antes de ejecutar este script.
# ============================================================
$ErrorActionPreference = "Stop"

$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv    = Join-Path $Project "backend\.venv\Scripts\python.exe"

# 1) Verificar que el entorno virtual existe
if (-not (Test-Path $Venv)) {
    Write-Host "No se encontró el entorno virtual en backend\.venv" -ForegroundColor Red
    Write-Host "Créalo con (usa tu intérprete de Python 3.12):" -ForegroundColor Yellow
    Write-Host '    python -m venv backend\.venv' -ForegroundColor Gray
    Write-Host '    backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt' -ForegroundColor Gray
    exit 1
}

# 2) Liberar el puerto 8000 si quedó un backend anterior ocupándolo
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "Puerto 8000 ocupado por un backend anterior - cerrandolo..." -ForegroundColor Yellow
    $busy | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2
}

# 3) Arrancar el backend FastAPI (SQLite por defecto)
$env:PYTHONUNBUFFERED = "1"
Set-Location (Join-Path $Project "backend")

$dbMsg = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "sqlite:///./protactics.db (local)" }

Write-Host ""
Write-Host "  App:       http://127.0.0.1:8000/"        -ForegroundColor Yellow
Write-Host "  API docs:  http://127.0.0.1:8000/docs"    -ForegroundColor Yellow
Write-Host "  DB:        $dbMsg"                         -ForegroundColor DarkGray
Write-Host "  (Ctrl+C para detener el backend)"         -ForegroundColor DarkGray
Write-Host ""

& $Venv -m uvicorn main:app --host 127.0.0.1 --port 8000
