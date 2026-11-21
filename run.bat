@echo off
cd /d "%~dp0"
py -3.12 app.py
if errorlevel 1 (
  echo The app could not start. Copy the error message to diagnose it.
  pause
)
