$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv/Scripts/python.exe)) { throw 'Run Setup.cmd first to install the studio.' }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location frontend
try {
    if (-not (Test-Path node_modules)) {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Dependency restore failed. Rerun Setup.cmd.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally {
    Pop-Location
}
& .\.venv\Scripts\python.exe -m scripts.launch
