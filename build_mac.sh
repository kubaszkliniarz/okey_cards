#!/bin/bash
# Build OkeyCardGame.app (macOS)
# Run once: pip3 install pyinstaller
pyinstaller --onefile --windowed --name OkeyCardGame \
  --add-data "okey_logic:okey_logic" \
  --add-data "okey_gui:okey_gui" \
  main.py

echo ""
echo "Build complete. Find OkeyCardGame.app in the dist/ folder."
