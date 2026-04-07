@echo off
setlocal
set "PYTHON_EXE=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python 3.12 environment not found at "%PYTHON_EXE%"
  exit /b 1
)
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
echo Launching Job Bot for first-run configuration...
"%PYTHON_EXE%" main.py
endlocal
