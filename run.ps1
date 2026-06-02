# ============================================================
#  PROTACTICS — Arranque local (PostgreSQL nativo, sin Docker)
#  Uso:  powershell -ExecutionPolicy Bypass -File run.ps1
# ============================================================
# No usar "Stop": psql/createdb escriben en stderr de forma benigna y abortarían el arranque.
$ErrorActionPreference = "Continue"

$PgBin   = "C:\Program Files\PostgreSQL\18\bin"
$PgData  = "C:\Users\admin\protactics_pgdata"
$PgPort  = 5433
$PgPass  = "TopDeveloper123!@#"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv    = Join-Path $Project "backend\.venv\Scripts\python.exe"

# La autenticación de PostgreSQL requiere contraseña (scram-sha-256).
# psql / createdb la toman de esta variable para no pedirla interactivamente.
$env:PGPASSWORD = $PgPass

# 1) Arrancar el cluster de PostgreSQL si no está corriendo
$status = & "$PgBin\pg_ctl.exe" -D $PgData status 2>&1
if ($status -match "no server running") {
    Write-Host "Iniciando PostgreSQL en el puerto $PgPort..." -ForegroundColor Cyan
    & "$PgBin\pg_ctl.exe" -D $PgData -l "$PgData\server.log" -o "-p $PgPort" start
    Start-Sleep 3
} else {
    Write-Host "PostgreSQL ya esta corriendo." -ForegroundColor Green
}

# 2) Asegurar que la base de datos 'protactics' existe
$exists = (& "$PgBin\psql.exe" -h 127.0.0.1 -p $PgPort -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='protactics'" 2>$null | Out-String).Trim()
if ($exists -notmatch "1") {
    Write-Host "Creando base de datos 'protactics'..." -ForegroundColor Cyan
    & "$PgBin\createdb.exe" -h 127.0.0.1 -p $PgPort -U postgres protactics 2>$null
}

# 3) Liberar el puerto 8000 si quedó un backend anterior ocupándolo
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "Puerto 8000 ocupado por un backend anterior - cerrandolo..." -ForegroundColor Yellow
    $busy | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep 2
}

# 4) Arrancar el backend FastAPI apuntando a PostgreSQL
# Contraseña 'TopDeveloper123!@#' codificada para URL: ! -> %21, @ -> %40, # -> %23
$env:DATABASE_URL = "postgresql://postgres:TopDeveloper123%21%40%23@127.0.0.1:$PgPort/protactics"
$env:PYTHONUNBUFFERED = "1"
Set-Location (Join-Path $Project "backend")

Write-Host ""
Write-Host "  Backend:   http://127.0.0.1:8000/"        -ForegroundColor Yellow
Write-Host "  API docs:  http://127.0.0.1:8000/docs"    -ForegroundColor Yellow
Write-Host "  DB:        $env:DATABASE_URL"             -ForegroundColor DarkGray
Write-Host "  (Ctrl+C para detener el backend)"        -ForegroundColor DarkGray
Write-Host ""

& $Venv -m uvicorn main:app --host 127.0.0.1 --port 8000
