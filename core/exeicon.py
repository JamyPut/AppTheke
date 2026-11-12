"""Reading the icon out of an installed program (Windows only)."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .icons import IconError, to_icon_png
from .launcher import resolve

# Windows PowerShell ships with Windows 10 and 11 and can ask Windows for a
# file's icon. The paths travel through environment variables, so spaces and
# quotes in a path can never break the command.
_SCRIPT = (
    "Add-Type -AssemblyName System.Drawing; "
    "$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($env:APPTHEKE_SRC); "
    "if ($null -eq $icon) { exit 2 }; "
    "$icon.ToBitmap().Save($env:APPTHEKE_OUT, [System.Drawing.Imaging.ImageFormat]::Png)"
)


def extract_exe_icon(path: str, base_dir: Path | None = None, timeout: float = 20) -> bytes | None:
    """Return the program's icon as a 64 x 64 PNG, or None if it cannot be read.

    None is a normal answer (not on Windows, file missing, PowerShell blocked,
    no icon in the file): the caller simply shows no icon.
    """
    if sys.platform != "win32" or not path.strip():
        return None
    try:
        target = resolve(path, base_dir)
    except (OSError, RuntimeError, ValueError):
        return None
    if not target.is_file():
        return None

    handle, out_name = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
            env={**os.environ, "APPTHEKE_SRC": str(target), "APPTHEKE_OUT": out_name},
            # Without a console, the packaged app has no standard streams to hand on.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no flashing black window
            timeout=timeout,
            check=True,
        )
        return to_icon_png(Path(out_name).read_bytes())
    except (OSError, subprocess.SubprocessError, IconError):
        return None
    finally:
        try:
            os.unlink(out_name)
        except OSError:
            pass
