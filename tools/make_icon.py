"""Builds assets/icon.ico (the Windows icon file) from assets/icon.png.

To use your own icon: replace assets/icon.png with a square picture of at
least 256 x 256 pixels, then run (with the virtual environment active):

    python tools/make_icon.py

and rebuild the exe with build.bat. The .ico holds several sizes, because
Windows picks a different one for the title bar, taskbar and Explorer.
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    source = ASSETS / "icon.png"
    if not source.is_file():
        raise SystemExit(f"Not found: {source}")
    image = Image.open(source).convert("RGBA")
    if image.width != image.height:
        raise SystemExit(f"icon.png must be square, but it is {image.width} x {image.height}.")
    if image.width < 256:
        raise SystemExit(f"icon.png must be at least 256 x 256, but it is {image.width} x {image.height}.")

    target = ASSETS / "icon.ico"
    image.save(target, format="ICO", sizes=SIZES)
    print(f"Wrote {target} with sizes {', '.join(f'{w}x{h}' for w, h in SIZES)}")


if __name__ == "__main__":
    main()
