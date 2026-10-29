@echo off
rem Starts the Offshore Wind Studio server and opens the interface in the browser.
rem Development only (the installed application opens its own window). Simulations need a
rem compute profile (Compute > Install an engine).
cd /d "%~dp0"
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
backend\.venv\Scripts\python.exe -m owstudio serve
