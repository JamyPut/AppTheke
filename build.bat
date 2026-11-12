@echo off
rem Builds the portable AppTheke.exe, with an app icon and a splash screen.
rem Run from the project folder, with the virtual environment active:
rem     .venv\Scripts\activate
rem     build.bat
rem
rem Needs two pictures in this project:
rem     splash.png        the start-up splash: a PNG, at most 760 x 480 pixels
rem     assets\icon.ico   the app icon (make it from assets\icon.png with: python tools\make_icon.py)

if not exist splash.png (
    echo splash.png was not found in this folder.
    echo Save your splash picture as a PNG named splash.png here, then run this again.
    exit /b 1
)

if not exist assets\icon.ico (
    echo assets\icon.ico was not found.
    echo Run:  python tools\make_icon.py   and then run this again.
    exit /b 1
)

pyinstaller --noconfirm --clean --onefile --windowed --splash splash.png --icon assets\icon.ico --add-data "assets\icon.ico;assets" --name AppTheke --collect-all customtkinter main.py

if errorlevel 1 (
    echo.
    echo Build failed. Read the messages above.
    exit /b 1
)

echo.
echo Done. Your program is: dist\AppTheke.exe
