import os
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.downloader import DownloadError, download, safe_filename

BODY = b"MZ" + b"x" * 200_000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/tool.exe":
            self._send(BODY)
        elif self.path == "/get?id=3":
            self._send(BODY, {"Content-Disposition": 'attachment; filename="setup v2.exe"'})
        elif self.path == "/evil":
            self._send(BODY, {"Content-Disposition": 'attachment; filename="..\\..\\evil.exe"'})
        elif self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "/tool.exe")
            self.end_headers()
        elif self.path == "/page":
            self._send(b"<html></html>", content_type="text/html; charset=utf-8")
        elif self.path == "/short":
            # Promises more bytes than it sends, then closes the connection.
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY[:1000])
            self.close_connection = True
        else:
            self.send_error(404)

    def _send(self, body, headers=None, content_type="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output quiet
        pass


class DownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Talk to the local server directly, even if a proxy is configured.
        cls._saved = {k: os.environ.get(k) for k in ("NO_PROXY", "no_proxy")}
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_downloads_file_and_reports_progress(self):
        calls = []
        path = download(
            self.base + "/tool.exe", self.folder, progress=lambda d, t: calls.append((d, t))
        )
        self.assertEqual(path.name, "tool.exe")
        self.assertEqual(path.read_bytes(), BODY)
        self.assertEqual(calls[-1], (len(BODY), len(BODY)))
        self.assertEqual([p.name for p in self.folder.iterdir()], ["tool.exe"])

    def test_uses_content_disposition_name(self):
        path = download(self.base + "/get?id=3", self.folder)
        self.assertEqual(path.name, "setup v2.exe")

    def test_follows_redirect_and_uses_final_name(self):
        path = download(self.base + "/redirect", self.folder)
        self.assertEqual(path.name, "tool.exe")

    def test_server_filename_cannot_escape_folder(self):
        path = download(self.base + "/evil", self.folder)
        self.assertEqual(path.parent, self.folder)
        self.assertEqual(path.name, "evil.exe")

    def test_never_overwrites_existing_file(self):
        first = download(self.base + "/tool.exe", self.folder)
        second = download(self.base + "/tool.exe", self.folder)
        self.assertEqual(first.name, "tool.exe")
        self.assertEqual(second.name, "tool (1).exe")

    def test_web_page_is_rejected(self):
        with self.assertRaises(DownloadError) as ctx:
            download(self.base + "/page", self.folder)
        self.assertIn("web page", str(ctx.exception))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_http_error_is_readable(self):
        with self.assertRaises(DownloadError) as ctx:
            download(self.base + "/missing", self.folder)
        self.assertIn("404", str(ctx.exception))

    def test_truncated_download_leaves_no_files(self):
        with self.assertRaises(DownloadError):
            download(self.base + "/short", self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_bad_scheme_and_bad_folder(self):
        with self.assertRaises(DownloadError):
            download("ftp://example.com/a.exe", self.folder)
        with self.assertRaises(DownloadError):
            download("example.com/a.exe", self.folder)
        with self.assertRaises(DownloadError):
            download(self.base + "/tool.exe", self.folder / "nope")

    def test_connection_refused(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(DownloadError):
            download(f"http://127.0.0.1:{port}/a.exe", self.folder, timeout=3)


class SafeFilenameTests(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(safe_filename("a/b\\c.exe"), "c.exe")
        self.assertEqual(safe_filename('we<ir>d:"name?.exe'), "we_ir_d__name_.exe")
        self.assertEqual(safe_filename("  ..  "), "download")
        self.assertEqual(safe_filename(""), "download")
        self.assertEqual(safe_filename("CON.txt"), "_CON.txt")


if __name__ == "__main__":
    unittest.main()
