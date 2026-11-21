"""NEXUS FileSort 0.2.0: English-only Windows desktop application.

No external Python dependencies. Uses safe, first-level-only organization.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import (
    APP_NAME, CATEGORIES, OUTPUT_DIR, VERSION, FileOrganizer, OrganizerError,
    Preview, preview_folder,
)
from settings import SettingsStore

COLORS = {
    "bg": "#0E111B", "panel": "#191E2C", "raised": "#252B3B",
    "text": "#F4F3FA", "muted": "#ABB4C8", "accent": "#9C80FF",
    "accent_dark": "#7059CF", "border": "#384057",
}


def friendly_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


class FileSortApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} | v{VERSION}")
        self.geometry("1120x760")
        self.minsize(870, 600)
        self.configure(bg=COLORS["bg"])
        self.engine = FileOrganizer()
        self.settings_store = SettingsStore()
        self.config_error = ""
        try:
            self.config_data = self.settings_store.load()
        except OrganizerError as error:
            self.config_data = {"version": 1, "last_folder": "", "custom_rules": {}}
            self.config_error = str(error)

        default_folder = Path.home() / "Downloads"
        if not default_folder.is_dir():
            default_folder = Path.home()
        last_folder = Path(self.config_data["last_folder"]) if self.config_data["last_folder"] else None
        if last_folder is not None and last_folder.is_dir():
            default_folder = last_folder

        self.path_text = tk.StringVar(value=str(default_folder))
        self.summary_text = tk.StringVar(value="Choose a folder and click Preview Files.")
        self.progress_text = tk.StringVar(value="Ready")
        self.rule_extension = tk.StringVar()
        self.rule_category = tk.StringVar(value="Documents")
        self.rule_count = tk.StringVar()
        self.history_info = tk.StringVar(value="No history loaded yet.")
        self.plan: Preview | None = None
        self._busy = False

        self._apply_style()
        self._create_ui()
        self._refresh_rules()
        self._refresh_history()
        if self.config_error:
            self.after(150, self._settings_warning)

    def _settings_warning(self) -> None:
        messagebox.showwarning(
            "Settings issue",
            self.config_error + "\n\nDefault settings have been loaded. "
            "Check the settings file before saving new rules.",
            parent=self,
        )

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        font = ("Segoe UI", 10)
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=font)
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI Semibold", 25))
        style.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=font)
        style.configure("Section.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI Semibold", 13))
        style.configure("Hint.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=COLORS["raised"], foreground=COLORS["text"], insertcolor=COLORS["text"], padding=8)
        style.configure("TCombobox", fieldbackground=COLORS["raised"], background=COLORS["raised"], foreground=COLORS["text"], padding=7,
                        arrowcolor=COLORS["text"], selectforeground=COLORS["text"], selectbackground=COLORS["accent_dark"])
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["raised"])], foreground=[("readonly", COLORS["text"])])
        style.configure("Primary.TButton", padding=(18, 10), background=COLORS["accent_dark"], foreground="white", borderwidth=0,
                        font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", COLORS["accent"]), ("disabled", COLORS["raised"])],
                  foreground=[("disabled", COLORS["muted"])])
        style.configure("Secondary.TButton", padding=(16, 10), background=COLORS["raised"], foreground=COLORS["text"], borderwidth=0, font=font)
        style.map("Secondary.TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["panel"])])
        style.configure("Treeview", background=COLORS["panel"], foreground=COLORS["text"], fieldbackground=COLORS["panel"],
                        rowheight=31, borderwidth=0, font=font)
        style.map("Treeview", background=[("selected", COLORS["accent_dark"])], foreground=[("selected", "white")])
        style.configure("Treeview.Heading", background=COLORS["raised"], foreground=COLORS["text"],
                        font=("Segoe UI Semibold", 9), padding=10, borderwidth=0)
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["panel"], foreground=COLORS["muted"],
                        padding=(24, 13), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", COLORS["raised"])], foreground=[("selected", COLORS["text"])])
        style.configure("Horizontal.TProgressbar", background=COLORS["accent"], troughcolor=COLORS["raised"], borderwidth=0)

    def _create_ui(self) -> None:
        root = ttk.Frame(self, padding=(25, 18, 25, 14))
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="NEXUS  /  FILESORT", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Organize your files safely. Offline. Private. In control.", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 18))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        self.organize_tab = ttk.Frame(self.tabs, padding=(10, 20, 10, 8))
        self.rules_tab = ttk.Frame(self.tabs, padding=(10, 20, 10, 8))
        self.history_tab = ttk.Frame(self.tabs, padding=(10, 20, 10, 8))
        self.tabs.add(self.organize_tab, text="Organize")
        self.tabs.add(self.rules_tab, text="Custom Rules")
        self.tabs.add(self.history_tab, text="History")

        self._create_organize_tab()
        self._create_rules_tab()
        self._create_history_tab()
        ttk.Label(root,
                  text="SAFETY: only files in the chosen folder are processed. Subfolders and links are skipped. "
                       "Files are never deleted or overwritten. Test with copies first.",
                  style="Hint.TLabel", wraplength=1050).pack(anchor="w", pady=(12, 0))

    @staticmethod
    def _table(parent: ttk.Frame, columns: tuple[str, ...], headings: tuple[tuple[str, int], ...]) -> ttk.Treeview:
        area = ttk.Frame(parent)
        area.pack(fill="both", expand=True, pady=(8, 4))
        tree = ttk.Treeview(area, columns=columns, show="headings", selectmode="browse")
        for (key, (label, width)) in zip(columns, headings):
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=70, stretch=True)
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def _create_organize_tab(self) -> None:
        tab = self.organize_tab
        ttk.Label(tab, text="Source folder", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 15))
        ttk.Entry(row, textvariable=self.path_text, state="readonly").pack(side="left", fill="x", expand=True)
        self.browse_button = ttk.Button(row, text="Choose Folder", style="Secondary.TButton", command=self.browse)
        self.browse_button.pack(side="left", padx=(12, 0))

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", pady=(0, 13))
        self.preview_button = ttk.Button(buttons, text="1. Preview Files", style="Secondary.TButton", command=self.make_preview)
        self.preview_button.pack(side="left", padx=(0, 10))
        self.organize_button = ttk.Button(buttons, text="2. Organize Files", style="Primary.TButton", command=self.organize, state="disabled")
        self.organize_button.pack(side="left", padx=(0, 10))
        self.undo_button = ttk.Button(buttons, text="Undo Last Batch", style="Secondary.TButton", command=self.undo)
        self.undo_button.pack(side="left")

        ttk.Label(tab, textvariable=self.summary_text, style="Subtitle.TLabel", wraplength=970).pack(anchor="w", pady=(0, 6))
        self.preview_tree = self._table(tab, ("filename", "category", "target", "size"), (
            ("FILE", 240), ("CATEGORY", 140), ("DESTINATION (PREVIEW)", 445), ("SIZE", 95)))
        ttk.Label(tab, text="Progress", style="Section.TLabel").pack(anchor="w", pady=(12, 6))
        self.progressbar = ttk.Progressbar(tab, mode="determinate", maximum=100)
        self.progressbar.pack(fill="x")
        ttk.Label(tab, textvariable=self.progress_text, style="Hint.TLabel").pack(anchor="w", pady=(6, 0))

    def _create_rules_tab(self) -> None:
        tab = self.rules_tab
        ttk.Label(tab, text="Custom extension rules", style="Section.TLabel").pack(anchor="w")
        ttk.Label(tab, text="Override the default category of a file extension. Example: .log → Documents.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(4, 15))
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Extension").pack(side="left", padx=(0, 8))
        self.extension_entry = ttk.Entry(row, textvariable=self.rule_extension, width=16)
        self.extension_entry.pack(side="left", padx=(0, 22))
        ttk.Label(row, text="Send to").pack(side="left", padx=(0, 8))
        self.category_picker = ttk.Combobox(row, textvariable=self.rule_category, values=CATEGORIES,
                                            state="readonly", width=20)
        self.category_picker.pack(side="left", padx=(0, 10))
        self.add_rule_button = ttk.Button(row, text="Save Rule", style="Primary.TButton", command=self.save_rule)
        self.add_rule_button.pack(side="left", padx=(0, 8))
        self.remove_rule_button = ttk.Button(row, text="Remove Selected", style="Secondary.TButton", command=self.remove_rule)
        self.remove_rule_button.pack(side="left")
        ttk.Label(tab, textvariable=self.rule_count, style="Subtitle.TLabel").pack(anchor="w", pady=(6, 4))
        self.rules_tree = self._table(tab, ("extension", "category"), (("FILE EXTENSION", 260), ("DESTINATION CATEGORY", 600)))
        ttk.Label(tab, text="Rules apply to the next Preview. Current files are never modified by changing a rule.",
                  style="Hint.TLabel").pack(anchor="w", pady=(6, 0))

    def _create_history_tab(self) -> None:
        tab = self.history_tab
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Organization history", style="Section.TLabel").pack(side="left")
        ttk.Button(row, text="Refresh", style="Secondary.TButton", command=self._refresh_history).pack(side="right")
        ttk.Label(tab, textvariable=self.history_info, style="Subtitle.TLabel").pack(anchor="w", pady=(4, 6))
        self.history_tree = self._table(tab, ("date", "folder", "files", "status"), (
            ("DATE", 185), ("SOURCE FOLDER", 445), ("FILES", 100), ("STATUS", 190)))
        ttk.Label(tab, text="Undo Last Batch on the Organize tab restores only the latest pending batch. "
                      "History is saved locally, even after restarting the app.",
                  style="Hint.TLabel", wraplength=950).pack(anchor="w", pady=(6, 0))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.browse_button.configure(state="disabled" if busy else "normal")
        self.preview_button.configure(state="disabled" if busy else "normal")
        ready = not busy and self.plan is not None and bool(self.plan.files)
        self.organize_button.configure(state="normal" if ready else "disabled")
        self.undo_button.configure(state="disabled" if busy else "normal")
        self.add_rule_button.configure(state="disabled" if busy else "normal")
        self.remove_rule_button.configure(state="disabled" if busy else "normal")

    def _save_config(self, new_config: dict) -> bool:
        try:
            self.settings_store.save(new_config)
        except OrganizerError as error:
            messagebox.showerror("Settings Error", str(error), parent=self)
            return False
        self.config_data = new_config
        return True

    def _invalidate_preview(self, reason: str) -> None:
        self.plan = None
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.summary_text.set(reason)
        self.progressbar["value"] = 0
        self.progress_text.set("Ready")
        self._set_busy(False)

    def browse(self) -> None:
        path = self.path_text.get()
        selected = filedialog.askdirectory(
            title="Select a folder to organize",
            initialdir=path if Path(path).is_dir() else str(Path.home()),
            mustexist=True,
        )
        if selected:
            self.path_text.set(selected)
            self._invalidate_preview("Folder selected. Click Preview Files to inspect the plan.")
            new_config = dict(self.config_data)
            new_config["last_folder"] = selected
            self._save_config(new_config)

    def make_preview(self) -> None:
        try:
            self.plan = preview_folder(self.path_text.get(), self.config_data["custom_rules"])
        except (OrganizerError, OSError) as error:
            self._invalidate_preview("Unable to generate preview.")
            messagebox.showerror("Preview Error", str(error), parent=self)
            return
        self.preview_tree.delete(*self.preview_tree.get_children())
        for entry in self.plan.files:
            self.preview_tree.insert("", "end", values=(
                entry.source.name, entry.category,
                str(entry.destination.relative_to(self.plan.folder)), friendly_size(entry.size)))
        total = sum(entry.size for entry in self.plan.files)
        self.summary_text.set(f"{len(self.plan.files)} files ready  |  {friendly_size(total)}  |  "
                              f"{len(self.plan.skipped)} skipped  |  No changes made")
        self.progress_text.set("Preview ready. Review the destinations before organizing.")
        self.progressbar["value"] = 0
        self._set_busy(False)

    def _progress(self, current: int, total: int, filename: str) -> None:
        self.progressbar["maximum"] = max(1, total)
        self.progressbar["value"] = current
        self.progress_text.set(f"{current}/{total}: {filename}")
        self.update_idletasks()

    @staticmethod
    def _result_text(result, moved: str) -> str:
        report = f"{moved}: {result.succeeded}\nSkipped / errors: {result.skipped}"
        if result.errors:
            report += "\n\nDetails:\n" + "\n".join(result.errors[:10])
            if len(result.errors) > 10:
                report += f"\n...and {len(result.errors) - 10} more issues"
        return report

    def organize(self) -> None:
        if self.plan is None or not self.plan.files:
            return
        if not messagebox.askyesno(
            "Confirm Organization",
            f"Move {len(self.plan.files)} files into {OUTPUT_DIR} inside the selected folder?\n\n"
            "No files will be deleted or overwritten. You can undo the last batch.",
            parent=self,
        ):
            return
        self._set_busy(True)
        try:
            result = self.engine.organize(self.plan, progress=self._progress)
        except (OrganizerError, OSError) as error:
            messagebox.showerror("Organization Stopped", str(error), parent=self)
            return
        finally:
            self.plan = None
            self._set_busy(False)
        messagebox.showinfo("Organization Result", self._result_text(result, "Moved"), parent=self)
        self._refresh_history()
        self.make_preview()

    def undo(self) -> None:
        try:
            if not self.engine.has_undo():
                messagebox.showinfo("Nothing to Undo", "No recent batches can be undone.", parent=self)
                return
        except OrganizerError as error:
            messagebox.showerror("Undo Unavailable", str(error), parent=self)
            return
        if not messagebox.askyesno(
            "Confirm Undo", "Restore files from the latest batch?\n\n"
            "Changed files and conflicts will be left untouched.", parent=self,
        ):
            return
        self._set_busy(True)
        try:
            result = self.engine.undo_last(progress=self._progress)
        except (OrganizerError, OSError) as error:
            messagebox.showerror("Undo Stopped", str(error), parent=self)
            return
        finally:
            self._set_busy(False)
        messagebox.showinfo("Undo Result", self._result_text(result, "Restored"), parent=self)
        self._refresh_history()
        self.make_preview()

    def save_rule(self) -> None:
        extension = self.rule_extension.get().strip().lower()
        if extension and not extension.startswith("."):
            extension = "." + extension
        new_config = dict(self.config_data)
        rules = dict(self.config_data["custom_rules"])
        rules[extension] = self.rule_category.get()
        new_config["custom_rules"] = rules
        if self._save_config(new_config):
            self.rule_extension.set("")
            self._refresh_rules()
            self._invalidate_preview("Rules changed. Preview again before organizing.")

    def remove_rule(self) -> None:
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showinfo("Select a Rule", "Select a custom rule to remove.", parent=self)
            return
        extension = self.rules_tree.item(selected[0], "values")[0]
        new_config = dict(self.config_data)
        rules = dict(self.config_data["custom_rules"])
        rules.pop(extension, None)
        new_config["custom_rules"] = rules
        if self._save_config(new_config):
            self._refresh_rules()
            self._invalidate_preview("Rule removed. Preview again before organizing.")

    def _refresh_rules(self) -> None:
        self.rules_tree.delete(*self.rules_tree.get_children())
        for extension, category in sorted(self.config_data["custom_rules"].items()):
            self.rules_tree.insert("", "end", values=(extension, category))
        self.rule_count.set(f"{len(self.config_data['custom_rules'])} custom rules saved")

    def _refresh_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        try:
            history = self.engine.list_batches()
        except OrganizerError as error:
            self.history_info.set(f"History unavailable: {error}")
            return
        for batch in history:
            raw_date = batch["created_at"]
            try:
                date = datetime.fromisoformat(raw_date).astimezone().strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date = raw_date or "Unknown"
            if batch["moved"] > 0:
                status = f"{batch['moved']} pending"
            elif batch["undone"] > 0:
                status = "Restored"
            elif batch["failed"] > 0:
                status = "Skipped / failed"
            else:
                status = "No changes"
            self.history_tree.insert("", "end", values=(date, batch["root"], batch["total"], status))
        self.history_info.set(f"{len(history)} recent batches (latest first). Stored on this computer.")


def main() -> None:
    app = FileSortApp()
    app.mainloop()


if __name__ == "__main__":
    main()
