@echo off
setlocal enabledelayedexpansion
title NFS:HPR Vinyl Modder - Setup

set "TOOL_DIR=%~dp0"
if "%TOOL_DIR:~-1%"=="\" set "TOOL_DIR=%TOOL_DIR:~0,-1%"

echo.
echo ============================================================
echo        NFS:HPR VINYL MODDER - SETUP AND INSTALLER
echo ============================================================
echo.

:: 1. Check Python
echo Checking for Python...
python --version >nul 2>&1
if errorlevel 1 goto :install_python

for /f "tokens=*" %%v in ('python --version') do echo [OK] %%v found.
goto :install_packages

:install_python
echo [!] Python not found. Downloading Python 3.12 installer...
curl.exe -L -o "%TEMP%\python-setup.exe" "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe"
if errorlevel 1 (
    echo [ERROR] Could not download Python. Please install it manually from python.org.
    pause
    exit /b 1
)
echo Installing Python 3.12 silently...
start /wait "" "%TEMP%\python-setup.exe" /quiet InstallAllUsers=0 PrependPath=1
del "%TEMP%\python-setup.exe" >nul 2>&1
echo [OK] Python installed. Please restart this script.
pause
exit /b 0

:install_packages
echo.
echo Checking required Python packages...
python -m pip install --quiet --upgrade pip >nul 2>&1

set "PACKAGES=customtkinter pillow tkinterdnd2 numpy"
for %%p in (%PACKAGES%) do (
    python -c "import %%p" >nul 2>&1
    if errorlevel 1 (
        echo   Installing %%p...
        python -m pip install --quiet %%p
    ) else (
        echo   [OK] %%p is already installed.
    )
)

:check_texconv
echo.
if not exist "%TOOL_DIR%\texconv.exe" (
    echo [!] texconv.exe not found. Downloading DirectXTex...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/microsoft/DirectXTex/releases/download/oct2025/texconv.exe' -OutFile '%TOOL_DIR%\texconv.exe'"
    if exist "%TOOL_DIR%\texconv.exe" (echo [OK] texconv.exe downloaded.) else (echo [WARNING] Failed to download texconv.exe.)
) else (
    echo [OK] texconv.exe found.
)

:create_shortcut
echo.
echo Creating Desktop shortcut...
set "SHORTCUT=%USERPROFILE%\Desktop\NFS HPR Vinyl Modder.lnk"
set "ICON=%TOOL_DIR%\icon.ico"
set "APP=%TOOL_DIR%\app.py"

powershell -NoProfile -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
    "$s.TargetPath = 'pythonw.exe';" ^
    "$s.Arguments = '\"%APP%\"';" ^
    "$s.WorkingDirectory = '%TOOL_DIR%';" ^
    "$s.IconLocation = '%ICON%';" ^
    "$s.Save()"
echo [OK] Shortcut created on Desktop.

echo.
echo ============================================================
echo   Setup complete! 
echo ============================================================
echo.
set /p LAUNCH="Launch the app now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    start "" pythonw.exe "%APP%"
)

pause
exit /b 0
