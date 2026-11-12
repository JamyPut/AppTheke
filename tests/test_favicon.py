import io
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from core.favicon import fetch_favicon

RED, BLUE, GREEN = (220, 30, 30, 255), (30, 60, 220, 255), (20, 160, 60, 255)


def png(color, size=(32, 32)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def center_color(icon_png: bytes):
    return Image.open(io.BytesIO(icon_png)).convert("RGBA").getpixel((32, 32))


PAGES = {
    "/rel": b'<html><head><link rel="icon" href="/static/i.png"></head></html>',
    # a small red icon and a large "apple-touch-icon" in blue: the large one wins
    "/touch": (
        b'<link rel="icon" href="/small.png" sizes="16x16">'
        b'<link rel="apple-touch-icon" href="/big.png" sizes="180x180">'
    ),
    "/svg": b'<link rel="icon" type="image/svg+xml" href="/logo.svg">',
    "/bare": b"<html><body>no icon here</body></html>",
    "/bad": b'<link rel="icon" href="/garbage.png">',
    "/sub/page": b'<link rel="shortcut icon" href="icon.png">',
}
FILES = {
    "/static/i.png": png(GREEN),
    "/small.png": png(RED, (16, 16)),
    "/big.png": png(BLUE, (180, 180)),
    "/sub/icon.png": png(GREEN),
    "/garbage.png": b"this is not an image",
}


class Handler(BaseHTTPRequestHandler):
    serve_default_favicon = True  # subclasses switch this off

    def do_GET(self):
        if self.path in PAGES:
            self._send(PAGES[self.path], "text/html; charset=utf-8")
        elif self.path in FILES:
            self._send(FILES[self.path], "image/png")
        elif self.path == "/favicon.ico" and self.serve_default_favicon:
            self._send(png(RED), "image/x-icon")
        elif self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "/sub/page")
            self.end_headers()
        else:
            self.send_error(404)

    def _send(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class NoFaviconHandler(Handler):
    serve_default_favicon = False


def start(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class FaviconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = {k: os.environ.get(k) for k in ("NO_PROXY", "no_proxy")}
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        cls.server, cls.base = start(Handler)
        cls.bare_server, cls.bare_base = start(NoFaviconHandler)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.server, cls.bare_server):
            server.shutdown()
            server.server_close()
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_icon_the_page_points_to(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/rel")), GREEN)

    def test_large_apple_touch_icon_beats_a_small_icon(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/touch")), BLUE)

    def test_svg_is_skipped_and_favicon_ico_is_used(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/svg")), RED)

    def test_page_without_icon_links_uses_favicon_ico(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/bare")), RED)

    def test_missing_page_still_tries_favicon_ico(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/does-not-exist")), RED)

    def test_unreadable_icon_is_skipped(self):
        self.assertEqual(center_color(fetch_favicon(self.base + "/bad")), RED)

    def test_relative_link_is_resolved_against_the_final_address(self):
        # /redirect -> /sub/page, whose icon link "icon.png" means /sub/icon.png
        self.assertEqual(center_color(fetch_favicon(self.base + "/redirect")), GREEN)

    def test_no_icon_anywhere_gives_none(self):
        self.assertIsNone(fetch_favicon(self.bare_base + "/bare"))

    def test_result_is_a_64_pixel_png(self):
        result = Image.open(io.BytesIO(fetch_favicon(self.base + "/rel")))
        self.assertEqual((result.format, result.size), ("PNG", (64, 64)))

    def test_bad_input_gives_none(self):
        for bad in ("", "ftp://example.org", "has a space.com", "file:///etc/passwd"):
            with self.subTest(bad=bad):
                self.assertIsNone(fetch_favicon(bad))

    def test_unreachable_site_gives_none(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.assertIsNone(fetch_favicon(f"http://127.0.0.1:{port}/", timeout=2))


if __name__ == "__main__":
    unittest.main()
