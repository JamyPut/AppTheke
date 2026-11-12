"""Main window.

Left:  Apps / Websites tabs above a searchable list.
Right: one of three views - empty state, detail page, add/edit form.

Apps and websites share one list, one detail page and one form; the fields that
only make sense for one of them are shown or hidden depending on the tab.
"""

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

import customtkinter as ctk

from core.database import Database, Tool
from core.downloader import DownloadError, download
from core.errorlog import log_exception
from core.exeicon import extract_exe_icon
from core.exeinfo import read_program_info
from core.favicon import fetch_favicon
from core.icons import IconError, load_icon_file, to_image
from core.launcher import LaunchError, launch, open_website
from core.paths import downloads_dir, resource_path
from core.version import __version__

ERROR_COLOR = "#e5534b"
OK_COLOR = "#3fb950"
MUTED = "gray"
CARD_NORMAL = ("gray90", "gray20")
CARD_SELECTED = ("#bcd7f0", "#1f538d")
BADGE_COLOR = ("gray75", "gray30")
DELETE_COLOR = ("#c0392b", "#a93226")
DELETE_HOVER = ("#962d22", "#7d261c")

TAB_APPS, TAB_WEBSITES = "Apps", "Websites"
LIST_ICON, DETAIL_ICON, FORM_ICON = 32, 48, 48  # icon sizes in pixels


class App(ctk.CTk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.kind = "app"                    # which tab is open: "app" or "website"
        self.selected_id: int | None = None  # entry shown on the detail page
        self.editing_id: int | None = None   # None = the form is adding a new entry
        self.cards: dict[int, ctk.CTkFrame] = {}
        self.form_icon: bytes | None = None  # icon currently chosen in the form
        self.form_icon_changed = False       # did the user touch the icon while editing?
        self._icon_job = 0                   # numbers icon searches, so old results are ignored
        self._fill_job = 0                   # the same for "Fill from program"
        self._image_cache: dict = {}
        self._downloading = False
        self._events: queue.Queue = queue.Queue()

        self.title(f"AppTheke {__version__}")
        self._set_window_icon()
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

        self._apply_kind_texts()
        self.refresh_list()
        self.show_view("empty")

    def _set_window_icon(self) -> None:
        icon = resource_path("assets/icon.ico")
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except Exception:  # a missing or broken icon must never stop the app from starting
                pass

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

    @staticmethod
    def _show(widgets, visible: bool) -> None:
        """Show or hide a group of already-placed widgets."""
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    # ================= icons ================================================

    def _icon_image(self, icon: bytes | None, size: int):
        """Stored icon bytes as an image for a label, or None if there is none."""
        if not icon:
            return None
        key = (icon, size)
        if key not in self._image_cache:
            picture = to_image(icon)
            self._image_cache[key] = (
                ctk.CTkImage(light_image=picture, dark_image=picture, size=(size, size))
                if picture is not None
                else None
            )
        return self._image_cache[key]

    def _icon_widget(self, parent, name: str, icon: bytes | None, size: int):
        """The icon, or - when there is none - a tile with the first letter of the name."""
        image = self._icon_image(icon, size)
        if image is not None:
            return ctk.CTkLabel(parent, text="", image=image)
        tile = ctk.CTkFrame(
            parent, width=size, height=size, corner_radius=size // 4, fg_color=BADGE_COLOR
        )
        tile.grid_propagate(False)
        tile.grid_rowconfigure(0, weight=1)
        tile.grid_columnconfigure(0, weight=1)
        letter = (name.strip()[:1] or "?").upper()
        ctk.CTkLabel(
            tile, text=letter, font=ctk.CTkFont(size=max(12, size // 2), weight="bold")
        ).grid(row=0, column=0)
        return tile

    def _show_icon(self, holder, name: str, icon: bytes | None, size: int) -> None:
        """Replace whatever the holder frame shows with this icon."""
        for child in holder.winfo_children():
            child.destroy()
        self._icon_widget(holder, name, icon, size).grid(row=0, column=0)

    def _run_background(self, work, done) -> None:
        """Run work() in a thread; then call done(result, error) on the main thread.

        The thread never touches a widget or the database: it only returns a
        value, which this method hands over safely through a queue."""
        results: queue.Queue = queue.Queue()

        def runner() -> None:
            try:
                results.put((work(), None))
            except Exception as error:  # never let the thread die silently
                results.put((None, error))

        def poll() -> None:
            try:
                result, error = results.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            done(result, error)

        threading.Thread(target=runner, daemon=True).start()
        self.after(100, poll)

    # ================= left: tabs, search, list =============================

    def _build_list_panel(self) -> None:
        panel = ctk.CTkFrame(self)
        panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)
        self.tabs = ctk.CTkSegmentedButton(
            header, values=[TAB_APPS, TAB_WEBSITES], command=self.switch_tab
        )
        self.tabs.set(TAB_APPS)
        self.tabs.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="+ Add", width=80, command=self.start_add).grid(
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

    def _apply_kind_texts(self) -> None:
        """Texts that depend on which tab is open."""
        websites = self.kind == "website"
        self.search_entry.configure(
            placeholder_text="Search websites..." if websites else "Search apps..."
        )
        self.empty_label.configure(
            text=(
                "Select a website on the left to see its details,\nor add a new one."
                if websites
                else "Select an app on the left to see its details,\nor add a new one."
            )
        )

    def switch_tab(self, value: str) -> None:
        kind = "website" if value == TAB_WEBSITES else "app"
        if kind == self.kind:
            return
        self.kind = kind
        self.selected_id = None
        self.search_entry.delete(0, "end")
        self._apply_kind_texts()
        self.refresh_list()
        self.show_view("empty")

    def refresh_list(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.cards = {}

        search = self.search_entry.get()
        tools = self.db.list_tools(search, kind=self.kind)
        for row, tool in enumerate(tools):
            card = self._tool_card(tool)
            card.grid(row=row, column=0, sticky="ew", padx=4, pady=3)
            self.cards[tool.id] = card

        if not tools:
            noun = "websites" if self.kind == "website" else "apps"
            message = (
                f"No {noun} match your search."
                if search.strip()
                else f"No {noun} yet. Click '+ Add' to add your first one."
            )
            ctk.CTkLabel(
                self.list_frame, text=message, text_color=MUTED, wraplength=240
            ).grid(row=0, column=0, pady=20)

        total = self.db.count_tools(self.kind)
        self.count_label.configure(text=f"{len(tools)} shown, {total} total")

    def _tool_card(self, tool: Tool) -> ctk.CTkFrame:
        selected = tool.id == self.selected_id
        card = ctk.CTkFrame(
            self.list_frame, corner_radius=8,
            fg_color=CARD_SELECTED if selected else CARD_NORMAL,
        )
        card.grid_columnconfigure(1, weight=1)

        self._icon_widget(card, tool.name, tool.icon, LIST_ICON).grid(
            row=0, column=0, rowspan=2, padx=(10, 0), pady=8
        )

        title = tool.name + (f"  v{tool.version}" if tool.version else "")
        ctk.CTkLabel(card, text=title, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, sticky="ew", padx=10, pady=(8, 0)
        )

        details = []
        if tool.kind == "website":
            host = urlparse(tool.site_url).hostname
            if host:
                details.append(host)
        if tool.category:
            details.append(tool.category)
        if tool.tags:
            details.append(", ".join(f"#{t}" for t in tool.tags))
        if details:
            ctk.CTkLabel(
                card, text="  ·  ".join(details), anchor="w", text_color=MUTED,
                wraplength=220, justify="left",
            ).grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 8))
        else:
            ctk.CTkLabel(card, text="", height=4).grid(row=1, column=1)

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
        self.empty_label = ctk.CTkLabel(
            frame, text="", text_color=MUTED, font=ctk.CTkFont(size=15),
        )
        self.empty_label.grid(row=0, column=0)
        return frame

    # ================= right: detail view ===================================

    def _build_detail_view(self) -> ctk.CTkScrollableFrame:
        frame = ctk.CTkScrollableFrame(self.right)
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        header.grid_columnconfigure(1, weight=1)
        self.detail_icon_holder = ctk.CTkFrame(
            header, fg_color="transparent", width=DETAIL_ICON, height=DETAIL_ICON
        )
        self.detail_icon_holder.grid(row=0, column=0, padx=(0, 12))
        self.detail_name = ctk.CTkLabel(
            header, text="", anchor="w", justify="left", wraplength=480,
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.detail_name.grid(row=0, column=1, sticky="ew")

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
        self.open_site_button = ctk.CTkButton(
            buttons, text="Open website", command=self.open_selected_website
        )
        self.open_site_button.grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(buttons, text="Edit", width=80, command=self.start_edit).grid(
            row=0, column=3, padx=(0, 8)
        )
        ctk.CTkButton(
            buttons, text="Delete", width=80, command=self.delete_selected,
            fg_color=DELETE_COLOR, hover_color=DELETE_HOVER,
        ).grid(row=0, column=4)
        # Result of the last Launch / Open website click; sits under the buttons.
        self.launch_status = ctk.CTkLabel(
            buttons, text="", anchor="w", justify="left", wraplength=560
        )
        self.launch_status.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        self.progress = ctk.CTkProgressBar(frame)
        self.progress.set(0)
        self.progress.grid(row=4, column=0, sticky="ew", padx=8, pady=(6, 0))
        self.progress.grid_remove()
        self.download_status = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560
        )
        self.download_status.grid(row=5, column=0, sticky="ew", padx=8)

        _, self.detail_description = self._readonly_box(frame, 6, "Description")
        notes_label, self.detail_notes = self._readonly_box(frame, 8, "Install notes")

        url_label = ctk.CTkLabel(frame, text="Download URL")
        url_label.grid(row=10, column=0, sticky="w", padx=8, pady=(12, 0))
        self.detail_url = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED
        )
        self.detail_url.grid(row=11, column=0, sticky="ew", padx=8, pady=(2, 8))

        exe_label = ctk.CTkLabel(frame, text="Executable (used by Launch)")
        exe_label.grid(row=12, column=0, sticky="w", padx=8, pady=(4, 0))
        self.detail_exe = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED
        )
        self.detail_exe.grid(row=13, column=0, sticky="ew", padx=8, pady=(2, 8))

        site_label = ctk.CTkLabel(frame, text="Website address")
        site_label.grid(row=14, column=0, sticky="w", padx=8, pady=(12, 0))
        self.detail_site = ctk.CTkLabel(
            frame, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED
        )
        self.detail_site.grid(row=15, column=0, sticky="ew", padx=8, pady=(2, 8))

        # What belongs to apps only, and what to websites only.
        self._detail_app_only = [
            self.launch_button, self.download_button, self.download_status,
            notes_label, self.detail_notes, url_label, self.detail_url,
            exe_label, self.detail_exe,
        ]
        self._detail_site_only = [self.open_site_button, site_label, self.detail_site]
        return frame

    def _readonly_box(self, parent, row: int, label: str):
        """A text box you can select and copy from, but not type into.
        Returns (label widget, box)."""
        title = ctk.CTkLabel(parent, text=label)
        title.grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        box = ctk.CTkTextbox(parent, height=120, border_width=1, wrap="word")
        box.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        box.configure(state="disabled")
        return title, box

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
        website = tool.kind == "website"
        self._show(self._detail_app_only, not website)
        self._show(self._detail_site_only, website)

        self._show_icon(self.detail_icon_holder, tool.name, tool.icon, DETAIL_ICON)
        self.detail_name.configure(text=tool.name)
        meta = []
        if tool.version:
            meta.append(f"Version {tool.version}")
        if tool.category:
            meta.append(f"Category: {tool.category}")
        self.detail_meta.configure(
            text="  ·  ".join(meta) or ("No category" if website else "No version or category")
        )
        self.detail_tags.configure(
            text="  ".join(f"#{t}" for t in tool.tags) or "No tags"
        )
        self._set_readonly_text(self.detail_description, tool.description)
        self._set_readonly_text(self.detail_notes, tool.install_notes)
        self.detail_url.configure(text=tool.download_url or "(none)")
        self.detail_exe.configure(text=tool.exe_path or "(none)")
        self.detail_site.configure(text=tool.site_url or "(none)")

        # The message under the buttons belongs to the previously shown entry.
        if website:
            self.launch_status.configure(text="", text_color=MUTED)
            self.progress.grid_remove()
            return

        # Launch needs a saved path.
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
            panel, text="Add an app", font=ctk.CTkFont(size=20, weight="bold")
        )
        self.form_title.grid(row=0, column=0, sticky="w", padx=8, pady=(4, 8))

        # --- icon: preview, choose a picture, find it automatically, remove
        icon_row = ctk.CTkFrame(panel, fg_color="transparent")
        icon_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.form_icon_holder = ctk.CTkFrame(
            icon_row, fg_color="transparent", width=FORM_ICON, height=FORM_ICON
        )
        self.form_icon_holder.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkButton(
            icon_row, text="Choose picture...", width=130, command=self.choose_icon
        ).grid(row=0, column=1, padx=(0, 8))
        self.auto_icon_button = ctk.CTkButton(
            icon_row, text="From program", width=130, command=self.auto_icon
        )
        self.auto_icon_button.grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(
            icon_row, text="Remove", width=80, command=self.remove_icon,
            fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
        ).grid(row=0, column=3)
        self.icon_status = ctk.CTkLabel(
            icon_row, text="", anchor="w", justify="left", wraplength=420
        )
        self.icon_status.grid(row=1, column=1, columnspan=3, sticky="w", pady=(4, 0))

        _, self.name_entry = self._field(panel, 2, "Name *")
        version_label, self.version_entry = self._field(panel, 4, "Version")
        site_label, self.site_entry = self._field(panel, 6, "Website address *")

        ctk.CTkLabel(panel, text="Category (one per entry, type a new one or pick one)").grid(
            row=8, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self.category_box = ctk.CTkComboBox(panel, values=[])
        self.category_box.set("")
        self.category_box.grid(row=9, column=0, sticky="ew", padx=8, pady=(2, 0))

        _, self.tags_entry = self._field(panel, 10, "Tags (separate with commas)")
        url_label, self.url_entry = self._field(panel, 12, "Download URL")

        exe_label = ctk.CTkLabel(
            panel, text="Executable path (the installed program that Launch starts)"
        )
        exe_label.grid(row=14, column=0, sticky="w", padx=8, pady=(8, 0))
        exe_row = ctk.CTkFrame(panel, fg_color="transparent")
        exe_row.grid(row=15, column=0, sticky="ew", padx=8, pady=(2, 0))
        exe_row.grid_columnconfigure(0, weight=1)
        self.exe_entry = ctk.CTkEntry(
            exe_row, placeholder_text=r"C:\Program Files\MyTool\mytool.exe"
        )
        self.exe_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(exe_row, text="Browse...", width=90, command=self.browse_exe).grid(
            row=0, column=1, padx=(0, 8)
        )
        ctk.CTkButton(
            exe_row, text="Fill from program", width=130, command=self.fill_from_program
        ).grid(row=0, column=2)
        # Result of reading the program's name, version and description.
        self.details_status = ctk.CTkLabel(
            exe_row, text="", anchor="w", justify="left", wraplength=480
        )
        self.details_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        _, self.description_box = self._textbox(panel, 16, "Description", height=90)
        notes_label, self.notes_box = self._textbox(panel, 18, "Install notes", height=90)

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=20, column=0, sticky="e", padx=8, pady=(14, 4))
        ctk.CTkButton(
            buttons, text="Cancel", width=90, command=self.cancel_form,
            fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
        ).grid(row=0, column=0, padx=(0, 8))
        self.save_button = ctk.CTkButton(buttons, text="Add", command=self.save_tool)
        self.save_button.grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(panel, text="", anchor="w")
        self.status_label.grid(row=21, column=0, sticky="w", padx=8)

        self._form_app_only = [
            version_label, self.version_entry, url_label, self.url_entry,
            exe_label, exe_row, notes_label, self.notes_box,
        ]
        self._form_site_only = [site_label, self.site_entry]
        return panel

    def _field(self, parent, row: int, label: str):
        """A label with a one-line entry below it. Returns (label widget, entry)."""
        title = ctk.CTkLabel(parent, text=label)
        title.grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        entry = ctk.CTkEntry(parent)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return title, entry

    def _textbox(self, parent, row: int, label: str, height: int):
        """A label with a multi-line box below it. Returns (label widget, box)."""
        title = ctk.CTkLabel(parent, text=label)
        title.grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        box = ctk.CTkTextbox(parent, height=height, border_width=1, wrap="word")
        box.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(2, 0))
        return title, box

    def _configure_form_for_kind(self) -> None:
        website = self.kind == "website"
        self._show(self._form_app_only, not website)
        self._show(self._form_site_only, website)
        self.auto_icon_button.configure(text="Fetch favicon" if website else "From program")

    def _reset_form(self) -> None:
        self._icon_job += 1  # ignore any icon search that is still running
        self._fill_job += 1  # ... and any "Fill from program" that is still running
        for entry in (
            self.name_entry, self.version_entry, self.tags_entry, self.url_entry,
            self.exe_entry, self.site_entry,
        ):
            entry.delete(0, "end")
        for box in (self.description_box, self.notes_box):
            box.delete("1.0", "end")
        # Reload the dropdown so categories created or pruned since last time are right.
        self.category_box.configure(values=self.db.list_categories())
        self.category_box.set("")
        self.status_label.configure(text="")
        self.icon_status.configure(text="")
        self.details_status.configure(text="")
        self._configure_form_for_kind()
        self._set_form_icon(None, changed=False)

    def start_add(self) -> None:
        self.editing_id = None
        self._reset_form()
        self.form_title.configure(text="Add a website" if self.kind == "website" else "Add an app")
        self.save_button.configure(text="Add website" if self.kind == "website" else "Add app")
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
        self.site_entry.insert(0, tool.site_url)
        self.category_box.set(tool.category)
        self.tags_entry.insert(0, ", ".join(tool.tags))
        self.url_entry.insert(0, tool.download_url)
        self.exe_entry.insert(0, tool.exe_path)
        self.description_box.insert("1.0", tool.description)
        self.notes_box.insert("1.0", tool.install_notes)
        self._set_form_icon(tool.icon, changed=False)
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
            # Picking a program fills in what is still empty; it never overwrites your typing.
            self.fill_from_program(overwrite=False)

    def fill_from_program(self, overwrite: bool = True) -> None:
        """Fill name, version, description (and the icon, if there is none) from the program.

        The button replaces name, version and description with what the program
        says (overwrite=True). After Browse..., only empty fields are filled.
        """
        path = self.exe_entry.get().strip()
        if not path:
            self.details_status.configure(
                text="Enter the executable path first, or use Browse...", text_color=ERROR_COLOR
            )
            return
        want_icon = self.form_icon is None

        def work():
            info = read_program_info(path)
            icon = extract_exe_icon(path) if want_icon else None
            return info, icon

        self._fill_job += 1
        job = self._fill_job
        self.details_status.configure(text="Reading the program...", text_color=MUTED)

        def done(result, error) -> None:
            if job != self._fill_job:  # the form was closed or refilled meanwhile
                return
            info, icon = result if error is None and result else (None, None)
            filled = []
            if info is not None:
                for entry, value, label in (
                    (self.name_entry, info.name, "name"),
                    (self.version_entry, info.version, "version"),
                ):
                    if value and (overwrite or not entry.get().strip()):
                        entry.delete(0, "end")
                        entry.insert(0, value)
                        filled.append(label)
                current = self.description_box.get("1.0", "end").strip()
                if info.description and (overwrite or not current):
                    self.description_box.delete("1.0", "end")
                    self.description_box.insert("1.0", info.description)
                    filled.append("description")
            if icon is not None and self.form_icon is None:  # a picture chosen meanwhile wins
                self._set_form_icon(icon)
                filled.append("icon")
            elif "name" in filled and self.form_icon is None:
                self._set_form_icon(None, changed=self.form_icon_changed)  # new first letter

            if filled:
                self.details_status.configure(
                    text=f"Filled in from the program: {', '.join(filled)}.", text_color=OK_COLOR
                )
            elif info is not None:
                self.details_status.configure(
                    text="Nothing new to fill in: the fields already have values.", text_color=MUTED
                )
            else:
                self.details_status.configure(
                    text="Could not read details from this program.", text_color=ERROR_COLOR
                )

        self._run_background(work, done)

    def cancel_form(self) -> None:
        self._fill_job += 1
        self._icon_job += 1  # ignore any icon search that is still running
        if self.selected_id is not None:
            self.select_tool(self.selected_id)
        else:
            self.show_view("empty")

    # ---- the icon in the form --------------------------------------------

    def _set_form_icon(self, icon: bytes | None, changed: bool = True) -> None:
        self.form_icon = icon
        self.form_icon_changed = changed
        self._show_icon(self.form_icon_holder, self.name_entry.get(), icon, FORM_ICON)

    def _icon_message(self, text: str, color=MUTED) -> None:
        self.icon_status.configure(text=text, text_color=color)

    def choose_icon(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Choose a picture for the icon",
            filetypes=[
                ("Pictures", "*.png *.ico *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not chosen:  # dialog cancelled
            return
        try:
            icon = load_icon_file(chosen)
        except IconError as error:
            self._icon_message(str(error), ERROR_COLOR)
            return
        self._icon_job += 1  # a picture you chose beats an automatic search still running
        self._set_form_icon(icon)
        self._icon_message("Icon set.", OK_COLOR)

    def remove_icon(self) -> None:
        self._icon_job += 1
        self._set_form_icon(None)
        self._icon_message("")

    def auto_icon(self) -> None:
        """Find the icon from the program (apps) or the website (favicon)."""
        if self.kind == "website":
            address = self.site_entry.get().strip()
            if not address:
                self._icon_message("Enter the website address first.", ERROR_COLOR)
                return
            work = lambda: fetch_favicon(address)  # noqa: E731
        else:
            path = self.exe_entry.get().strip()
            if not path:
                self._icon_message("Enter the executable path first.", ERROR_COLOR)
                return
            work = lambda: extract_exe_icon(path)  # noqa: E731

        self._icon_job += 1
        job = self._icon_job
        self._icon_message("Looking for the icon...")

        def done(icon, error) -> None:
            if job != self._icon_job:  # the form was closed or the icon changed meanwhile
                return
            if error is not None or icon is None:
                self._icon_message("No icon found. Use 'Choose picture...' instead.", ERROR_COLOR)
                return
            self._set_form_icon(icon)
            self._icon_message("Icon found.", OK_COLOR)

        self._run_background(work, done)

    def _auto_icon_for_new(self, tool_id: int) -> None:
        """A new entry saved without an icon gets one looked up in the background."""
        tool = self.db.get_tool(tool_id)
        if tool is None:
            return
        if tool.kind == "website":
            address = tool.site_url
            work = lambda: fetch_favicon(address)  # noqa: E731
        elif tool.exe_path:
            path = tool.exe_path
            work = lambda: extract_exe_icon(path)  # noqa: E731
        else:
            return

        def done(icon, error) -> None:
            if error is not None or icon is None:
                return
            current = self.db.get_tool(tool_id)
            if current is None or current.icon is not None:
                return  # deleted, or given an icon by hand, in the meantime
            self.db.set_icon(tool_id, icon)
            self.refresh_list()
            if self.selected_id == tool_id:
                self._fill_detail(self.db.get_tool(tool_id))

        self._run_background(work, done)

    # ---- saving ------------------------------------------------------------

    def save_tool(self) -> None:
        fields = dict(
            name=self.name_entry.get(),
            description=self.description_box.get("1.0", "end"),
            category=self.category_box.get(),
            tags=self.tags_entry.get(),
        )
        if self.kind == "website":
            fields["site_url"] = self.site_entry.get()
        else:
            fields.update(
                version=self.version_entry.get(),
                install_notes=self.notes_box.get("1.0", "end"),
                download_url=self.url_entry.get(),
                exe_path=self.exe_entry.get(),
            )

        is_new = self.editing_id is None
        try:
            if is_new:
                tool_id = self.db.add_tool(kind=self.kind, icon=self.form_icon, **fields)
                # A search filter could hide the new entry, so clear it.
                self.search_entry.delete(0, "end")
            else:
                tool_id = self.editing_id
                if self.form_icon_changed:
                    fields["icon"] = self.form_icon
                self.db.update_tool(tool_id, **fields)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color=ERROR_COLOR)
            return

        self._icon_job += 1  # an icon search for the closed form must not apply any more
        self._fill_job += 1
        self.selected_id = tool_id
        self.refresh_list()
        self.select_tool(tool_id)
        if is_new and self.form_icon is None:
            self._auto_icon_for_new(tool_id)

    # ================= launch / open website ================================

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

    def open_selected_website(self) -> None:
        tool = self.db.get_tool(self.selected_id) if self.selected_id else None
        if tool is None or tool.kind != "website":
            return
        try:
            open_website(tool.site_url)
        except LaunchError as error:
            self.launch_status.configure(text=str(error), text_color=ERROR_COLOR)
            return
        self.launch_status.configure(
            text=f"Opened {tool.name} in your browser.", text_color=OK_COLOR
        )

    # ================= delete ===============================================

    def delete_selected(self) -> None:
        tool = self.db.get_tool(self.selected_id) if self.selected_id else None
        if tool is None:
            return
        consequence = (
            "This only removes the entry. The website itself is not affected."
            if tool.kind == "website"
            else "This only removes the catalog entry. Files you already downloaded stay on disk."
        )
        confirmed = messagebox.askyesno(
            "Delete entry",
            f"Delete '{tool.name}' from the catalog?\n\n{consequence}",
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
