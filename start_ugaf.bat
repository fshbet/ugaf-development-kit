@echo off
setlocal

rem Always run from this script's own directory, regardless of where
rem it was launched from (double-click, shortcut, another shell, etc.).
cd /d "%~dp0"

set PORT=8420

echo ============================================
echo  UGAF Control Panel
echo ============================================

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo Using virtual environment: .venv
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: No .venv found and no "python" on PATH.
        echo Create a virtual environment first, e.g.:
        echo     python -m venv .venv
        echo     .venv\Scripts\pip install -e ".[dev,input,imaging,vision,webapp]"
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo No .venv found - using system Python on PATH.
)

echo Checking for connected Android devices...
where adb >nul 2>nul
if errorlevel 1 (
    echo   adb not found on PATH - device detection may not work
    echo   until the Android SDK platform-tools folder is on PATH.
) else (
    adb devices
)

echo.
echo Starting web control panel on http://127.0.0.1:%PORT%
echo Press Ctrl+C in this window to stop the server.
echo.

rem Open the browser a couple seconds after launch, once the server is
rem actually listening, without blocking server startup itself.
start "" /min cmd /c "timeout /t 2 >nul & start http://127.0.0.1:%PORT%"

"%PYTHON%" -m ugaf.webapp --port %PORT%

echo.
echo Server stopped.
pause
endlocal
