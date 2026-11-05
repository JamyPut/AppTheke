"""Main window.

Left:  searchable tool list.
Right: one of three views - empty state, tool detail page, add/edit form.
"""

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.database import Database, Tool
from core.downloader import DownloadError, download
from core.errorlog import log_exception
from core.launcher import LaunchError, launch
from core.paths import downloads_dir
from core.version import __version__

ERROR_COLOR = "#e5534b"
OK_COLOR = "#3fb950"
MUTED = "gray"
CARD_NORMAL = ("gray90", "gray20")
CARD_SELECTED = ("#bcd7f0", "#1f538d")
DELETE_COLOR = ("#c0392b", "#a93226")
DELETE_HOVER = ("#962d22", "#7d261c")


class App(ctk.CTk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.selected_id: int | None = None  # tool shown on the detail page
        self.editing_id: int | None = None   # None = the form is adding a new tool
        self.cards: dict[int, ctk.CTkFrame] = {}
        self._downloading = False
        self._events: queue.Queue = queue.Queue()

        self.title(f"AppTheke {__version__}")
        self.geometry("1100x700")
        self.minsize(860, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        self._build_list_panel()

        self.right = ctk.CTkFrame(self, fg_color="transparent")
        self.right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=1)
        self.views = {
            "empty": self._build_empty_view(),
            "detail": self._build_detail_view(),
            "form": self._build_form_view(),
        }

        self.refresh_list()
        self.show_view("empty")

    def report_callback_exception(self, exc_type, exc, tb) -> None:
        """Tk calls this when a button or key handler raises. The packaged app has
        no console, so without this an error would pass without any sign."""
        path = log_exception(exc_type, exc, tb)
        where = (
            f"Details were saved to:\n{path}"
            if path
            else "The details could not be saved to a file."
        )
        messagebox.showerror("AppTheke", f"Something went wrong: {exc}\n\n{where}", parent=self)

    def show_view(self, name: str) -> None:
        for view in self.views.values():
            view.grid_remove()
        self.views[name].grid(row=0, column=0, sticky="nsew")

    # ================= left: search + list ==================================

    def _build_list_panel(self) -> None:
        panel = ctk.CTkFrame(self)
        panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Tools", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkButton(header, text="+ Add tool", width=90, command=self.start_add).grid(
            row=0, column=1, sticky="e"
        )

        self.search_entry = ctk.CTkEntry(panel, placeholder_text="Search by name...")
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        # Refresh after every key press, so results update as you type.
        self.search_entry.bind("<KeyRelease>", lambda _event: self.refresh_list())

        self.list_frame = ctk.CTkScrollableFrame(panel)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.count_label = ctk.CTkLabel(panel, text="", text_color=MUTED)
        self.count_label.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

    def refresh_list(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.cards = {}

        search = self.search_entry.get()
        tools = self.db.list_tools(search)
        for row, tool in enumerate(tools):
            card = self._tool_card(tool)
            card.grid(row=row, column=0, sticky="ew", padx=4, pady=3)
            self.cards[tool.id] = card

        if not tools:
            message = (
                "No tools match your search."
                if search.strip()
                else "No tools yet. Click '+ Add tool' to add your first one."
            )
            ctk.CTkLabel(
                self.list_frame, text=message, text_color=MUTED, wraplength=240
            ).grid(row=0, column=0, pady=20)

        total = len(self.db.list_tools())
        self.count_label.configure(text=f"{len(tools)} shown, {total} total")

    def _tool_card(self, tool: Tool) -> ctk.CTkFrame:
        selected = tool.id == self.selected_id
        card = ctk.CTkFrame(
            self.list_frame, corner_radius=8,
            fg_color=CARD_SELECTED if selected else CARD_NORMAL,
        )
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
                card, text="  ·  ".join(details), anchor="w", text_color=MUTED,
                wraplength=260, justify="left",
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        else:
            ctk.CTkLabel(card, text="", height=4).grid(row=1, column=0)

        self._bind_click(card, lambda _event, tid=tool.id: self.select_tool(tid))
        return card

    def _bind_click(self, widget, callback) -> None:
        """Make a card and everything inside it clickable."""
        widget.bind("<Button-1>", callback)
        for child in widget.winfo_children():
            self._bind_click(child, callback)

    def _update_highlight(self) -> None:
        for tool_id, card in self.cards.items():
            card.configure(fg_color=CARD_SELECTED if tool_id == self.selected_id else CARD_NORMAL)

    # ================= right: empty view ====================================

    def _build_empty_view(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.right)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text="Select a tool on the left to see its details,\nor add a new one.",
            text_color=MUTED, font=ctk.CTkFont(size=15),
        ).grid(row=0, column=0)
        return frame

    # ================= right: detail view ===================================

    def _build_detail_view(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.right)
        frame.grid_columnconfigure(0, weight=1)

        self.detail_name = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560,
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.detail_name.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.detail_meta = ctk.CTkLabel(frame, text="", anchor="w", text_color=MUTED)
        self.detail_meta.grid(row=1, column=0, sticky="ew", padx=8)
        self.detail_tags = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", text_color=MUTED, wraplength=560
        )
        self.detail_tags.grid(row=2, column=0, sticky="ew", padx=8)

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="w", padx=8, pady=(12, 4))
        self.launch_button = ctk.CTkButton(
            buttons, text="Launch", width=90, command=self.launch_selected
        )
        self.launch_button.grid(row=0, column=0, padx=(0, 8))
        self.download_button = ctk.CTkButton(buttons, text="Download", command=self.start_download)
        self.download_button.grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(buttons, text="Edit", width=80, command=self.start_edit).grid(
            row=0, column=2, padx=(0, 8)
        )
        ctk.CTkButton(
            buttons, text="Delete", width=80, command=self.delete_selected,
            fg_color=DELETE_COLOR, hover_color=DELETE_HOVER,
        ).grid(row=0, column=3)
        # Result of the last Launch click; sits under the buttons.
        self.launch_status = ctk.CTkLabel(
            buttons, text="", anchor="w", justify="left", wraplength=560
        )
        self.launch_status.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        self.progress = ctk.CTkProgressBar(frame)
        self.progress.set(0)
        self.progress.grid(row=4, column=0, sticky="ew", padx=8, pady=(6, 0))
        self.progress.grid_remove()
        self.download_status = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560
        )
        self.download_status.grid(row=5, column=0, sticky="ew", padx=8)

        self.detail_description = self._readonly_box(frame, 6, "Description")
        self.detail_notes = self._readonly_box(frame, 8, "Install notes")

        ctk.CTkLabel(frame, text="Download URL").grid(
            row=10, column=0, sticky="w", padx=8, pady=(12, 0)
        )
        self.detail_url = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED
        )
        self.detail_url.grid(row=11, column=0, sticky="ew", padx=8, pady=(2, 8))

        ctk.CTkLabel(frame, text="Executable (used by Launch)").grid(
            row=12, column=0, sticky="w", padx=8, pady=(4, 0)
        )
        self.detail_exe = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED
        )
        self.detail_exe.grid(row=13, column=0, sticky="ew", padx=8, pady=(2, 8))
        return frame

    def _readonly_box(self, parent, row: int, label: str) -> ctk.CTkTextbox:
        """A text box you can select and copy from, but not type into."""
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        box = ctk.CTkTextbox(parent, height=120, border_width=1, wrap="word")
        box.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        box.configure(state="disabled")
        return box

    @staticmethod
    def _set_readonly_text(box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text or "(none)")
        box.configure(state="disabled")

    def select_tool(self, tool_id: int) -> None:
        tool = self.db.get_tool(tool_id)
        if tool is None:  # deleted elsewhere; fall back to a clean state
            self.selected_id = None
            self.refresh_list()
            self.show_view("empty")
            return
        self.selected_id = tool_id
        self._fill_detail(tool)
        self._update_highlight()
        self.show_view("detail")

    def _fill_detail(self, tool: Tool) -> None:
        self.detail_name.configure(text=tool.name)
        meta = []
        if tool.version:
            meta.append(f"Version {tool.version}")
        if tool.category:
            meta.append(f"Category: {tool.category}")
        self.detail_meta.configure(text="  ·  ".join(meta) or "No version or category")
        self.detail_tags.configure(
            text="  ".join(f"#{t}" for t in tool.tags) or "No tags"
        )
        self._set_readonly_text(self.detail_description, tool.description)
        self._set_readonly_text(self.detail_notes, tool.install_notes)
        self.detail_url.configure(text=tool.download_url or "(none)")
        self.detail_exe.configure(text=tool.exe_path or "(none)")

        # Launch needs a saved path; the message belongs to the previously shown tool.
        self.launch_button.configure(state="normal" if tool.exe_path else "disabled")
        self.launch_status.configure(
            text="" if tool.exe_path else "No executable path yet. Use Edit to add one.",
            text_color=MUTED,
        )

        if not self._downloading:
            self.progress.grid_remove()
            self.download_status.configure(text="")
        has_url = bool(tool.download_url)
        self.download_button.configure(
            state="normal" if has_url and not self._downloading else "disabled"
        )
        if not has_url and not self._downloading:
            self.download_status.configure(
                text="No download URL yet. Use Edit to add one.", text_color=MUTED
            )

    # ================= right: add/edit form =================================

    def _build_form_view(self) -> ctk.CTkScrollableFrame:
        panel = ctk.CTkScrollableFrame(self.right)
        panel.grid_columnconfigure(0, weight=1)

        self.form_title = ctk.CTkLabel(
            panel, text="Add a tool", font=ctk.CTkFont(size=20, weight="bold")
        )
        self.form_title.grid(row=0, column=0, sticky="w", padx=8, pady=(4, 8))

        self.name_entry = self._field(panel, 1, "Name *")
        self.version_entry = self._field(panel, 3, "Version")

        ctk.CTkLabel(panel, text="Category (one per tool, type a new one or pick one)").grid(
            row=5, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self.category_box = ctk.CTkComboBox(panel, values=[])
        self.category_box.set("")
        self.category_box.grid(row=6, column=0, sticky="ew", padx=8, pady=(2, 0))

        self.tags_entry = self._field(panel, 7, "Tags (separate with commas)")
        self.url_entry = self._field(panel, 9, "Download URL")

        ctk.CTkLabel(
            panel,
            text="Executable path (the installed program that Launch starts)",
        ).grid(row=11, column=0, sticky="w", padx=8, pady=(8, 0))
        exe_row = ctk.CTkFrame(panel, fg_color="transparent")
        exe_row.grid(row=12, column=0, sticky="ew", padx=8, pady=(2, 0))
        exe_row.grid_columnconfigure(0, weight=1)
        self.exe_entry = ctk.CTkEntry(
            exe_row, placeholder_text=r"C:\Program Files\MyTool\mytool.exe"
        )
        self.exe_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(exe_row, text="Browse...", width=90, command=self.browse_exe).grid(
            row=0, column=1
        )

        self.description_box = self._textbox(panel, 13, "Description", height=90)
        self.notes_box = self._textbox(panel, 15, "Install notes", height=90)

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=17, column=0, sticky="e", padx=8, pady=(14, 4))
        ctk.CTkButton(
            buttons, text="Cancel", width=90, command=self.cancel_form,
            fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
        ).grid(row=0, column=0, padx=(0, 8))
        self.save_button = ctk.CTkButton(buttons, text="Add tool", command=self.save_tool)
        self.save_button.grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(panel, text="", anchor="w")
        self.status_label.grid(row=18, column=0, sticky="w", padx=8)
        return panel

    def _field(self, parent, row: int, label: str) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        entry = ctk.CTkEntry(parent)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return entry

    def _textbox(self, parent, row: int, label: str, height: int) -> ctk.CTkTextbox:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        box = ctk.CTkTextbox(parent, height=height, border_width=1, wrap="word")
        box.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return box

    def _reset_form(self) -> None:
        for entry in (
            self.name_entry, self.version_entry, self.tags_entry, self.url_entry, self.exe_entry
        ):
            entry.delete(0, "end")
        for box in (self.description_box, self.notes_box):
            box.delete("1.0", "end")
        # Reload the dropdown so categories created or pruned since last time are right.
        self.category_box.configure(values=self.db.list_categories())
        self.category_box.set("")
        self.status_label.configure(text="")

    def start_add(self) -> None:
        self.editing_id = None
        self._reset_form()
        self.form_title.configure(text="Add a tool")
        self.save_button.configure(text="Add tool")
        self.show_view("form")
        self.name_entry.focus()

    def start_edit(self) -> None:
        tool = self.db.get_tool(self.selected_id) if self.selected_id else None
        if tool is None:
            return
        self.editing_id = tool.id
        self._reset_form()
        self.name_entry.insert(0, tool.name)
        self.version_entry.insert(0, tool.version)
        self.category_box.set(tool.category)
        self.tags_entry.insert(0, ", ".join(tool.tags))
        self.url_entry.insert(0, tool.download_url)
        self.exe_entry.insert(0, tool.exe_path)
        self.description_box.insert("1.0", tool.description)
        self.notes_box.insert("1.0", tool.install_notes)
        self.form_title.configure(text=f"Edit {tool.name}")
        self.save_button.configure(text="Save changes")
        self.show_view("form")
        self.name_entry.focus()

    def browse_exe(self) -> None:
        current = self.exe_entry.get().strip()
        start_dir = Path(current).parent if current and Path(current).parent.is_dir() else None
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Choose the program to launch",
            initialdir=str(start_dir) if start_dir else None,
            filetypes=[
                ("Programs and shortcuts", "*.exe *.lnk *.bat *.cmd"),
                ("All files", "*.*"),
            ],
        )
        if chosen:  # empty when the dialog is cancelled
            self.exe_entry.delete(0, "end")
            self.exe_entry.insert(0, str(Path(chosen)))

    def cancel_form(self) -> None:
        if self.selected_id is not None:
            self.select_tool(self.selected_id)
        else:
            self.show_view("empty")

    def save_tool(self) -> None:
        fields = dict(
            name=self.name_entry.get(),
            version=self.version_entry.get(),
            description=self.description_box.get("1.0", "end"),
            install_notes=self.notes_box.get("1.0", "end"),
            download_url=self.url_entry.get(),
            exe_path=self.exe_entry.get(),
            category=self.category_box.get(),
            tags=self.tags_entry.get(),
        )
        try:
            if self.editing_id is None:
                tool_id = self.db.add_tool(**fields)
                # A search filter could hide the new tool, so clear it.
                self.search_entry.delete(0, "end")
            else:
                tool_id = self.editing_id
                self.db.update_tool(tool_id, **fields)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color=ERROR_COLOR)
            return

        self.selected_id = tool_id
        self.refresh_list()
        self.select_tool(tool_id)

    # ================= launch ===============================================

    def launch_selected(self) -> None:
        tool = self.db.get_tool(self.selected_id) if self.selected_id else None
        if tool is None:
            return
        try:
            launch(tool.exe_path)
        except LaunchError as error:
            self.launch_status.configure(text=str(error), text_color=ERROR_COLOR)
            return
        self.launch_status.configure(text=f"Started {tool.name}.", text_color=OK_COLOR)

    # ================= delete ===============================================

    def delete_selected(self) -> None:
        tool = self.db.get_tool(self.selected_id) if self.selected_id else None
        if tool is None:
            return
        confirmed = messagebox.askyesno(
            "Delete tool",
            f"Delete '{tool.name}' from the catalog?\n\n"
            "This only removes the catalog entry. Files you already downloaded stay on disk.",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return
        self.db.delete_tool(tool.id)
        self.selected_id = None
        self.refresh_list()
        self.show_view("empty")

    # ================= download =============================================

    def start_download(self) -> None:
        if self._downloading or self.selected_id is None:
            return
        tool = self.db.get_tool(self.selected_id)
        if tool is None or not tool.download_url:
            return

        folder = filedialog.askdirectory(
            parent=self,
            title=f"Save {tool.name} to...",
            initialdir=str(downloads_dir()),
            mustexist=True,
        )
        if not folder:  # dialog cancelled
            return

        self._downloading = True
        self._events = queue.Queue()
        self.download_button.configure(state="disabled")
        self.progress.set(0)
        self.progress.grid()
        self.download_status.configure(text=f"Connecting for {tool.name}...", text_color=MUTED)

        events, url, name = self._events, tool.download_url, tool.name

        def worker() -> None:
            # Runs in a background thread. It must not touch any widget, so it
            # only puts messages on the queue; the main thread reads them.
            try:
                path = download(
                    url, Path(folder),
                    progress=lambda done, total: events.put(("progress", done, total)),
                )
                events.put(("done", path))
            except DownloadError as error:
                events.put(("error", str(error)))
            except Exception as error:  # never let the thread die silently
                events.put(("error", f"Unexpected error: {error}"))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_download(name)

    def _poll_download(self, name: str) -> None:
        finished = False
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _, done, total = event
                    if total:
                        self.progress.set(done / total)
                        text = f"Downloading {name}: {done / 1e6:.1f} of {total / 1e6:.1f} MB"
                    else:
                        text = f"Downloading {name}: {done / 1e6:.1f} MB"
                    self.download_status.configure(text=text, text_color=MUTED)
                elif kind == "done":
                    self.progress.set(1)
                    self.download_status.configure(
                        text=f"Saved to {event[1]}", text_color=OK_COLOR
                    )
                    finished = True
                else:  # error
                    self.progress.grid_remove()
                    self.download_status.configure(text=event[1], text_color=ERROR_COLOR)
                    finished = True
        except queue.Empty:
            pass

        if finished:
            self._downloading = False
            current = self.db.get_tool(self.selected_id) if self.selected_id else None
            if current and current.download_url:
                self.download_button.configure(state="normal")
        else:
            self.after(100, lambda: self._poll_download(name))

    # ================= shutdown =============================================

    def _on_close(self) -> None:
        self.db.close()
        self.destroy()
