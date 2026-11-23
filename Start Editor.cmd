@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" wallpaper_editor.py
) else (
  py -3.14 wallpaper_editor.py
)
if errorlevel 1 (
  echo.
  echo Editor could not start. See the error above and README.md.
  pause
)
