"""SQLite catalog: tools, categories (one per tool) and tags (many per tool).

No UI code in here, so the web app in phase 2 can reuse it unchanged.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .paths import db_path as default_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS tools (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    install_notes TEXT NOT NULL DEFAULT '',
    download_url  TEXT NOT NULL DEFAULT '',
    category_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS tool_tags (
    tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (tool_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(name COLLATE NOCASE);
"""


@dataclass
class Tool:
    id: int
    name: str
    version: str = ""
    description: str = ""
    install_notes: str = ""
    download_url: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)


def clean_tags(raw: str | list[str]) -> list[str]:
    """Accept 'a, b, a' or a list; return trimmed, de-duplicated tags in order."""
    parts = raw.split(",") if isinstance(raw, str) else raw
    seen: dict[str, str] = {}
    for part in parts:
        tag = part.strip()
        if tag and tag.lower() not in seen:
            seen[tag.lower()] = tag
    return list(seen.values())


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path is not None else str(default_db_path())
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        # SQLite ignores foreign keys unless this is switched on per connection.
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---- helpers -------------------------------------------------------

    def _category_id(self, name: str) -> int | None:
        name = name.strip()
        if not name:
            return None
        self.conn.execute("INSERT OR IGNORE INTO categories(name) VALUES (?)", (name,))
        row = self.conn.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _set_tags(self, tool_id: int, tags: list[str]) -> None:
        self.conn.execute("DELETE FROM tool_tags WHERE tool_id = ?", (tool_id,))
        for tag in tags:
            self.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
            tag_id = self.conn.execute(
                "SELECT id FROM tags WHERE name = ?", (tag,)
            ).fetchone()["id"]
            self.conn.execute(
                "INSERT OR IGNORE INTO tool_tags(tool_id, tag_id) VALUES (?, ?)",
                (tool_id, tag_id),
            )

    def _to_tool(self, row: sqlite3.Row) -> Tool:
        tag_rows = self.conn.execute(
            "SELECT t.name FROM tags t JOIN tool_tags tt ON tt.tag_id = t.id "
            "WHERE tt.tool_id = ? ORDER BY t.name COLLATE NOCASE",
            (row["id"],),
        ).fetchall()
        return Tool(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            description=row["description"],
            install_notes=row["install_notes"],
            download_url=row["download_url"],
            category=row["category"] or "",
            tags=[r["name"] for r in tag_rows],
        )

    _SELECT = (
        "SELECT t.*, c.name AS category FROM tools t "
        "LEFT JOIN categories c ON c.id = t.category_id "
    )

    # ---- tools ---------------------------------------------------------

    def add_tool(
        self,
        name: str,
        version: str = "",
        description: str = "",
        install_notes: str = "",
        download_url: str = "",
        category: str = "",
        tags: str | list[str] = "",
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("A tool needs a name.")
        with self.conn:  # one transaction: all of it is saved, or none of it
            cur = self.conn.execute(
                "INSERT INTO tools(name, version, description, install_notes, "
                "download_url, category_id) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    name,
                    version.strip(),
                    description.strip(),
                    install_notes.strip(),
                    download_url.strip(),
                    self._category_id(category),
                ),
            )
            tool_id = cur.lastrowid
            self._set_tags(tool_id, clean_tags(tags))
        return tool_id

    def update_tool(
        self,
        tool_id: int,
        name: str,
        version: str = "",
        description: str = "",
        install_notes: str = "",
        download_url: str = "",
        category: str = "",
        tags: str | list[str] = "",
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("A tool needs a name.")
        with self.conn:
            cur = self.conn.execute(
                "UPDATE tools SET name = ?, version = ?, description = ?, "
                "install_notes = ?, download_url = ?, category_id = ? WHERE id = ?",
                (
                    name,
                    version.strip(),
                    description.strip(),
                    install_notes.strip(),
                    download_url.strip(),
                    self._category_id(category),
                    tool_id,
                ),
            )
            if cur.rowcount == 0:
                raise ValueError("That tool no longer exists.")
            self._set_tags(tool_id, clean_tags(tags))
            self._prune_unused()

    def delete_tool(self, tool_id: int) -> bool:
        """Remove a catalog entry. Returns False if it did not exist."""
        with self.conn:
            # tool_tags rows go with it (ON DELETE CASCADE).
            cur = self.conn.execute("DELETE FROM tools WHERE id = ?", (tool_id,))
            self._prune_unused()
        return cur.rowcount > 0

    def _prune_unused(self) -> None:
        """Drop categories and tags that no tool uses any more, so typos
        and renamed categories do not pile up in the dropdown."""
        self.conn.execute(
            "DELETE FROM categories WHERE id NOT IN "
            "(SELECT category_id FROM tools WHERE category_id IS NOT NULL)"
        )
        self.conn.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM tool_tags)"
        )

    def get_tool(self, tool_id: int) -> Tool | None:
        row = self.conn.execute(
            self._SELECT + "WHERE t.id = ?", (tool_id,)
        ).fetchone()
        return self._to_tool(row) if row else None

    def list_tools(self, search: str = "") -> list[Tool]:
        search = search.strip()
        if search:
            # Escape LIKE wildcards so searching for '%' or '_' matches literally.
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = self.conn.execute(
                self._SELECT
                + "WHERE t.name LIKE ? ESCAPE '\\' ORDER BY t.name COLLATE NOCASE",
                (f"%{escaped}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                self._SELECT + "ORDER BY t.name COLLATE NOCASE"
            ).fetchall()
        return [self._to_tool(r) for r in rows]

    # ---- categories / tags --------------------------------------------

    def list_categories(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM categories ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r["name"] for r in rows]

    def list_tags(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM tags ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [r["name"] for r in rows]
