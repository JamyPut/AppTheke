import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from core import exeicon
from core.exeicon import extract_exe_icon


def png_bytes(color=(10, 200, 30, 255)):
    buffer = io.BytesIO()
    Image.new("RGBA", (32, 32), color).save(buffer, "PNG")
    return buffer.getvalue()


class ExtractExeIconTests(unittest.TestCase):
    """PowerShell only exists on Windows, so it is replaced by a stand-in that
    behaves the way the real one does: it writes a PNG to the output path it is given."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.program = self.folder / "My Tool (x86)" / "tool.exe"
        self.program.parent.mkdir()
        self.program.write_bytes(b"MZ")
        self.windows = mock.patch.object(exeicon.sys, "platform", "win32")
        self.windows.start()
        self.addCleanup(self.windows.stop)
        self.addCleanup(self.tmp.cleanup)

    def fake_powershell(self, data=None, error=None):
        seen = {}

        def run(command, **kwargs):
            seen["command"], seen["kwargs"] = command, kwargs
            if error:
                raise error
            if data is not None:
                Path(kwargs["env"]["APPTHEKE_OUT"]).write_bytes(data)
            return subprocess.CompletedProcess(command, 0)

        return run, seen

    def test_returns_the_programs_icon_as_a_64_pixel_png(self):
        run, seen = self.fake_powershell(png_bytes())
        with mock.patch.object(exeicon.subprocess, "run", run):
            icon = extract_exe_icon(str(self.program))
        decoded = Image.open(io.BytesIO(icon))
        self.assertEqual((decoded.format, decoded.size), ("PNG", (64, 64)))
        self.assertEqual(decoded.convert("RGBA").getpixel((32, 32)), (10, 200, 30, 255))

    def test_paths_travel_in_the_environment_not_in_the_command(self):
        run, seen = self.fake_powershell(png_bytes())
        with mock.patch.object(exeicon.subprocess, "run", run):
            extract_exe_icon(str(self.program))
        self.assertEqual(seen["kwargs"]["env"]["APPTHEKE_SRC"], str(self.program))
        self.assertNotIn(str(self.program), " ".join(seen["command"]))
        self.assertEqual(seen["command"][0], "powershell.exe")
        self.assertEqual(seen["kwargs"]["stdin"], subprocess.DEVNULL)  # packaged app has no console

    def test_temporary_file_is_removed(self):
        run, seen = self.fake_powershell(png_bytes())
        with mock.patch.object(exeicon.subprocess, "run", run):
            extract_exe_icon(str(self.program))
        self.assertFalse(os.path.exists(seen["kwargs"]["env"]["APPTHEKE_OUT"]))

    def test_every_failure_gives_none(self):
        failures = {
            "powershell blocked": self.fake_powershell(error=subprocess.CalledProcessError(1, "powershell")),
            "too slow": self.fake_powershell(error=subprocess.TimeoutExpired("powershell", 20)),
            "powershell missing": self.fake_powershell(error=FileNotFoundError("powershell.exe")),
            "wrote nothing": self.fake_powershell(data=None),
            "wrote garbage": self.fake_powershell(data=b"not a picture"),
        }
        for label, (run, seen) in failures.items():
            with self.subTest(label), mock.patch.object(exeicon.subprocess, "run", run):
                self.assertIsNone(extract_exe_icon(str(self.program)))
                if "kwargs" in seen:
                    self.assertFalse(os.path.exists(seen["kwargs"]["env"]["APPTHEKE_OUT"]))

    def test_missing_file_or_empty_path_never_starts_powershell(self):
        run = mock.Mock()
        with mock.patch.object(exeicon.subprocess, "run", run):
            self.assertIsNone(extract_exe_icon(str(self.folder / "nope.exe")))
            self.assertIsNone(extract_exe_icon("   "))
        run.assert_not_called()

    def test_relative_paths_are_read_from_the_base_folder(self):
        run, seen = self.fake_powershell(png_bytes())
        with mock.patch.object(exeicon.subprocess, "run", run):
            icon = extract_exe_icon(os.path.join("My Tool (x86)", "tool.exe"), base_dir=self.folder)
        self.assertIsNotNone(icon)
        self.assertEqual(seen["kwargs"]["env"]["APPTHEKE_SRC"], str(self.program))


class NotWindowsTests(unittest.TestCase):
    def test_other_systems_get_none_without_starting_anything(self):
        run = mock.Mock()
        with mock.patch.object(exeicon.sys, "platform", "linux"), \
             mock.patch.object(exeicon.subprocess, "run", run):
            self.assertIsNone(extract_exe_icon(__file__))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
