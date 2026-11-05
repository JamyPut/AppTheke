"""Where AppTheke keeps its files.

Portable means: the database and downloads sit next to the .exe (or next to
the project folder when running from source), never in AppData.
"""

import sys
from pathlib import Path


def app_dir() -> Path:
    """Folder that holds the .exe when packaged, or the project root otherwise."""
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys.frozen. sys.executable is the real .exe location.
        # (__file__ would point into a temp folder with --onefile.)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def db_path() -> Path:
    return app_dir() / "apptheke.db"


def downloads_dir() -> Path:
    """Default folder offered by the Download picker. Never raises: if the app
    folder is read-only (Program Files, for example) the user's home folder is
    offered instead."""
    folder = app_dir() / "downloads"
    try:
        folder.mkdir(exist_ok=True)
    except OSError:
        return Path.home()
    return folder
