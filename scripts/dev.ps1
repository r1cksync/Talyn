$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'backend')
try {
    python -m uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    python -m uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
} finally { Pop-Location }
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $backendRoot '.venv\Scripts\python.exe'
Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $backendRoot -WindowStyle Hidden
Push-Location $frontendRoot
try { npm ci --no-audit --no-fund; npm run dev } finally { Pop-Location }
