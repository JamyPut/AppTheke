"""Start an installed app from its saved path."""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from .paths import app_dir
from .urls import normalize_url


class LaunchError(Exception):
    """Starting the app failed in a way worth showing to the user as plain text."""


def resolve(path: str, base_dir: Path | None = None) -> Path:
    """Turn the saved text into a real path.

    - %ProgramFiles%-style variables are expanded (so one entry works on any PC).
    - A relative path is read from the AppTheke folder, so tools kept on the
      same USB stick still start when the drive letter changes.
    """
    text = os.path.expandvars(path.strip().strip('"'))
    target = Path(text).expanduser()
    if not target.is_absolute():
        target = (base_dir if base_dir is not None else app_dir()) / target
    return target


def launch(path: str, base_dir: Path | None = None) -> Path:
    """Start the program at path and return the resolved path.

    Raises LaunchError with a readable message on any failure.
    """
    if not path.strip():
        raise LaunchError("This tool has no executable path yet. Use Edit to add one.")

    target = resolve(path, base_dir)
    if target.is_dir():
        raise LaunchError(f"That path is a folder, not a program: {target}")
    if not target.is_file():
        raise LaunchError(f"File not found: {target}")

    try:
        if sys.platform == "win32":
            # Same as double-clicking the file in Explorer: Windows shows its own
            # administrator prompt when the app needs one, and .lnk/.bat files
            # work too. cwd makes apps that read files next to themselves happy.
            os.startfile(str(target), cwd=str(target.parent))
        else:
            subprocess.Popen(
                [str(target)],
                cwd=target.parent,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # keep running if AppTheke is closed
            )
    except OSError as error:
        raise LaunchError(f"Windows could not start it: {error}")
    return target


def open_website(url: str) -> str:
    """Open a saved web address in the default browser and return the address used.

    Raises LaunchError with a readable message on any failure.
    """
    try:
        address = normalize_url(url)  # only http and https, never a file or a script
    except ValueError as error:
        raise LaunchError(str(error)) from error
    try:
        opened = webbrowser.open(address)
    except webbrowser.Error as error:
        raise LaunchError(f"Could not open the browser: {error}") from error
    if not opened:
        raise LaunchError("No web browser could be started.")
    return address
