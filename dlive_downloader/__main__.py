"""Entry point for the DLive Downloader GUI application."""
from __future__ import annotations

import os
import sys
from importlib import import_module

# Avoid Tk trying to spawn the legacy "Tk Console" window on macOS bundles,
# which can trigger a first-launch crash inside Tk's menu setup.
os.environ.setdefault("TKCONSOLE", "0")


def _import_gui_run():
    """
    Import the GUI runner with a helpful error message when Tk or CustomTkinter
    is missing. This avoids an unhandled ModuleNotFoundError when the user runs
    the app with a Python interpreter that does not have the GUI dependencies.
    """
    try:
        module = import_module("dlive_downloader.gui_modern")
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing in {"customtkinter", "tkinter", "_tkinter"}:
            sys.stderr.write(
                "GUI dependencies are missing.\n"
                "Activate the bundled virtualenv (source venv/bin/activate) or run:\n"
                "  python3 -m pip install -r requirements.txt\n"
                "Ensure your Python build has Tk support (python.org or Homebrew python-tk).\n"
            )
            sys.exit(1)
        raise
    return module.run


if __name__ == "__main__":
    sys.exit(_import_gui_run()())
