# Okey Card Solver

A strategy advisor for the Okey card mini-game (as found in Metin2 and similar games).
You play the real game on another device; this tool tells you exactly what to do.

## How it works

- Use the **card picker grid** to enter the 5 cards you currently see in the real game
- The AI solver analyses all valid combos, near-combos, and draw probabilities using exact hypergeometric statistics
- It recommends whether to **play a combo now**, **keep a pair and redraw**, or **draw fresh**
- The solver tracks every card seen across the full session so probabilities stay accurate as the deck shrinks

### Scoring rules

| Combination | Formula | Range |
|---|---|---|
| Run · same colour (e.g. Y6 Y7 Y8)   | 40 + 10 × (max number − 2) | 50 … 100 |
| Run · mixed colours (e.g. Y1 R2 B3) | 10 × lowest number         | 10 …  60 |
| Set · all 3 colours (e.g. Y5 R5 B5) | 10 × (number + 1)          | 20 …  90 |

Matches the open-sourced game clone this tool is built to solve.

## Running locally

Requires Python ≥ 3.10. No third-party packages needed (`tkinter` ships with Python).

```bash
python main.py
```

## Building a standalone executable

### macOS (.app)
```bash
pip install pyinstaller
./build_mac.sh
# → dist/OkeyCardGame.app  (double-click in Finder; right-click → Open to bypass Gatekeeper)
```

### Windows (.exe) — built automatically via GitHub Actions

1. Push this repo to GitHub
2. Go to **Actions → Build Windows EXE → Run workflow**
3. Download `OkeyCardGame.exe` from the **Artifacts** section

Or on a Windows machine directly:
```bat
pip install pyinstaller
build_exe.bat
rem → dist\OkeyCardGame.exe
```

## Project structure

```
okey_logic/
  game.py      Card definitions, scoring rules
  session.py   Session state: hand, stack, seen cards, remaining deck
  solver.py    Probability engine: hypergeometric EVs, two-pair analysis, recommendations
okey_gui/
  widgets.py   Reusable tkinter widgets and colour palette
  window.py    Main application window
main.py        Entry point
.github/
  workflows/
    build-exe.yml   CI: builds Windows .exe on every push to main
pyproject.toml      Project metadata and tool config
build_mac.sh        macOS build script
build_exe.bat       Windows build script
```

## License
MIT
