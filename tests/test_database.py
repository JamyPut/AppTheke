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

    def test_update_tool(self):
        tool_id = self.db.add_tool("Old", version="1", category="A", tags="x, y")
        self.db.update_tool(
            tool_id, "New", version="2", description="d", install_notes="n",
            download_url="https://example.com/a.exe", category="B", tags="y, z",
        )
        tool = self.db.get_tool(tool_id)
        self.assertEqual(
            (tool.name, tool.version, tool.description, tool.install_notes, tool.download_url),
            ("New", "2", "d", "n", "https://example.com/a.exe"),
        )
        self.assertEqual(tool.category, "B")
        self.assertEqual(tool.tags, ["y", "z"])

    def test_update_prunes_unused_category_and_tags(self):
        tool_id = self.db.add_tool("T", category="Typo", tags="old, keep")
        self.db.update_tool(tool_id, "T", category="Fixed", tags="keep")
        self.assertEqual(self.db.list_categories(), ["Fixed"])
        self.assertEqual(self.db.list_tags(), ["keep"])

    def test_update_validation(self):
        tool_id = self.db.add_tool("T")
        with self.assertRaises(ValueError):
            self.db.update_tool(tool_id, "  ")
        with self.assertRaises(ValueError):
            self.db.update_tool(9999, "Ghost")

    def test_delete_tool(self):
        keep = self.db.add_tool("Keep", category="Shared", tags="shared")
        gone = self.db.add_tool("Gone", category="Shared", tags="shared, only-gone")
        self.assertTrue(self.db.delete_tool(gone))
        self.assertIsNone(self.db.get_tool(gone))
        self.assertFalse(self.db.delete_tool(gone))
        # shared category/tag stay because another tool uses them
        self.assertEqual(self.db.list_categories(), ["Shared"])
        self.assertEqual(self.db.list_tags(), ["shared"])
        self.assertEqual(self.db.get_tool(keep).tags, ["shared"])

    def test_delete_last_tool_clears_categories_and_tags(self):
        tool_id = self.db.add_tool("T", category="C", tags="a")
        self.db.delete_tool(tool_id)
        self.assertEqual(self.db.list_categories(), [])
        self.assertEqual(self.db.list_tags(), [])

    def test_exe_path_roundtrip_and_update(self):
        tool_id = self.db.add_tool("A", exe_path=r"  C:\Program Files\A\a.exe ")
        self.assertEqual(self.db.get_tool(tool_id).exe_path, r"C:\Program Files\A\a.exe")
        self.db.update_tool(tool_id, "A", exe_path=r"D:\Tools\a.exe")
        self.assertEqual(self.db.get_tool(tool_id).exe_path, r"D:\Tools\a.exe")
        self.assertEqual(self.db.get_tool(self.db.add_tool("B")).exe_path, "")

    def test_old_database_without_exe_path_is_upgraded(self):
        import sqlite3

        old_path = Path(self.tmp.name) / "old.db"
        conn = sqlite3.connect(old_path)
        # The tools table exactly as v0.1/v0.2 created it, without exe_path.
        conn.executescript(
            """
            CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
            CREATE TABLE tools (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                install_notes TEXT NOT NULL DEFAULT '', download_url TEXT NOT NULL DEFAULT '',
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO categories(name) VALUES ('Utilities');
            INSERT INTO tools(name, version, category_id) VALUES ('7-Zip', '24.08', 1);
            """
        )
        conn.commit()
        conn.close()

        db = Database(old_path)
        try:
            tool = db.list_tools()[0]
            self.assertEqual((tool.name, tool.version, tool.category), ("7-Zip", "24.08", "Utilities"))
            self.assertEqual(tool.exe_path, "")
            db.update_tool(tool.id, "7-Zip", exe_path="C:/x/7z.exe", category="Utilities")
            self.assertEqual(db.get_tool(tool.id).exe_path, "C:/x/7z.exe")
        finally:
            db.close()
        # opening it a second time must not try to add the column again
        Database(old_path).close()

    def test_clean_tags(self):
        self.assertEqual(clean_tags(" a ,, b,A "), ["a", "b"])
        self.assertEqual(clean_tags(["x", "x"]), ["x"])
        self.assertEqual(clean_tags(""), [])


if __name__ == "__main__":
    unittest.main()
