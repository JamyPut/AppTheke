"""AppTheke entry point."""

import sqlite3
import tkinter
from tkinter import messagebox

import customtkinter as ctk

from core.database import Database
from core.paths import db_path
from gui.app import App


def open_database() -> Database | None:
    """Open the catalog, or explain why that is not possible and return None."""
    try:
        return Database()  # apptheke.db next to the .exe (or project folder)
    except (sqlite3.Error, OSError) as error:
        root = tkinter.Tk()
        root.withdraw()  # hide the empty main window; only the message shows
        messagebox.showerror(
            "AppTheke",
            f"AppTheke could not open its database:\n{db_path()}\n\n{error}\n\n"
            "Move the AppTheke folder to a place you can write to, such as "
            "Documents or a USB stick. Program Files is usually read-only.",
        )
        root.destroy()
        return None


def main() -> None:
    ctk.set_appearance_mode("system")  # follow the Windows light/dark setting
    ctk.set_default_color_theme("blue")

    db = open_database()
    if db is None:
        return
    App(db).mainloop()


if __name__ == "__main__":
    main()
