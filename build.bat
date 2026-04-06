@echo off
setlocal
python -m PyInstaller --noconfirm --clean jobbot.spec
endlocal
