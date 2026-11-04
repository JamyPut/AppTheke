"""Fetch a setup/executable file from a URL into a folder (standard library only)."""

import http.client
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Callable

USER_AGENT = "AppTheke/0.1"
CHUNK_SIZE = 64 * 1024
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# progress(bytes_downloaded, total_bytes_or_None)
ProgressCallback = Callable[[int, "int | None"], None]


class DownloadError(Exception):
    """A download failed in a way worth showing to the user as plain text."""


def safe_filename(name: str) -> str:
    """Make a server-supplied file name safe to write on Windows."""
    # Keep only the last path part, so '..\\..\\evil.exe' cannot escape the folder.
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        return "download"
    if name.split(".")[0].lower() in WINDOWS_RESERVED:
        name = "_" + name
    return name


def _filename_from_response(response) -> str:
    header = response.headers.get("Content-Disposition")
    if header:
        message = Message()
        message["Content-Disposition"] = header
        name = message.get_filename()
        if name:
            return safe_filename(name)
    # Fall back to the URL path. geturl() is the final URL after redirects.
    path = urllib.parse.urlparse(response.geturl()).path
    return safe_filename(urllib.parse.unquote(path))


def _unique_path(folder: Path, name: str) -> Path:
    """Never overwrite an existing file: 'a.exe' -> 'a (1).exe' -> 'a (2).exe'."""
    target = folder / name
    stem, suffix = target.stem, target.suffix
    counter = 1
    while target.exists():
        target = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return target


def download(
    url: str,
    folder: Path,
    progress: ProgressCallback | None = None,
    timeout: float = 30,
) -> Path:
    """Download url into folder and return the saved file's path.

    Raises DownloadError with a readable message on any failure.
    """
    url = url.strip()
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise DownloadError("The download URL must start with http:// or https://")

    folder = Path(folder)
    if not folder.is_dir():
        raise DownloadError(f"The folder does not exist: {folder}")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        raise DownloadError(f"The server answered with an error: {error.code} {error.reason}")
    except urllib.error.URLError as error:
        raise DownloadError(f"Could not connect: {error.reason}")
    except (TimeoutError, OSError) as error:
        raise DownloadError(f"Could not connect: {error}")
    except ValueError as error:
        raise DownloadError(f"That does not look like a valid URL: {error}")

    with response:
        content_type = response.headers.get_content_type()
        if content_type == "text/html":
            raise DownloadError(
                "That URL returns a web page, not a file. "
                "Use the direct link to the installer or executable."
            )

        length = response.headers.get("Content-Length")
        total = int(length) if length and length.isdigit() else None
        target = _unique_path(folder, _filename_from_response(response))
        partial = target.with_name(target.name + ".part")

        downloaded = 0
        try:
            with open(partial, "wb") as out:
                while True:
                    try:
                        chunk = response.read(CHUNK_SIZE)
                    except (OSError, http.client.HTTPException) as error:
                        raise DownloadError(f"The connection was interrupted: {error}")
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
            if total is not None and downloaded != total:
                raise DownloadError("The download was cut off before it finished.")
            os.replace(partial, target)  # finished files never appear half-written
        except DownloadError:
            partial.unlink(missing_ok=True)
            raise
        except OSError as error:
            partial.unlink(missing_ok=True)
            raise DownloadError(f"Could not save the file: {error}")
    return target
