"""Regression tests: run with python -m unittest discover -s tests -v."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import FileOrganizer, OrganizerError, OUTPUT_DIR, classify_file, preview_folder


class FileSortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "downloads"
        self.source.mkdir()
        self.engine = FileOrganizer(history_path=self.base / "appdata" / "history.json")

    def write(self, name, data=b"hello"):
        p = self.source / name
        p.write_bytes(data)
        return p

    def test_classification(self):
        self.assertEqual(classify_file("file.PDF"), "PDF")
        self.assertEqual(classify_file("photo.JpG"), "Images")
        self.assertEqual(classify_file("report.xlsx"), "Spreadsheets")
        self.assertEqual(classify_file("noextension"), "Other")

    def test_preview_does_not_modify_folder(self):
        self.write("photo.JPG")
        before = sorted(x.name for x in self.source.iterdir())
        plan = preview_folder(self.source)
        self.assertEqual(len(plan.files), 1)
        self.assertEqual(sorted(x.name for x in self.source.iterdir()), before)
        self.assertFalse((self.source / OUTPUT_DIR).exists())
        self.assertFalse(self.engine.history_path.exists())

    def test_move_and_undo_persistent(self):
        self.write("hello.pdf", b"important")
        self.write("song.mp3", b"sound")
        plan = preview_folder(self.source)
        moved = self.engine.organize(plan)
        self.assertEqual((moved.succeeded, moved.skipped), (2, 0))
        self.assertEqual((self.source / OUTPUT_DIR / "PDF" / "hello.pdf").read_bytes(), b"important")
        second_process = FileOrganizer(self.engine.history_path)
        self.assertTrue(second_process.has_undo())
        undone = second_process.undo_last()
        self.assertEqual((undone.succeeded, undone.skipped), (2, 0))
        self.assertEqual((self.source / "hello.pdf").read_bytes(), b"important")
        self.assertEqual((self.source / "song.mp3").read_bytes(), b"sound")
        self.assertFalse(second_process.has_undo())

    def test_name_collision_preserves_both(self):
        target = self.source / OUTPUT_DIR / "PDF"
        target.mkdir(parents=True)
        (target / "paper.pdf").write_bytes(b"old")
        self.write("paper.pdf", b"new")
        plan = preview_folder(self.source)
        self.assertEqual(plan.files[0].destination.name, "paper (1).pdf")
        self.engine.organize(plan)
        self.assertEqual((target / "paper.pdf").read_bytes(), b"old")
        self.assertEqual((target / "paper (1).pdf").read_bytes(), b"new")
        self.engine.undo_last()
        self.assertEqual((self.source / "paper.pdf").read_bytes(), b"new")
        self.assertEqual((target / "paper.pdf").read_bytes(), b"old")

    def test_source_changed_after_preview_is_skipped(self):
        file = self.write("notes.txt", b"a")
        plan = preview_folder(self.source)
        file.write_bytes(b"an entirely different file")
        result = self.engine.organize(plan)
        self.assertEqual((result.succeeded, result.skipped), (0, 1))
        self.assertTrue(file.exists())

    def test_undo_does_not_overwrite_original(self):
        original = self.write("notes.txt", b"old")
        self.engine.organize(preview_folder(self.source))
        original.write_bytes(b"new! do not touch")
        result = self.engine.undo_last()
        self.assertEqual((result.succeeded, result.skipped), (0, 1))
        self.assertEqual(original.read_bytes(), b"new! do not touch")
        self.assertTrue((self.source / OUTPUT_DIR / "Documents" / "notes.txt").exists())

    def test_undo_does_not_restore_modified_target(self):
        self.write("notes.txt", b"old")
        self.engine.organize(preview_folder(self.source))
        target = self.source / OUTPUT_DIR / "Documents" / "notes.txt"
        target.write_bytes(b"changed")
        result = self.engine.undo_last()
        self.assertEqual((result.succeeded, result.skipped), (0, 1))
        self.assertEqual(target.read_bytes(), b"changed")

    def test_subfolders_are_not_processed(self):
        nested = self.source / "subfolder"
        nested.mkdir()
        (nested / "secret.pdf").write_bytes(b"inner")
        self.assertEqual(len(preview_folder(self.source).files), 0)

    def test_symbolic_links_skipped_if_supported(self):
        outside = self.base / "outside.pdf"
        outside.write_bytes(b"outside")
        link = self.source / "alias.pdf"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available")
        plan = preview_folder(self.source)
        self.assertEqual(len(plan.files), 0)
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_output_symlink_rejected(self):
        external = self.base / "external"
        external.mkdir()
        output = self.source / OUTPUT_DIR
        try:
            output.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available")
        self.write("paper.pdf")
        with self.assertRaises(OrganizerError):
            preview_folder(self.source)

    def test_more_recent_batch_undone_first(self):
        first = self.write("one.pdf")
        self.engine.organize(preview_folder(self.source))
        second = self.write("two.mp3")
        self.engine.organize(preview_folder(self.source))
        self.engine.undo_last()
        self.assertTrue(second.exists())
        self.assertFalse(first.exists())
        self.engine.undo_last()
        self.assertTrue(first.exists())

    def test_crash_pending_move_recovers(self):
        source = self.write("incomplete.pdf", b"abc")
        plan = preview_folder(self.source)
        item = plan.files[0]
        item.destination.parent.mkdir(parents=True)
        source.rename(item.destination)
        history = {"version": 1, "batches": [{"id": "test", "root": str(self.source), "moves": [
            {"from": str(source), "to": str(item.destination), "fingerprint": item.identity(), "state": "moving"}
        ]}]}
        self.engine.history_path.parent.mkdir()
        self.engine.history_path.write_text(json.dumps(history), encoding="utf-8")
        result = self.engine.undo_last()
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(source.read_bytes(), b"abc")


if __name__ == "__main__":
    unittest.main()


class CustomRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'files'
        self.root.mkdir()
        self.engine = FileOrganizer(self.base / 'history.json')

    def test_custom_extension_rule_routes_file(self):
        (self.root / 'archive.pdf').write_text('a')
        plan = preview_folder(self.root, {'.pdf': 'Archives'})
        self.assertEqual(plan.files[0].category, 'Archives')
        self.engine.organize(plan)
        self.assertTrue((self.root / OUTPUT_DIR / 'Archives' / 'archive.pdf').exists())
        self.assertEqual(self.engine.undo_last().succeeded, 1)

    def test_custom_invalid_category_fails_safely(self):
        (self.root / 'file.pdf').write_text('a')
        with self.assertRaises(OrganizerError):
            preview_folder(self.root, {'.pdf': '../bad'})
        self.assertFalse((self.root / OUTPUT_DIR).exists())

    def test_undo_older_romanian_category_works(self):
        from core import _check_destination
        src = self.root / 'photo.png'
        src.write_bytes(b'old')
        destination = _check_destination(self.root, 'Imagini', create=True) / src.name
        plan = preview_folder(self.root)
        fingerprint = plan.files[0].identity()
        src.rename(destination)
        history = {'version': 1, 'batches': [{'root': str(self.root), 'moves': [
            {'from': str(src), 'to': str(destination), 'fingerprint': fingerprint, 'state': 'moved'}
        ]}]}
        self.engine.history_path.write_text(json.dumps(history), encoding='utf-8')
        self.assertEqual(self.engine.undo_last().succeeded, 1)
        self.assertEqual(src.read_bytes(), b'old')

    def test_history_counts(self):
        (self.root / 'a.pdf').write_text('a')
        self.engine.organize(preview_folder(self.root))
        history = self.engine.list_batches()
        self.assertEqual((history[0]['total'], history[0]['moved']), (1, 1))
        self.engine.undo_last()
        self.assertEqual(self.engine.list_batches()[0]['undone'], 1)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from settings import SettingsStore
        self.store = SettingsStore(Path(self.tmp.name) / 'settings.json')

    def test_round_trip(self):
        value = {'last_folder': 'C:/Work/Files', 'custom_rules': {'.abc': 'Documents'}}
        self.store.save(value)
        loaded = self.store.load()
        self.assertEqual(loaded['custom_rules'], value['custom_rules'])
        self.assertEqual(loaded['last_folder'], value['last_folder'])

    def test_invalid_extension_rejected(self):
        with self.assertRaises(OrganizerError):
            self.store.save({'last_folder': '', 'custom_rules': {'../evil': 'PDF'}})
        self.assertFalse(self.store.path.exists())

    def test_invalid_category_rejected(self):
        with self.assertRaises(OrganizerError):
            self.store.save({'last_folder': '', 'custom_rules': {'.foo': '../../something'}})

    def test_broken_settings_errors_without_overwrite(self):
        self.store.path.write_text('{not json', encoding='utf-8')
        with self.assertRaises(OrganizerError):
            self.store.load()
