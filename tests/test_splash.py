import sys
import types
import unittest
from unittest import mock

from core.splash import close_splash


class CloseSplashTests(unittest.TestCase):
    def test_does_nothing_without_a_splash(self):
        # Setting a module to None makes "import pyi_splash" raise ImportError,
        # which is what happens when running from source.
        with mock.patch.dict(sys.modules, {"pyi_splash": None}):
            close_splash()  # must not raise

    def test_closes_the_pyinstaller_splash(self):
        fake = types.ModuleType("pyi_splash")
        fake.close = mock.Mock()
        with mock.patch.dict(sys.modules, {"pyi_splash": fake}):
            close_splash()
        fake.close.assert_called_once_with()

    def test_a_failing_splash_never_stops_the_app(self):
        fake = types.ModuleType("pyi_splash")
        fake.close = mock.Mock(side_effect=RuntimeError("This module is not initialized"))
        with mock.patch.dict(sys.modules, {"pyi_splash": fake}):
            close_splash()  # must not raise
        fake.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
