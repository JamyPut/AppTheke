"""Main window: searchable tool list on the left, add-tool form on the right."""

import customtkinter as ctk

from core.database import Database, Tool

ERROR_COLOR = "#e5534b"
OK_COLOR = "#3fb950"


class App(ctk.CTk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        self.title("AppTheke")
        self.geometry("1000x640")
        self.minsize(820, 520)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        self._build_list_panel()
        self._build_form_panel()
        self.refresh_list()

    # ---- left: search + list ------------------------------------------

    def _build_list_panel(self) -> None:
        panel = ctk.CTkFrame(self)
        panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(panel, text="Tools", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6)
        )

        self.search_entry = ctk.CTkEntry(panel, placeholder_text="Search by name...")
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        # Refresh after every key press, so results update as you type.
        self.search_entry.bind("<KeyRelease>", lambda _event: self.refresh_list())

        self.list_frame = ctk.CTkScrollableFrame(panel)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.count_label = ctk.CTkLabel(panel, text="", text_color="gray")
        self.count_label.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

    def refresh_list(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        search = self.search_entry.get()
        tools = self.db.list_tools(search)
        for row, tool in enumerate(tools):
            self._tool_card(tool).grid(row=row, column=0, sticky="ew", padx=4, pady=3)

        if not tools:
            message = "No tools match your search." if search.strip() else (
                "No tools yet. Add your first one on the right."
            )
            ctk.CTkLabel(self.list_frame, text=message, text_color="gray").grid(
                row=0, column=0, pady=20
            )

        total = len(self.db.list_tools())
        self.count_label.configure(text=f"{len(tools)} shown, {total} total")

    def _tool_card(self, tool: Tool) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.list_frame, corner_radius=8)
        card.grid_columnconfigure(0, weight=1)

        title = tool.name + (f"  v{tool.version}" if tool.version else "")
        ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="ew", padx=10, pady=(8, 0)
        )

        details = []
        if tool.category:
            details.append(tool.category)
        if tool.tags:
            details.append(", ".join(f"#{t}" for t in tool.tags))
        if details:
            ctk.CTkLabel(
                card, text="  ·  ".join(details), anchor="w", text_color="gray",
                wraplength=260, justify="left",
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        else:
            ctk.CTkLabel(card, text="", height=4).grid(row=1, column=0)
        return card

    # ---- right: add form -----------------------------------------------

    def _build_form_panel(self) -> None:
        panel = ctk.CTkScrollableFrame(self)
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="Add a tool", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=(4, 8)
        )

        self.name_entry = self._field(panel, 1, "Name *")
        self.version_entry = self._field(panel, 3, "Version")

        ctk.CTkLabel(panel, text="Category (one per tool, type a new one or pick one)").grid(
            row=5, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self.category_box = ctk.CTkComboBox(panel, values=self.db.list_categories())
        self.category_box.set("")
        self.category_box.grid(row=6, column=0, sticky="ew", padx=8, pady=(2, 0))

        self.tags_entry = self._field(panel, 7, "Tags (separate with commas)")
        self.url_entry = self._field(panel, 9, "Download URL")
        self.description_box = self._textbox(panel, 11, "Description", height=90)
        self.notes_box = self._textbox(panel, 13, "Install notes", height=90)

        ctk.CTkButton(panel, text="Add tool", command=self.save_tool).grid(
            row=15, column=0, sticky="e", padx=8, pady=(14, 4)
        )
        self.status_label = ctk.CTkLabel(panel, text="")
        self.status_label.grid(row=16, column=0, sticky="w", padx=8)

    def _field(self, parent, row: int, label: str) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        entry = ctk.CTkEntry(parent)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return entry

    def _textbox(self, parent, row: int, label: str, height: int) -> ctk.CTkTextbox:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        box = ctk.CTkTextbox(parent, height=height, border_width=1)
        box.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return box

    # ---- actions ---------------------------------------------------------

    def save_tool(self) -> None:
        name = self.name_entry.get().strip()
        try:
            self.db.add_tool(
                name=name,
                version=self.version_entry.get(),
                description=self.description_box.get("1.0", "end"),
                install_notes=self.notes_box.get("1.0", "end"),
                download_url=self.url_entry.get(),
                category=self.category_box.get(),
                tags=self.tags_entry.get(),
            )
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color=ERROR_COLOR)
            return

        self._clear_form()
        self.status_label.configure(text=f"Added '{name}'.", text_color=OK_COLOR)
        self.refresh_list()

    def _clear_form(self) -> None:
        for entry in (self.name_entry, self.version_entry, self.tags_entry, self.url_entry):
            entry.delete(0, "end")
        for box in (self.description_box, self.notes_box):
            box.delete("1.0", "end")
        # Refresh the dropdown so a category added just now is offered next time.
        self.category_box.configure(values=self.db.list_categories())
        self.category_box.set("")
        self.name_entry.focus()

    def _on_close(self) -> None:
        self.db.close()
        self.destroy()
