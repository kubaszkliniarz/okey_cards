@echo off
REM Build OkeyCardGame.exe (Windows)
REM Run this once: pip install pyinstaller
pyinstaller --onefile --windowed --name OkeyCardGame ^
  --add-data "okey_logic;okey_logic" ^
  --add-data "okey_gui;okey_gui" ^
  main.py
echo.
echo Build complete. Find OkeyCardGame.exe in the dist\ folder.
pause
