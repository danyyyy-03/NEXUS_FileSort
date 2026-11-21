"""NEXUS FileSort - safe, offline, non-recursive file organization engine.

Python 3.12+, standard library only. The target folder is always inside the
selected source folder. Files are never overwritten or intentionally deleted.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


APP_NAME = "NEXUS FileSort"
VERSION = "0.2.0"
OUTPUT_DIR = "NEXUS_Organized"

EXTENSIONS: dict[str, set[str]] = {
    "PDF": {".pdf"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg", ".heic", ".ico", ".raw"},
    "Documents": {".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub", ".pages"},
    "Spreadsheets": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
    "Presentations": {".ppt", ".pptx", ".odp", ".key"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".java", ".cpp", ".c", ".h", ".sql", ".ipynb"},
    "Installers": {".exe", ".msi", ".msix", ".apk", ".dmg"},
}


# Preserve Undo access to files organized by v0.1 with Romanian category names.
LEGACY_CATEGORIES = frozenset({
    "Imagini", "Documente", "Tabele", "Prezentari", "Video",
    "Arhive", "Cod", "Instalatoare", "Altele",
})
CATEGORIES = (*EXTENSIONS.keys(), "Other")


class OrganizerError(Exception):
    """A user-facing error that should be displayed without a traceback."""


@dataclass(frozen=True)
class FilePlan:
    source: Path
    destination: Path
    category: str
    size: int
    modified_ns: int
    device: int
    inode: int

    def identity(self) -> dict[str, int]:
        return {
            "size": self.size,
            "modified_ns": self.modified_ns,
            "device": self.device,
            "inode": self.inode,
        }


@dataclass
class Preview:
    folder: Path
    files: list[FilePlan] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


@dataclass
class OperationResult:
    succeeded: int = 0
    errors: list[str] = field(default_factory=list)
    skipped: int = 0


ProgressCallback = Callable[[int, int, str], None]


def classify_file(filename: str, custom_rules: dict[str, str] | None = None) -> str:
    extension = Path(filename).suffix.lower()
    if custom_rules and extension in custom_rules:
        category = custom_rules[extension]
        if category not in CATEGORIES:
            raise OrganizerError(f"Invalid custom category: {category}")
        return category
    for category, extensions in EXTENSIONS.items():
        if extension in extensions:
            return category
    return "Other"


def _lexists(path: Path) -> bool:
    """Unlike Path.exists(), detects broken symlinks too."""
    return os.path.lexists(os.fspath(path))


def _regular_file_stat(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise OrganizerError(f"Symbolic link is not a regular file: {path.name}")
    result = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(result.st_mode):
        raise OrganizerError(f"Not a regular file: {path.name}")
    return result


def _fingerprint_matches(path: Path, fingerprint: dict[str, int]) -> bool:
    try:
        info = _regular_file_stat(path)
    except (OSError, OrganizerError):
        return False
    return all(
        int(getattr(info, field)) == int(expected)
        for field, expected in (
            ("st_size", fingerprint["size"]),
            ("st_mtime_ns", fingerprint["modified_ns"]),
            ("st_dev", fingerprint["device"]),
            ("st_ino", fingerprint["inode"]),
        )
    )


def _safe_directory(path: Path, *, create: bool = False) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise OrganizerError(f"Folder is a symbolic link or junction: {path}")
    if _lexists(path):
        if os.name == "nt":
            attr = path.stat(follow_symlinks=False).st_file_attributes
            if attr & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise OrganizerError(f"Folder is a reparse point: {path}")
        if not path.is_dir():
            raise OrganizerError(f"A file exists where a folder is required: {path}")
        return
    if create:
        # Do not silently replace or redirect preexisting paths.
        try:
            path.mkdir()
        except FileExistsError as error:
            raise OrganizerError(f"Folder appeared during the operation: {path}") from error
    else:
        raise OrganizerError(f"Folder does not exist: {path}")


def _check_root(folder: Path) -> Path:
    folder = folder.expanduser().absolute()
    _safe_directory(folder)
    # Avoid directory junction/reparse points on Windows as entry points.
    if os.name == "nt":
        attr = folder.stat(follow_symlinks=False).st_file_attributes
        if attr & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise OrganizerError("Select a regular folder, not a junction or shortcut.")
    return folder


def _check_destination(root: Path, category: str, *, create: bool) -> Path:
    if category not in CATEGORIES and category not in LEGACY_CATEGORIES:
        raise OrganizerError("Invalid category in file plan.")
    _safe_directory(root)
    output = root / OUTPUT_DIR
    _safe_directory(output, create=create)
    target = output / category
    _safe_directory(target, create=create)
    return target


def _available_destination(target_dir: Path, filename: str, reserved: set[str]) -> Path:
    original = Path(filename)
    stem = original.stem
    suffix = original.suffix
    for attempt in range(10001):
        name = filename if attempt == 0 else f"{stem} ({attempt}){suffix}"
        candidate = target_dir / name
        key = str(candidate).casefold()
        if key not in reserved and not _lexists(candidate):
            reserved.add(key)
            return candidate
    raise OrganizerError(f"Too many files with the same name: {filename}")


def preview_folder(folder: str | Path, custom_rules: dict[str, str] | None = None) -> Preview:
    """Build a dry-run without moving or creating any files/folders."""
    root = _check_root(Path(folder))
    output = root / OUTPUT_DIR
    if _lexists(output):
        _safe_directory(output)

    result = Preview(folder=root)
    reserved: set[str] = set()
    try:
        paths = sorted(root.iterdir(), key=lambda p: (p.name.casefold(), p.name))
    except OSError as error:
        raise OrganizerError(f"Cannot read folder: {error}") from error

    for source in paths:
        if source.name == OUTPUT_DIR or source.name.casefold() == OUTPUT_DIR.casefold():
            result.skipped.append(f"{source.name}: organized output folder")
            continue
        try:
            metadata = _regular_file_stat(source)
        except (OSError, OrganizerError):
            result.skipped.append(f"{source.name}: not a readable regular file")
            continue
        category = classify_file(source.name, custom_rules)
        target_dir = output / category
        if _lexists(target_dir):
            _safe_directory(target_dir)
        destination = _available_destination(target_dir, source.name, reserved)
        result.files.append(
            FilePlan(
                source=source,
                destination=destination,
                category=category,
                size=metadata.st_size,
                modified_ns=metadata.st_mtime_ns,
                device=metadata.st_dev,
                inode=metadata.st_ino,
            )
        )
    return result


def default_history_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "NEXUS_FileSort" / "history.json"


class FileOrganizer:
    """Persisted journal with conservative move + undo behavior.

    The journal is stored outside of the organized folder. Every planned move
    gets a durable 'moving' record before the filesystem is changed.
    """

    def __init__(self, history_path: str | Path | None = None):
        self.history_path = Path(history_path) if history_path else default_history_path()

    def _load(self) -> dict:
        if not self.history_path.exists():
            return {"version": 1, "batches": []}
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
            if data.get("version") != 1 or not isinstance(data.get("batches"), list):
                raise ValueError("Undo journal has an invalid format.")
            return data
        except (OSError, ValueError, TypeError) as error:
            raise OrganizerError(f"Cannot read Undo journal: {error}") from error

    def _save(self, history: dict) -> None:
        tmp_name = None
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.history_path.parent,
                prefix="history_", suffix=".tmp", delete=False,
            ) as stream:
                tmp_name = stream.name
                json.dump(history, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.history_path)
        except OSError as error:
            raise OrganizerError(f"Cannot save Undo journal: {error}") from error
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    @staticmethod
    def _validate_item(item: FilePlan, root: Path) -> None:
        if item.source.parent != root:
            raise OrganizerError("Source is not directly inside the selected folder.")
        if item.destination.parent.parent != root / OUTPUT_DIR:
            raise OrganizerError("Destination is outside NEXUS_Organized.")
        if item.destination.parent.name != item.category:
            raise OrganizerError("Category does not match the destination folder.")
        if not _fingerprint_matches(item.source, item.identity()):
            raise OrganizerError(f"File changed or disappeared after preview: {item.source.name}")

    def organize(self, plan: Preview, progress: ProgressCallback | None = None) -> OperationResult:
        root = _check_root(plan.folder)
        history = self._load()  # Fail BEFORE moving any file when Undo is unavailable.
        result = OperationResult()
        if not plan.files:
            return result

        batch = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root": str(root),
            "moves": [],
        }
        history["batches"].append(batch)
        # Keep a bounded journal. This may discard Undo data older than 30 batches.
        history["batches"] = history["batches"][-30:]
        self._save(history)

        for index, item in enumerate(plan.files, start=1):
            if progress:
                progress(index, len(plan.files), item.source.name)
            entry = None
            try:
                self._validate_item(item, root)
                _check_destination(root, item.category, create=True)
                if _lexists(item.destination):
                    raise OrganizerError(f"Destination already exists: {item.destination.name}; refresh preview.")
                entry = {
                    "from": str(item.source),
                    "to": str(item.destination),
                    "fingerprint": item.identity(),
                    "state": "moving",
                }
                batch["moves"].append(entry)
                self._save(history)
                # Windows os.rename REFUSES to overwrite an existing destination.
                # This project targets Windows. Other OSs are test-only.
                if _lexists(item.destination):
                    raise OrganizerError("Destination appeared immediately before the move.")
                os.rename(item.source, item.destination)
                entry["state"] = "moved"
                self._save(history)
                result.succeeded += 1
            except (OSError, OrganizerError) as error:
                if entry is not None and entry["state"] == "moving":
                    # A failed save AFTER rename leaves the pending entry for recovery.
                    # Do not mark it as failed when destination may now contain the file.
                    if _lexists(item.source) and not _lexists(item.destination):
                        entry["state"] = "failed"
                        try:
                            self._save(history)
                        except OrganizerError:
                            pass
                result.errors.append(f"{item.source.name}: {error}")
                result.skipped += 1
                # A journal failure requires stopping to avoid untracked moves.
                if isinstance(error, OrganizerError) and "Undo journal" in str(error):
                    break
        return result

    def _last_pending_batch(self, history: dict) -> dict | None:
        undoable = {"moving", "moved", "reverting", "undo_failed"}
        for batch in reversed(history["batches"]):
            if any(entry.get("state") in undoable for entry in batch.get("moves", [])):
                return batch
        return None

    def has_undo(self) -> bool:
        return self._last_pending_batch(self._load()) is not None

    def undo_last(self, progress: ProgressCallback | None = None) -> OperationResult:
        history = self._load()
        batch = self._last_pending_batch(history)
        if not batch:
            raise OrganizerError("No recent file moves to undo.")
        result = OperationResult()
        root = _check_root(Path(batch["root"]))
        pending = [e for e in reversed(batch["moves"]) if e["state"] in {"moving", "moved", "reverting", "undo_failed"}]

        for index, entry in enumerate(pending, start=1):
            original = Path(entry["from"])
            destination = Path(entry["to"])
            if progress:
                progress(index, len(pending), destination.name)
            try:
                if original.parent != root or destination.parent.parent != root / OUTPUT_DIR:
                    raise OrganizerError("Unsafe path detected in Undo journal; operation stopped.")
                _check_destination(root, destination.parent.name, create=False)
                # Crash recovery: move might not have happened, or undo already succeeded.
                if _lexists(original) and not _lexists(destination):
                    entry["state"] = "undone" if entry["state"] == "reverting" else "not_moved"
                    self._save(history)
                    result.skipped += 1
                    continue
                if _lexists(original):
                    raise OrganizerError("Original file already exists; it will not be overwritten.")
                if not _lexists(destination):
                    raise OrganizerError("Moved file can no longer be found.")
                if not _fingerprint_matches(destination, entry["fingerprint"]):
                    raise OrganizerError("Moved file has changed; refusing to restore it.")
                entry["state"] = "reverting"
                self._save(history)
                if _lexists(original):
                    raise OrganizerError("Original file reappeared; refusing to overwrite it.")
                os.rename(destination, original)
                entry["state"] = "undone"
                self._save(history)
                result.succeeded += 1
            except (OSError, OrganizerError, KeyError, ValueError) as error:
                result.errors.append(f"{destination.name}: {error}")
                result.skipped += 1
                if isinstance(error, OrganizerError) and "Undo journal" in str(error):
                    break
                entry["state"] = "undo_failed"
                try:
                    self._save(history)
                except OrganizerError:
                    break
        return result


    def list_batches(self) -> list[dict]:
        """Read-only batch summary, newest first (including undone)."""
        history = self._load()
        rows = []
        for batch in reversed(history["batches"]):
            states = [entry.get("state", "unknown") for entry in batch.get("moves", [])]
            rows.append({
                "created_at": batch.get("created_at", ""),
                "root": batch.get("root", ""),
                "total": len(states),
                "moved": sum(state in {"moved", "moving", "reverting", "undo_failed"} for state in states),
                "undone": sum(state == "undone" for state in states),
                "failed": sum(state in {"failed", "not_moved"} for state in states),
            })
        return rows
