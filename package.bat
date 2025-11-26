@echo off
setlocal

REM Setup and build script
echo Starting build process...

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Create virtual environment if needed
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        exit /b 1
    )
)

REM Install requirements
if exist "requirements.txt" (
    echo Installing dependencies...
    call .venv\Scripts\python -m pip install --upgrade pip
    call .venv\Scripts\pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install requirements
        exit /b 1
    )
)

REM Build with pyinstaller
echo Building executable...
.venv\Scripts\python -m PyInstaller --onefile --clean weibo.py --add-data "logging.conf;." --add-data "config.json;."
if errorlevel 1 (
    echo Error: Build failed
    exit /b 1
)

echo Build completed successfully!
echo Executable location: dist\weibo.exe

endlocal