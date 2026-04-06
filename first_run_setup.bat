@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Launching Job Bot for first-run configuration...
python main.py
endlocal
