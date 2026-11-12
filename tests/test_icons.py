import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from core import paths
from core.icons import ICON_SIZE, MAX_SOURCE_BYTES, IconError, load_icon_file, to_icon_png, to_image


def make_image_bytes(size, color=(255, 0, 0, 255), fmt="PNG", mode="RGBA"):
    buffer = io.BytesIO()
    Image.new(mode, size, color if mode == "RGBA" else color[:3]).save(buffer, fmt)
    return buffer.getvalue()


def decode(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGBA")


class ToIconPngTests(unittest.TestCase):
    def test_result_is_a_64_square_png_with_transparent_padding(self):
        result = decode(to_icon_png(make_image_bytes((200, 100))))
        self.assertEqual(result.size, (ICON_SIZE, ICON_SIZE))
        self.assertEqual(result.getpixel((32, 32)), (255, 0, 0, 255))  # the picture
        self.assertEqual(result.getpixel((32, 2))[3], 0)               # padding above a wide picture

    def test_it_is_really_png(self):
        self.assertTrue(to_icon_png(make_image_bytes((10, 10))).startswith(b"\x89PNG"))

    def test_small_pictures_are_enlarged_to_fill_the_icon(self):
        result = decode(to_icon_png(make_image_bytes((16, 16))))
        self.assertEqual(result.getpixel((1, 1))[3], 255)
        self.assertEqual(result.getpixel((62, 62))[3], 255)

    def test_jpeg_input(self):
        result = decode(to_icon_png(make_image_bytes((120, 80), fmt="JPEG", mode="RGB")))
        self.assertEqual(result.size, (ICON_SIZE, ICON_SIZE))

    def test_the_apps_own_ico_file_is_accepted(self):
        data = paths.resource_path("assets/icon.ico").read_bytes()
        self.assertEqual(decode(to_icon_png(data)).size, (ICON_SIZE, ICON_SIZE))

    def test_something_that_is_not_a_picture_is_rejected(self):
        with self.assertRaises(IconError) as ctx:
            to_icon_png(b"this is not a picture")
        self.assertIn("not a picture", str(ctx.exception))

    def test_huge_input_is_rejected_before_it_is_opened(self):
        with self.assertRaises(IconError) as ctx:
            to_icon_png(b"x" * (MAX_SOURCE_BYTES + 1))
        self.assertIn("too large", str(ctx.exception))


class LoadIconFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_and_converts(self):
        path = self.folder / "logo.png"
        path.write_bytes(make_image_bytes((50, 50)))
        self.assertEqual(decode(load_icon_file(path)).size, (ICON_SIZE, ICON_SIZE))

    def test_missing_file(self):
        with self.assertRaises(IconError) as ctx:
            load_icon_file(self.folder / "nope.png")
        self.assertIn("Could not read", str(ctx.exception))

    def test_text_file(self):
        path = self.folder / "notes.txt"
        path.write_text("hello")
        with self.assertRaises(IconError):
            load_icon_file(path)


class ToImageTests(unittest.TestCase):
    def test_valid_and_damaged(self):
        self.assertEqual(to_image(to_icon_png(make_image_bytes((9, 9)))).size, (ICON_SIZE, ICON_SIZE))
        self.assertIsNone(to_image(b"damaged"))


class BundledAssetTests(unittest.TestCase):
    """The build script and the window icon depend on these files."""

    def test_icon_files_exist_and_are_usable(self):
        ico = paths.resource_path("assets/icon.ico")
        self.assertTrue(ico.is_file(), "assets/icon.ico is missing: run python tools/make_icon.py")
        with Image.open(ico) as opened:
            self.assertIn((256, 256), opened.info["sizes"])
            self.assertIn((16, 16), opened.info["sizes"])
        with Image.open(paths.resource_path("assets/icon.png")) as source:
            self.assertEqual(source.width, source.height)
            self.assertGreaterEqual(source.width, 256)

    def test_resource_path_when_packaged_points_into_the_unpacked_folder(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", tmp, create=True):
            self.assertEqual(paths.resource_path("assets/icon.ico"), Path(tmp) / "assets" / "icon.ico")


if __name__ == "__main__":
    unittest.main()
