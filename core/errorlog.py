"""Crash log for the packaged app.

The .exe is built with --windowed, so it has no console and an error would
otherwise vanish without a trace. Errors are appended to a text file next to
the app instead, which can be attached to a bug report.
"""

import datetime
import traceback
from pathlib import Path

from .paths import app_dir
from .version import __version__

LOG_NAME = "apptheke-error.log"


def log_exception(exc_type, exc, tb, folder: Path | None = None) -> Path | None:
    """Append an error report to the log file and return its path.

    Returns None when the file cannot be written (for example a read-only folder).
    """
    target = (folder if folder is not None else app_dir()) / LOG_NAME
    try:
        with open(target, "a", encoding="utf-8") as log:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.write(f"--- {stamp}  AppTheke {__version__} ---\n")
            log.write("".join(traceback.format_exception(exc_type, exc, tb)))
            log.write("\n")
    except OSError:
        return None
    return target
