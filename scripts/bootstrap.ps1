[CmdletBinding()]
param(
    [string]$RepositoryUrl = 'https://github.com/NOutram123/MarketingMediaSystem.git',
    [string]$Ref = 'main',
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'MarketingMediaSystem'),
    [string]$LocalSource,
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
function Install-Package([string]$Id) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'Install Microsoft App Installer from the Microsoft Store, then run Setup.cmd again (winget is required).'
    }
    & winget.exe install --exact --id $Id --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Installation of $Id did not complete. Follow the installer instructions and rerun setup." }
    Refresh-Path
}
if ([Environment]::OSVersion.Version.Build -lt 22000) { throw 'Windows 11 or later is required.' }
if (-not $LocalSource -and $RepositoryUrl -notmatch '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$') {
    throw 'Use an HTTPS GitHub repository URL without embedded credentials.'
}
if ($Ref.StartsWith('-')) { throw 'Invalid release/branch name.' }
Write-Host 'Marketing Media System - preparing prerequisites. Keep this window open.'
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { Install-Package 'Git.Git' }
$pythonReady = $false
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3.11 -c 'import sys; assert sys.version_info[:2] == (3,11)' 2>$null
    $pythonReady = ($LASTEXITCODE -eq 0)
}
if (-not $pythonReady) { Install-Package 'Python.Python.3.11' }
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { Install-Package 'OpenJS.NodeJS.LTS' }
$nodeMajor = & node.exe -p 'parseInt(process.versions.node)'
if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 24) { throw 'Install Node.js 24 LTS (nodejs.org), reopen this terminal, and run setup again.' }
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    # Pinokio may already provide these; bootstrap does not overwrite that installation.
    $ffmpegInPinokio = $false
    $configPath = Join-Path $env:USERPROFILE '.pinokio\config.json'
    if (Test-Path -LiteralPath $configPath) {
        $pinokioConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($pinokioConfig.home) { $ffmpegInPinokio = Test-Path -LiteralPath (Join-Path $pinokioConfig.home 'bin\ffmpeg-env\Library\bin\ffprobe.exe') }
    }
    if (-not $ffmpegInPinokio) { Install-Package 'Gyan.FFmpeg' }
}
if ($LocalSource) {
    $projectDirectory = (Resolve-Path -LiteralPath $LocalSource).Path
} else {
    $projectDirectory = [IO.Path]::GetFullPath($InstallDirectory)
    if (Test-Path -LiteralPath $projectDirectory) {
        throw 'Destination already exists. Run its Setup.cmd to repair it, or select an empty installation directory. No files were changed there.'
    }
    & git.exe clone --branch $Ref --single-branch -- $RepositoryUrl $projectDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Repository download failed. Check its URL, release and your GitHub access.' }
}
Set-Location -LiteralPath $projectDirectory
if (-not (Test-Path -LiteralPath 'backend\requirements.lock.txt')) { throw 'The selected directory is not a Marketing Media System source folder.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
foreach ($folder in @('data','data\projects','data\setup','data\models\kokoro','data\models\whisper','data\benchmarks','backups')) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & py.exe -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed. Install Python 3.11 including its py launcher and retry.' }
}
& .\.venv\Scripts\python.exe -c 'import sys; assert sys.version_info[:2] == (3,11), "Existing environment requires Python 3.11"'
if ($LASTEXITCODE -ne 0) { throw 'Existing .venv uses an incompatible Python. Move it aside manually before rerunning setup.' }
& .\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check connectivity and retry; existing projects are preserved.' }
Push-Location frontend
try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host "Installed at $projectDirectory. Use Launch.cmd next time. Setup continues in your browser."
if (-not $NoLaunch) { & (Join-Path $projectDirectory 'scripts\start.ps1') }
