import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import paths
from core.errorlog import LOG_NAME, log_exception


class PathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def frozen_as_exe(self):
        """Pretend to be the PyInstaller .exe sitting in self.folder."""
        exe = self.folder / "AppTheke.exe"
        return (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(exe)),
        )

    def test_from_source_uses_project_folder(self):
        self.assertTrue((paths.app_dir() / "main.py").is_file())
        self.assertEqual(paths.db_path(), paths.app_dir() / "apptheke.db")

    def test_packaged_exe_keeps_data_next_to_the_exe(self):
        frozen, executable = self.frozen_as_exe()
        with frozen, executable:
            self.assertEqual(paths.app_dir(), self.folder)
            self.assertEqual(paths.db_path(), self.folder / "apptheke.db")
            self.assertEqual(paths.downloads_dir(), self.folder / "downloads")
            self.assertTrue((self.folder / "downloads").is_dir())

    def test_downloads_dir_falls_back_to_home_when_folder_is_read_only(self):
        frozen, executable = self.frozen_as_exe()
        with frozen, executable, mock.patch.object(
            Path, "mkdir", side_effect=PermissionError("read-only")
        ):
            self.assertEqual(paths.downloads_dir(), Path.home())


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def make_error():
        try:
            raise ValueError("boom")
        except ValueError:
            return sys.exc_info()

    def test_writes_and_appends(self):
        path = log_exception(*self.make_error(), folder=self.folder)
        self.assertEqual(path, self.folder / LOG_NAME)
        log_exception(*self.make_error(), folder=self.folder)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("AppTheke 1."), 2)
        self.assertIn("ValueError: boom", text)
        self.assertIn("Traceback", text)

    def test_unwritable_folder_returns_none(self):
        missing = self.folder / "does-not-exist"
        self.assertIsNone(log_exception(*self.make_error(), folder=missing))


if __name__ == "__main__":
    unittest.main()
