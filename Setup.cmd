@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" -LocalSource "%~dp0."
if errorlevel 1 pause
