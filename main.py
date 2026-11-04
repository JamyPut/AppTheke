"""AppTheke entry point."""

import customtkinter as ctk

from core.database import Database
from gui.app import App


def main() -> None:
    ctk.set_appearance_mode("system")  # follow the Windows light/dark setting
    ctk.set_default_color_theme("blue")

    db = Database()  # apptheke.db next to the .exe (or project folder)
    App(db).mainloop()


if __name__ == "__main__":
    main()
