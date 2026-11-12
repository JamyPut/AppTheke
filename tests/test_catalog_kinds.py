import sqlite3
import tempfile
import unittest
import webbrowser
from pathlib import Path
from unittest import mock

from core import launcher
from core.database import MAX_ICON_BYTES, Database
from core.launcher import LaunchError, open_website

ICON = b"\x89PNG-pretend-icon-bytes"
OTHER_ICON = b"\x89PNG-another-icon"


class CatalogKindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    # ---- websites ------------------------------------------------------

    def test_apps_are_the_default_kind(self):
        tool = self.db.get_tool(self.db.add_tool("7-Zip"))
        self.assertEqual((tool.kind, tool.site_url, tool.icon), ("app", "", None))

    def test_add_website(self):
        tool_id = self.db.add_tool(
            "Wikipedia", kind="website", site_url="wikipedia.org",
            description="Encyclopedia", category="Reference", tags="wiki, facts",
        )
        tool = self.db.get_tool(tool_id)
        self.assertEqual((tool.kind, tool.site_url), ("website", "https://wikipedia.org"))
        self.assertEqual((tool.category, tool.tags), ("Reference", ["facts", "wiki"]))

    def test_website_needs_a_valid_web_address_and_nothing_is_saved_otherwise(self):
        for bad in ("", "ftp://example.org", "file:///C:/x.exe", "javascript:alert(1)"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.db.add_tool("Site", kind="website", site_url=bad)
        self.assertEqual(self.db.count_tools(), 0)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self.db.add_tool("X", kind="spaceship")

    def test_name_error_mentions_websites(self):
        with self.assertRaises(ValueError) as ctx:
            self.db.add_tool(" ", kind="website", site_url="example.org")
        self.assertIn("website needs a name", str(ctx.exception))

    def test_app_ignores_a_site_url(self):
        tool_id = self.db.add_tool("App", site_url="https://example.org")
        self.assertEqual(self.db.get_tool(tool_id).site_url, "")

    def test_update_website_keeps_its_kind_and_cleans_the_address(self):
        tool_id = self.db.add_tool("Old", kind="website", site_url="example.org")
        self.db.update_tool(tool_id, "New", site_url="example.net/path", category="Web")
        tool = self.db.get_tool(tool_id)
        self.assertEqual((tool.name, tool.kind, tool.site_url), ("New", "website", "https://example.net/path"))

    def test_update_website_with_a_bad_address_changes_nothing(self):
        tool_id = self.db.add_tool("Site", kind="website", site_url="example.org")
        with self.assertRaises(ValueError):
            self.db.update_tool(tool_id, "Renamed", site_url="ftp://nope")
        tool = self.db.get_tool(tool_id)
        self.assertEqual((tool.name, tool.site_url), ("Site", "https://example.org"))

    def test_update_app_cannot_gain_a_site_url_or_change_kind(self):
        tool_id = self.db.add_tool("App")
        self.db.update_tool(tool_id, "App", site_url="https://example.org")
        tool = self.db.get_tool(tool_id)
        self.assertEqual((tool.kind, tool.site_url), ("app", ""))

    # ---- lists and counts ------------------------------------------------

    def test_lists_and_counts_are_split_by_kind(self):
        self.db.add_tool("Notepad++")
        self.db.add_tool("7-Zip")
        self.db.add_tool("Wikipedia", kind="website", site_url="wikipedia.org")
        self.assertEqual([t.name for t in self.db.list_tools(kind="app")], ["7-Zip", "Notepad++"])
        self.assertEqual([t.name for t in self.db.list_tools(kind="website")], ["Wikipedia"])
        self.assertEqual(len(self.db.list_tools()), 3)
        self.assertEqual((self.db.count_tools("app"), self.db.count_tools("website"), self.db.count_tools()), (2, 1, 3))

    def test_search_works_within_a_kind(self):
        self.db.add_tool("Wiki Reader")
        self.db.add_tool("Wikipedia", kind="website", site_url="wikipedia.org")
        self.assertEqual([t.name for t in self.db.list_tools("wiki", kind="website")], ["Wikipedia"])
        self.assertEqual([t.name for t in self.db.list_tools("wiki", kind="app")], ["Wiki Reader"])
        self.assertEqual(len(self.db.list_tools("wiki")), 2)

    def test_categories_and_tags_are_shared_and_pruned_across_kinds(self):
        app = self.db.add_tool("App", category="Dev", tags="code")
        site = self.db.add_tool("Site", kind="website", site_url="example.org", category="dev", tags="code")
        self.assertEqual((self.db.list_categories(), self.db.list_tags()), (["Dev"], ["code"]))
        self.db.delete_tool(app)
        self.assertEqual((self.db.list_categories(), self.db.list_tags()), (["Dev"], ["code"]))
        self.db.delete_tool(site)
        self.assertEqual((self.db.list_categories(), self.db.list_tags()), ([], []))

    # ---- icons -------------------------------------------------------------

    def test_icon_roundtrip(self):
        tool_id = self.db.add_tool("A", icon=ICON)
        self.assertEqual(self.db.get_tool(tool_id).icon, ICON)
        self.assertEqual(self.db.list_tools()[0].icon, ICON)

    def test_update_keeps_replaces_or_removes_the_icon(self):
        tool_id = self.db.add_tool("A", icon=ICON)
        self.db.update_tool(tool_id, "A renamed")                  # icon left out: kept
        self.assertEqual(self.db.get_tool(tool_id).icon, ICON)
        self.db.update_tool(tool_id, "A", icon=OTHER_ICON)         # replaced
        self.assertEqual(self.db.get_tool(tool_id).icon, OTHER_ICON)
        self.db.update_tool(tool_id, "A", icon=None)               # removed
        self.assertIsNone(self.db.get_tool(tool_id).icon)

    def test_set_icon(self):
        tool_id = self.db.add_tool("A")
        self.assertTrue(self.db.set_icon(tool_id, ICON))
        self.assertEqual(self.db.get_tool(tool_id).icon, ICON)
        self.assertTrue(self.db.set_icon(tool_id, None))
        self.assertIsNone(self.db.get_tool(tool_id).icon)
        self.assertFalse(self.db.set_icon(9999, ICON))

    def test_bad_icons_are_rejected_and_nothing_is_saved(self):
        with self.assertRaises(ValueError):
            self.db.add_tool("A", icon=b"x" * (MAX_ICON_BYTES + 1))
        with self.assertRaises(ValueError):
            self.db.add_tool("A", icon="not bytes")
        self.assertEqual(self.db.count_tools(), 0)
        tool_id = self.db.add_tool("B", icon=ICON)
        with self.assertRaises(ValueError):
            self.db.update_tool(tool_id, "B renamed", icon=12345)
        tool = self.db.get_tool(tool_id)
        self.assertEqual((tool.name, tool.icon), ("B", ICON))

    # ---- upgrading old catalogs ---------------------------------------------

    def test_version_1_database_is_upgraded_and_keeps_its_data(self):
        old_path = Path(self.tmp.name) / "v1.db"
        conn = sqlite3.connect(old_path)
        # The tools table as version 1.0 created it: has exe_path, none of the newer columns.
        conn.executescript(
            """
            CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
            CREATE TABLE tools (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                install_notes TEXT NOT NULL DEFAULT '', download_url TEXT NOT NULL DEFAULT '',
                exe_path TEXT NOT NULL DEFAULT '',
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO categories(name) VALUES ('search');
            INSERT INTO tools(name, version, exe_path, category_id)
                VALUES ('Everything', '1.4', 'C:\\Program Files\\Everything\\Everything.exe', 1);
            """
        )
        conn.commit()
        conn.close()

        db = Database(old_path)
        try:
            tool = db.list_tools()[0]
            self.assertEqual((tool.name, tool.version, tool.category), ("Everything", "1.4", "search"))
            self.assertEqual((tool.kind, tool.site_url, tool.icon), ("app", "", None))
            self.assertEqual(db.list_tools(kind="app")[0].name, "Everything")
            self.assertEqual(db.list_tools(kind="website"), [])
            site_id = db.add_tool("Wikipedia", kind="website", site_url="wikipedia.org", icon=ICON)
            self.assertEqual(db.get_tool(site_id).icon, ICON)
        finally:
            db.close()
        Database(old_path).close()  # opening again must not try to add the columns again


class OpenWebsiteTests(unittest.TestCase):
    def test_opens_in_the_default_browser(self):
        with mock.patch.object(launcher.webbrowser, "open", return_value=True) as opened:
            result = open_website("example.org/path")
        opened.assert_called_once_with("https://example.org/path")
        self.assertEqual(result, "https://example.org/path")

    def test_no_browser_available(self):
        with mock.patch.object(launcher.webbrowser, "open", return_value=False):
            with self.assertRaises(LaunchError) as ctx:
                open_website("https://example.org")
        self.assertIn("No web browser", str(ctx.exception))

    def test_browser_error_becomes_a_readable_message(self):
        with mock.patch.object(launcher.webbrowser, "open", side_effect=webbrowser.Error("boom")):
            with self.assertRaises(LaunchError) as ctx:
                open_website("https://example.org")
        self.assertIn("boom", str(ctx.exception))

    def test_anything_but_a_web_address_is_refused(self):
        for bad in ("", "file:///C:/Windows/notepad.exe", "javascript:alert(1)", "ftp://example.org", "a b.com"):
            with self.subTest(bad=bad), mock.patch.object(launcher.webbrowser, "open") as opened:
                with self.assertRaises(LaunchError):
                    open_website(bad)
                opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
