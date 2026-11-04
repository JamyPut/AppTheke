import tempfile
import unittest
from pathlib import Path

from core.database import Database, clean_tags


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_add_and_get(self):
        tool_id = self.db.add_tool(
            "7-Zip",
            version="24.08",
            description="Archiver",
            install_notes="Run installer",
            download_url="https://example.com/7z.exe",
            category="Utilities",
            tags="archive, compression",
        )
        tool = self.db.get_tool(tool_id)
        self.assertEqual(tool.name, "7-Zip")
        self.assertEqual(tool.version, "24.08")
        self.assertEqual(tool.category, "Utilities")
        self.assertEqual(tool.tags, ["archive", "compression"])
        self.assertEqual(tool.download_url, "https://example.com/7z.exe")

    def test_name_required(self):
        with self.assertRaises(ValueError):
            self.db.add_tool("   ")

    def test_category_is_reused_case_insensitively(self):
        self.db.add_tool("A", category="Dev")
        self.db.add_tool("B", category="dev")
        self.assertEqual(len(self.db.list_categories()), 1)

    def test_tags_deduplicated_and_shared(self):
        self.db.add_tool("A", tags="x, X, y")
        self.db.add_tool("B", tags="x")
        self.assertEqual(self.db.list_tags(), ["x", "y"])
        self.assertEqual(self.db.list_tools()[0].tags, ["x", "y"])

    def test_search_by_name(self):
        self.db.add_tool("Notepad++")
        self.db.add_tool("7-Zip")
        self.db.add_tool("Git")
        self.assertEqual([t.name for t in self.db.list_tools("zip")], ["7-Zip"])
        self.assertEqual(len(self.db.list_tools("")), 3)
        self.assertEqual(self.db.list_tools("nothing"), [])

    def test_search_treats_wildcards_literally(self):
        self.db.add_tool("100% Tool")
        self.db.add_tool("Other")
        self.assertEqual([t.name for t in self.db.list_tools("%")], ["100% Tool"])

    def test_no_category_is_empty_string(self):
        tool_id = self.db.add_tool("A")
        self.assertEqual(self.db.get_tool(tool_id).category, "")

    def test_clean_tags(self):
        self.assertEqual(clean_tags(" a ,, b,A "), ["a", "b"])
        self.assertEqual(clean_tags(["x", "x"]), ["x"])
        self.assertEqual(clean_tags(""), [])


if __name__ == "__main__":
    unittest.main()
