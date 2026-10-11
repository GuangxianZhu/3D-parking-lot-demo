@echo off
rem One-click launcher for Windows: double-click this file.
rem First run: creates .venv next to this file and installs requirements.txt.
rem Later runs: skips straight to main.py.
rem Messages are ASCII on purpose: cmd.exe reads .bat files in the console
rem code page, so Chinese text here would show up garbled on many systems.
setlocal
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto deps

rem Find Python 3.8+. Try the "py" launcher first, then "python".
rem The version check also rejects the Microsoft Store stub python.exe,
rem which exists on PATH but is not a real interpreter.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.8 or newer was not found.
    echo Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup, then run this file again.
    goto fail
)

echo Creating virtual environment in .venv ...
%PY% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    goto fail
)

:deps
"%VENV_PY%" -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 goto run
echo Installing dependencies (first run only, needs internet) ...
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your network or proxy, then run again.
    echo If it says no matching distribution for panda3d, your Python version
    echo is too new or too old: install Python 3.12 or 3.13, delete .venv, run again.
    goto fail
)

:run
echo Starting the demo. A 3D window will open; close it to quit.
"%VENV_PY%" main.py
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
pause
exit /b 1
