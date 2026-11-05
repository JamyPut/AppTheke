import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import launcher
from core.launcher import LaunchError, launch, resolve


class ResolveTests(unittest.TestCase):
    def test_relative_path_uses_base_dir(self):
        base = Path("/some/base")
        self.assertEqual(resolve("tools/a.exe", base), base / "tools" / "a.exe")

    def test_absolute_path_is_kept(self):
        target = Path(tempfile.gettempdir()) / "a.exe"
        self.assertEqual(resolve(str(target), Path("/other")), target)

    def test_quotes_and_spaces_are_stripped(self):
        target = Path(tempfile.gettempdir()) / "a.exe"
        self.assertEqual(resolve(f'  "{target}"  ', Path("/other")), target)

    def test_environment_variables_are_expanded(self):
        with mock.patch.dict(os.environ, {"APPTHEKE_TEST_DIR": tempfile.gettempdir()}):
            text = "%APPTHEKE_TEST_DIR%" if sys.platform == "win32" else "$APPTHEKE_TEST_DIR"
            self.assertEqual(
                resolve(f"{text}/a.exe", Path("/other")),
                Path(tempfile.gettempdir()) / "a.exe",
            )


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_path(self):
        with self.assertRaises(LaunchError) as ctx:
            launch("   ")
        self.assertIn("no executable path", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(LaunchError) as ctx:
            launch(str(self.folder / "nope.exe"))
        self.assertIn("File not found", str(ctx.exception))

    def test_folder_is_rejected(self):
        with self.assertRaises(LaunchError) as ctx:
            launch(str(self.folder))
        self.assertIn("folder", str(ctx.exception))

    def test_windows_branch_uses_startfile_in_the_programs_folder(self):
        program = self.folder / "app.exe"
        program.write_bytes(b"MZ")
        with mock.patch.object(launcher.sys, "platform", "win32"), \
             mock.patch.object(os, "startfile", create=True) as startfile:
            result = launch(str(program))
        startfile.assert_called_once_with(str(program), cwd=str(self.folder))
        self.assertEqual(result, program)

    def test_windows_start_failure_becomes_readable_error(self):
        program = self.folder / "app.exe"
        program.write_bytes(b"MZ")
        with mock.patch.object(launcher.sys, "platform", "win32"), \
             mock.patch.object(os, "startfile", create=True, side_effect=OSError("blocked")):
            with self.assertRaises(LaunchError) as ctx:
                launch(str(program))
        self.assertIn("blocked", str(ctx.exception))

    @unittest.skipIf(sys.platform == "win32", "real-process check uses a shell script")
    def test_really_starts_a_program_in_its_own_folder(self):
        marker = self.folder / "started.txt"
        script = self.folder / "run.sh"
        script.write_text("#!/bin/sh\npwd > started.txt\n")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        launch("run.sh", base_dir=self.folder)  # relative path, resolved from base_dir

        for _ in range(100):  # wait up to 5 s for the child process
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.05)
        self.assertEqual(Path(marker.read_text().strip()).resolve(), self.folder.resolve())

    @unittest.skipIf(sys.platform == "win32", "permission bits are a Unix concept")
    def test_unrunnable_file_becomes_readable_error(self):
        script = self.folder / "plain.txt"
        script.write_text("not a program")
        with self.assertRaises(LaunchError):
            launch(str(script))


if __name__ == "__main__":
    unittest.main()
