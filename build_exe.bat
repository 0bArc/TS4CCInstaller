@echo off
setlocal
cd /d "%~dp0"

python -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean CCInstaller.spec
if errorlevel 1 exit /b 1

echo.
echo Built: dist\CCInstaller.exe
powershell -NoProfile -Command "(Get-Item dist\CCInstaller.exe).Length / 1MB"
echo Double-click that file to run. Preferences write to %%APPDATA%%\CCInstaller.
endlocal
