"""
Okey Solver — entry point.

To build a standalone executable:
  Mac:     ./build_mac.sh         →  dist/OkeyCardGame.app
  Windows: build_exe.bat          →  dist/OkeyCardGame.exe
  CI/CD:   push to GitHub; the Actions workflow builds the .exe automatically.
"""

from okey_gui.window import OkeyApp


def main() -> None:
    app = OkeyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
