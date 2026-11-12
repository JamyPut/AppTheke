import unittest

from core.urls import normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_adds_https_when_missing(self):
        self.assertEqual(normalize_url("example.org"), "https://example.org")
        self.assertEqual(normalize_url("  example.org/a?b=1  "), "https://example.org/a?b=1")

    def test_keeps_http_and_https(self):
        self.assertEqual(normalize_url("http://example.org"), "http://example.org")
        self.assertEqual(normalize_url("https://example.org:8080/x"), "https://example.org:8080/x")

    def test_rejects_things_that_are_not_web_addresses(self):
        for bad in (
            "",
            "   ",
            "ftp://example.org",
            "file:///C:/Windows/notepad.exe",
            "javascript:alert(1)",
            "has a space.com",
            "https://",
            "https://example.org:abc",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_url(bad)


if __name__ == "__main__":
    unittest.main()
