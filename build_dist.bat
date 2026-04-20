@echo off
echo ==============================================
echo Flash Drive Fraud Fixer - Windows Build Script
echo ==============================================
echo.

echo Installing PyInstaller...
pip install pyinstaller

echo.
echo Building standalone EXE...
pyinstaller --onefile --windowed --name "F3 Flash Fixer" --icon NONE --clean "Flash Drive Fraud Fixer .py"

echo.
echo ==============================================
echo Build completed!
echo Output file: dist\F3 Flash Fixer.exe
echo ==============================================
echo.
echo This EXE is completely standalone, no Python required.
echo It will run on any Windows 10/11 machine.
echo Right click -> Run as Administrator for best functionality.
echo.
pause