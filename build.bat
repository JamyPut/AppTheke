@echo off
rem Builds the portable AppTheke.exe.
rem Run from the project folder, with the virtual environment active:
rem     .venv\Scripts\activate
rem     build.bat

pyinstaller --noconfirm --clean --onefile --windowed --name AppTheke --collect-all customtkinter main.py

if errorlevel 1 (
    echo.
    echo Build failed. Read the messages above.
    exit /b 1
)

echo.
echo Done. Your program is: dist\AppTheke.exe
