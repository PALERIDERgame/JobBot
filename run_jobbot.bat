@echo off
setlocal

set "VENV_PYTHON=%~dp0.venv312\Scripts\pythonw.exe"

if not exist "%VENV_PYTHON%" (
    echo Python 3.12 GUI environment not found at:
    echo %VENV_PYTHON%
    echo.
    echo Recreate it first, or ask Codex to set it up again.
    pause
    exit /b 1
)

start "" "%VENV_PYTHON%" "%~dp0launcher.pyw"

endlocal
