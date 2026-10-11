@echo off
rem One-click launcher for Windows: double-click this file.
rem First run: creates .venv next to this file and installs requirements.txt.
rem Every run: pulls the latest code first if git is installed.
rem Later runs: skips straight to main.py.
rem Messages are ASCII on purpose: cmd.exe reads .bat files in the console
rem code page, so Chinese text here would show up garbled on many systems.
setlocal
cd /d "%~dp0"

rem Update to the latest code with "git pull" when this is a git checkout.
rem cmd.exe reads a running .bat file line by line from disk, so if the pull
rem changes this file, the rest of it would be read at the wrong offsets.
rem The pull and the restart are therefore on one line (parsed as a whole),
rem and the restarted copy skips this step via PARKING_UPDATED.
if defined PARKING_UPDATED goto venv
if not exist ".git" goto venv
where git >nul 2>&1
if errorlevel 1 goto venv
set "PARKING_UPDATED=1"
echo Updating to the latest version (git pull) ...
(git pull --ff-only || echo [WARN] Update failed, starting the version you have.) & call "%~f0" %* & exit /b

:venv

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
if errorlevel 1 goto crashed
exit /b 0

:crashed
rem Not inside a ( ) block: the folder path may contain ")" and would end it.
echo [ERROR] The demo stopped with an error. Please send the newest file
echo in the logs folder: %~dp0logs

:fail
echo.
pause
exit /b 1
