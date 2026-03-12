@echo off

set "VENV_NAME=.venv"
set "LAUNCH_DIR=%CD%"
set "SCRIPT_DIR=%~dp0"

echo The current directory is: %LAUNCH_DIR%
echo Script directory is: %SCRIPT_DIR%

cd /d "%SCRIPT_DIR%"

if DEFINED VIRTUAL_ENV (
    echo Python virtual environment used: "%VIRTUAL_ENV%"
) else (
    echo No Python virtual environment is currently enabled.
    if not exist "%VENV_NAME%\Scripts\activate.bat" (
        echo Creating python virtual environment: "%VENV_NAME%"
        python -m venv "%VENV_NAME%"
        if errorlevel 1 (
            echo Error: Failed to create python virtual environment. Exiting.
            exit /b 1
        )
        echo Activating python virtual environment: "%VENV_NAME%"
        call "%VENV_NAME%\Scripts\activate.bat"
        python.exe -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install windows-curses
        echo Python virtual environment created and enabled: "%VENV_NAME%"
    ) else (
        call "%VENV_NAME%\Scripts\activate.bat"
        echo Python virtual environment enabled: "%VENV_NAME%"
    )
)

cd /d "%LAUNCH_DIR%"
