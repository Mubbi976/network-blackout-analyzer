@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Video-Clipper.ps1"
if errorlevel 1 pause
