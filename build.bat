@echo off
rem Builds the portable AppTheke.exe, with a splash screen while it starts.
rem Run from the project folder, with the virtual environment active:
rem     .venv\Scripts\activate
rem     build.bat
rem
rem Needs splash.png in this folder: a PNG picture, at most 760 x 480 pixels.

if not exist splash.png (
    echo splash.png was not found in this folder.
    echo Save your splash picture as a PNG named splash.png here, then run this again.
    exit /b 1
)

pyinstaller --noconfirm --clean --onefile --windowed --splash splash.png --name AppTheke --collect-all customtkinter main.py

if errorlevel 1 (
    echo.
    echo Build failed. Read the messages above.
    exit /b 1
)

echo.
echo Done. Your program is: dist\AppTheke.exe
