@echo off
cd /d "%~dp0"
echo Building NEXUS FileSort 0.2 (English)...
py -3.12 --version
if errorlevel 1 goto no_python
py -3.12 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo PyInstaller not found. Installing it...
  py -3.12 -m pip install pyinstaller
  if errorlevel 1 goto error
)
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name "NEXUS_FileSort" app.py
if errorlevel 1 goto error
echo.
echo SUCCESS: dist\NEXUS_FileSort.exe
pause
exit /b 0
:no_python
echo Python 3.12 was not found. Please install Python 3.12 first.
pause
exit /b 1
:error
echo Build failed. Copy the error message and ask for help.
pause
exit /b 1
