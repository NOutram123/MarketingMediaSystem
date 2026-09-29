param([Parameter(Mandatory=$true)][ValidateSet('comfy','ffmpeg')][string]$Action, [string]$ComfyDirectory, [switch]$Worker)
$ErrorActionPreference = 'Stop'
if ($Action -eq 'ffmpeg') {
    & winget.exe install --exact --id Gyan.FFmpeg --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'FFmpeg installation did not finish. Install through winget or rerun Setup.cmd.' }
    exit 0
}
$configPath = Join-Path $env:USERPROFILE '.pinokio\config.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Install and open Pinokio first, choose its home folder, then retry.' }
$pinokioConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$pinokioDirectory = [IO.Path]::GetFullPath($pinokioConfig.home)
if ($pinokioDirectory -match '[&|<>^%"`\r\n]') { throw 'Use a Pinokio home path without shell metacharacters.' }
$ptermExecutable = Join-Path $pinokioDirectory 'bin\npm\pterm.cmd'
if (-not (Test-Path -LiteralPath $ptermExecutable)) { throw 'Open Pinokio and finish its initial tools setup, then retry.' }
if ($Worker) { $ComfyDirectory = $env:MMS_COMFY_LAUNCH_DIRECTORY }
if (-not $ComfyDirectory) { $ComfyDirectory = Join-Path $pinokioDirectory 'api\comfy.git' }
if ($ComfyDirectory -match '[&|<>^%"`\r\n]') { throw 'Use a ComfyUI path without shell metacharacters.' }
if (-not (Test-Path -LiteralPath $comfyDirectory)) {
    & $ptermExecutable download 'https://github.com/pinokiofactory/comfy.git' 'comfy.git'
    if ($LASTEXITCODE -ne 0) { throw 'ComfyUI download failed. Check the Pinokio terminal.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $comfyDirectory 'pinokio.js'))) { throw 'The existing comfy.git folder is not a recognised launcher; preserve it and inspect it in Pinokio.' }
# The launcher's menu selects install when uninstalled, or start when installed.
if ($Worker) {
    & $ptermExecutable run $ComfyDirectory --default start.js --default install.js
    exit $LASTEXITCODE
}
$appName = Split-Path $ComfyDirectory -Leaf
$statusText = & $ptermExecutable status $appName
if ($LASTEXITCODE -ne 0) { throw 'Pinokio is unavailable. Open it and finish its initial setup, then retry.' }
$appStatus = $statusText | ConvertFrom-Json
if (-not $appStatus.running) {
    # pterm remains attached to a daemon for its lifetime. Keep that session hidden,
    # independently of the studio request; readiness is checked through ComfyUI.
    $env:MMS_COMFY_LAUNCH_DIRECTORY = $ComfyDirectory
    $logDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) 'data\setup'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = [Guid]::NewGuid().ToString('N')
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),'-Action','comfy','-Worker') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory "$stamp.out.log") -RedirectStandardError (Join-Path $logDirectory "$stamp.err.log") | Out-Null
}
Write-Output 'ComfyUI dispatched to Pinokio. Follow installation progress there; start it after installation if needed, then check readiness in the studio.'
