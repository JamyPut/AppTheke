import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import exeinfo
from core.exeinfo import ProgramInfo, clean_version, info_from_version_data, read_program_info


class CleanVersionTests(unittest.TestCase):
    def test_cases(self):
        cases = {
            "1.4.1.1032": "1.4.1.1032",
            "24.08": "24.08",
            "1, 4, 1, 1032": "1.4.1.1032",
            "v1.7.3": "1.7.3",
            "2.1.0+abc123": "2.1.0",
            "3.0.0-beta.2": "3.0.0-beta.2",
            "3.0.18 (build 5)": "3.0.18",
            "  10.0.22621.1  ": "10.0.22621.1",
            "": "",
            None: "",
            "Release": "Release",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(clean_version(raw), expected)


class InfoFromVersionDataTests(unittest.TestCase):
    def test_typical_program(self):
        info = info_from_version_data(
            {"product": "7-Zip", "description": "7-Zip File Manager", "product_version": "24.08",
             "file_version": "24.08", "company": "Igor Pavlov"},
            fallback_name="7zFM",
        )
        self.assertEqual(info, ProgramInfo("7-Zip", "24.08", "7-Zip File Manager\nPublisher: Igor Pavlov"))

    def test_description_equal_to_name_is_not_repeated(self):
        info = info_from_version_data(
            {"product": "Everything", "description": "Everything", "product_version": "1.4.1.1032",
             "company": "voidtools"},
            fallback_name="Everything",
        )
        self.assertEqual(info.description, "Publisher: voidtools")

    def test_trademark_signs_and_extra_spaces_are_removed(self):
        info = info_from_version_data(
            {"product": "Microsoft®  Windows® Operating System", "company": "Microsoft Corporation"},
            fallback_name="notepad",
        )
        self.assertEqual(info.name, "Microsoft Windows Operating System")

    def test_falls_back_to_description_then_file_name(self):
        self.assertEqual(info_from_version_data({"description": "Handy Tool"}, "handy").name, "Handy Tool")
        empty = info_from_version_data({"product": None, "description": "", "product_version": None}, "mytool")
        self.assertEqual(empty, ProgramInfo("mytool", "", ""))

    def test_file_version_is_used_when_product_version_is_missing(self):
        info = info_from_version_data({"product": "X", "file_version": "5, 2, 0, 1"}, "x")
        self.assertEqual(info.version, "5.2.0.1")

    def test_odd_values_do_not_crash(self):
        info = info_from_version_data({"product": 123, "description": ["x"], "company": {}}, "odd")
        self.assertEqual(info, ProgramInfo("odd", "", ""))

    def test_very_long_name_is_cut(self):
        self.assertEqual(len(info_from_version_data({"product": "x" * 500}, "f").name), exeinfo.MAX_NAME)


class ReadProgramInfoTests(unittest.TestCase):
    """PowerShell only exists on Windows, so it is replaced by a stand-in that writes
    JSON to the output path it is given, with the byte-order mark Windows PowerShell adds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.program = self.folder / "Tools (x86)" / "tool.exe"
        self.program.parent.mkdir()
        self.program.write_bytes(b"MZ")
        windows = mock.patch.object(exeinfo.sys, "platform", "win32")
        windows.start()
        self.addCleanup(windows.stop)

    def fake_powershell(self, text=None, error=None):
        seen = {}

        def run(command, **kwargs):
            seen["command"], seen["kwargs"] = command, kwargs
            if error:
                raise error
            if text is not None:
                Path(kwargs["env"]["APPTHEKE_OUT"]).write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            return subprocess.CompletedProcess(command, 0)

        return run, seen

    def test_reads_details(self):
        data = {"product": "Café Tool™", "description": "Makes coffee", "product_version": "2, 0, 1",
                "file_version": "2.0.1.0", "company": "Bean Ltd"}
        run, seen = self.fake_powershell(json.dumps(data, ensure_ascii=False))
        with mock.patch.object(exeinfo.subprocess, "run", run):
            info = read_program_info(str(self.program))
        self.assertEqual(info, ProgramInfo("Café Tool", "2.0.1", "Makes coffee\nPublisher: Bean Ltd"))
        self.assertEqual(seen["kwargs"]["env"]["APPTHEKE_SRC"], str(self.program))
        self.assertNotIn(str(self.program), " ".join(seen["command"]))
        self.assertEqual(seen["kwargs"]["stdin"], subprocess.DEVNULL)
        self.assertFalse(os.path.exists(seen["kwargs"]["env"]["APPTHEKE_OUT"]))

    def test_program_without_details_gives_its_file_name(self):
        run, _ = self.fake_powershell(json.dumps({"product": None, "description": None}))
        with mock.patch.object(exeinfo.subprocess, "run", run):
            self.assertEqual(read_program_info(str(self.program)), ProgramInfo("tool", "", ""))

    def test_every_failure_gives_none(self):
        failures = {
            "blocked": self.fake_powershell(error=subprocess.CalledProcessError(1, "powershell")),
            "too slow": self.fake_powershell(error=subprocess.TimeoutExpired("powershell", 20)),
            "missing": self.fake_powershell(error=FileNotFoundError("powershell.exe")),
            "wrote nothing": self.fake_powershell(text=None),
            "not json": self.fake_powershell(text="<<oops>>"),
            "json list": self.fake_powershell(text="[1, 2]"),
        }
        for label, (run, seen) in failures.items():
            with self.subTest(label), mock.patch.object(exeinfo.subprocess, "run", run):
                self.assertIsNone(read_program_info(str(self.program)))
                if "kwargs" in seen:
                    self.assertFalse(os.path.exists(seen["kwargs"]["env"]["APPTHEKE_OUT"]))

    def test_missing_file_or_empty_path_never_starts_powershell(self):
        run = mock.Mock()
        with mock.patch.object(exeinfo.subprocess, "run", run):
            self.assertIsNone(read_program_info(str(self.folder / "nope.exe")))
            self.assertIsNone(read_program_info("  "))
        run.assert_not_called()

    def test_not_windows(self):
        run = mock.Mock()
        with mock.patch.object(exeinfo.sys, "platform", "linux"), \
             mock.patch.object(exeinfo.subprocess, "run", run):
            self.assertIsNone(read_program_info(str(self.program)))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
