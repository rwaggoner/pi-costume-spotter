@echo off
rem Update, rebuild and restart the Costume Spotter (edge\deploy\windows\update.ps1).
rem Double-click it, or run "update.cmd -NoPull" etc. from a terminal.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0edge\deploy\windows\update.ps1" %*
if errorlevel 1 pause
