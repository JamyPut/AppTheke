"""Turning pictures into the small PNG icons stored with each tool.

Uses Pillow. This module has no window code, so the planned web app can reuse it.
"""

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ICON_SIZE = 64                       # icons are stored as 64 x 64 PNG, plenty for lists and headers
MAX_SOURCE_BYTES = 10 * 1024 * 1024  # refuse pictures larger than this before even opening them


class IconError(Exception):
    """A picture could not be used as an icon; the message is readable as-is."""


def to_icon_png(data: bytes) -> bytes:
    """Convert any picture Pillow can read (PNG, ICO, JPG, GIF, BMP...) into a
    64 x 64 PNG with a transparent background. The picture keeps its
    proportions and is centered."""
    if len(data) > MAX_SOURCE_BYTES:
        raise IconError("That picture is too large (over 10 MB).")
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("RGBA")  # for .ico files Pillow opens the largest size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise IconError(
            "That file is not a picture AppTheke can read (PNG, ICO, JPG, GIF or BMP)."
        ) from error

    scale = min(ICON_SIZE / image.width, ICON_SIZE / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    image = image.resize(size, Image.LANCZOS)

    canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((ICON_SIZE - size[0]) // 2, (ICON_SIZE - size[1]) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def load_icon_file(path: str | Path) -> bytes:
    """Read a picture file the user chose and convert it with to_icon_png."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise IconError("That picture is too large (over 10 MB).")
        data = path.read_bytes()
    except OSError as error:
        raise IconError(f"Could not read the file: {error}") from error
    return to_icon_png(data)


def to_image(png: bytes) -> Image.Image | None:
    """Open stored icon bytes as a Pillow image, or None if they are damaged."""
    try:
        with Image.open(io.BytesIO(png)) as source:
            return source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError):
        return None
