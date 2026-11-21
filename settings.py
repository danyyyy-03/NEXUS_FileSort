"""Small validated settings store for NEXUS FileSort 0.2, standard library only."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from core import CATEGORIES, OrganizerError, default_history_path

EXTENSION_RE = re.compile(r"^\.[a-z0-9][a-z0-9_-]{0,15}$")


def settings_path() -> Path:
    return default_history_path().with_name("settings.json")


def validate_rules(rules: object) -> dict[str, str]:
    if not isinstance(rules, dict):
        raise OrganizerError("Custom rules must be an object of extensions and categories.")
    if len(rules) > 200:
        raise OrganizerError("Too many custom rules (maximum 200).")
    clean: dict[str, str] = {}
    for extension, category in rules.items():
        if not isinstance(extension, str) or not EXTENSION_RE.fullmatch(extension):
            raise OrganizerError(f"Invalid extension: {extension!r}. Example: .pdf")
        if not isinstance(category, str) or category not in CATEGORIES:
            raise OrganizerError(f"Invalid category for {extension}: {category!r}")
        clean[extension] = category
    return clean


class SettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else settings_path()

    def load(self) -> dict:
        default = {"version": 1, "last_folder": "", "custom_rules": {}}
        if not self.path.exists():
            return default
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("version") != 1:
                raise ValueError("Invalid settings format")
            folder = content.get("last_folder", "")
            if not isinstance(folder, str) or len(folder) > 4096:
                raise ValueError("Invalid last folder path")
            return {"version": 1, "last_folder": folder,
                    "custom_rules": validate_rules(content.get("custom_rules", {}))}
        except (OSError, ValueError, TypeError, OrganizerError) as error:
            raise OrganizerError(f"Cannot read settings: {error}") from error

    def save(self, config: dict) -> None:
        folder = config.get("last_folder", "")
        if not isinstance(folder, str) or len(folder) > 4096:
            raise OrganizerError("Invalid folder setting")
        clean = {"version": 1, "last_folder": folder,
                 "custom_rules": validate_rules(config.get("custom_rules", {}))}
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix="settings_", suffix=".tmp", delete=False,
            ) as stream:
                temporary = stream.name
                json.dump(clean, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise OrganizerError(f"Cannot save settings: {error}") from error
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
