@echo off
title O-SAVS
cd /d "%~dp0"

if exist "..\requirements.txt" (
    echo Installing requirements...
    py -m pip install -U -r "..\requirements.txt" --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo Failed to install requirements. See the error above.
        pause
        exit /b 1
    )
) else (
    echo requirements.txt not found in parent folder, skipping install.
)

py bot.py %*
pause
