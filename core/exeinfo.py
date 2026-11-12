"""Reading a program's name, version and description from its file (Windows only).

Windows programs carry these details inside the .exe (right-click the file,
Properties, Details). Windows PowerShell can read them, the same way
exeicon.py reads the icon.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .launcher import resolve

# The path travels through an environment variable, so spaces and quotes in it
# can never break the command. The result is written as JSON to a temp file.
_SCRIPT = (
    "$v = (Get-Item -LiteralPath $env:APPTHEKE_SRC).VersionInfo; "
    "$data = @{ product = $v.ProductName; description = $v.FileDescription; "
    "product_version = $v.ProductVersion; file_version = $v.FileVersion; "
    "company = $v.CompanyName }; "
    "[IO.File]::WriteAllText($env:APPTHEKE_OUT, ($data | ConvertTo-Json -Compress), "
    "[Text.Encoding]::UTF8)"
)

_MARKS = re.compile(r"[®™©]")
_VERSION = re.compile(r"v?(\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?)", re.IGNORECASE)
MAX_NAME = 100


@dataclass
class ProgramInfo:
    name: str = ""
    version: str = ""
    description: str = ""


def _clean(value) -> str:
    """Drop ® ™ © and squeeze whitespace. Anything that is not text becomes ''."""
    if not isinstance(value, str):
        return ""
    return " ".join(_MARKS.sub("", value).split())


def clean_version(value) -> str:
    """'1, 4, 1, 1032' -> '1.4.1.1032', 'v1.7.3' -> '1.7.3', '2.1.0+abc123' -> '2.1.0'."""
    text = _clean(value)
    if not text:
        return ""
    text = re.sub(r"\s*,\s*", ".", text)  # some older programs separate with commas
    match = _VERSION.match(text)
    return match.group(1) if match else text[:40]


def info_from_version_data(data: dict, fallback_name: str) -> ProgramInfo:
    """Turn the raw details Windows reports into the form's name, version and description."""
    product = _clean(data.get("product"))
    description = _clean(data.get("description"))
    company = _clean(data.get("company"))

    name = (product or description or fallback_name)[:MAX_NAME]
    version = clean_version(data.get("product_version")) or clean_version(data.get("file_version"))

    lines = []
    if description and description.lower() != name.lower():
        lines.append(description)
    if company:
        lines.append(f"Publisher: {company}")
    return ProgramInfo(name=name, version=version, description="\n".join(lines))


def read_program_info(path: str, base_dir: Path | None = None, timeout: float = 20) -> ProgramInfo | None:
    """Return the program's name, version and description, or None if they cannot be read.

    None is a normal answer (not on Windows, file missing, PowerShell blocked).
    A program without any details still gives its file name as the name.
    """
    if sys.platform != "win32" or not path.strip():
        return None
    try:
        target = resolve(path, base_dir)
    except (OSError, RuntimeError, ValueError):
        return None
    if not target.is_file():
        return None

    handle, out_name = tempfile.mkstemp(suffix=".json")
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
        # utf-8-sig: Windows PowerShell writes a byte-order mark at the start.
        data = json.loads(Path(out_name).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return None
        return info_from_version_data(data, fallback_name=target.stem)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        try:
            os.unlink(out_name)
        except OSError:
            pass
