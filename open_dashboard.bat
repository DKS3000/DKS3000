@echo off
REM One-click dashboard opener for Windows.
REM
REM Usage:
REM   1) Drag a captured .jsonl session log (copied from the Pi) onto this
REM      file, OR just double-click it and paste the path when asked.
REM   2) It builds the markdown + HTML report and opens the dashboard in
REM      your default browser.
REM
REM Only needs a plain Python install (python.org) - no extra packages,
REM since report generation uses the standard library only.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "LOGFILE=%~1"
if "%LOGFILE%"=="" (
    echo Drag a .jsonl session log onto this file next time to skip this prompt.
    set /p LOGFILE="Path to .jsonl session log: "
)

REM Strip any surrounding quotes the user may have pasted.
set "LOGFILE=%LOGFILE:"=%"

if not exist "%LOGFILE%" (
    echo.
    echo Could not find: %LOGFILE%
    pause
    exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYCMD=python"
    ) else (
        echo.
        echo Python was not found on PATH. Install it from https://python.org
        echo ^(check "Add python.exe to PATH" during setup^) and try again.
        pause
        exit /b 1
    )
)

if not exist "reports" mkdir "reports"
for %%F in ("%LOGFILE%") do set "BASENAME=%%~nF"

echo.
echo Building dashboard from %LOGFILE% ...
%PYCMD% -m rf_sniffer report --log "%LOGFILE%" --out "reports\%BASENAME%.md" --html "reports\%BASENAME%.html" --open

if errorlevel 1 (
    echo.
    echo Something went wrong generating the report - see the error above.
    pause
    exit /b 1
)

echo.
echo Done. Dashboard: reports\%BASENAME%.html
pause
