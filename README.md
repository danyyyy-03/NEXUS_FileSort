# NEXUS FileSort 0.2.0 — English Edition

An offline Windows desktop app to sort files by category, without deleting or overwriting your files.

## What's new in 0.2.0

- English interface, error messages and category names.
- Cleaner dark UI with **Organize**, **Custom Rules** and **History** tabs.
- Custom `.extension → Category` rules saved locally between restarts.
- Read-only history of recent batches, including Undo status.
- Last selected folder remembered between restarts.
- Existing v0.1 Undo journals remain compatible, even if folders have Romanian names.

## Requirements

- Windows 10 or 11
- Python **3.12** to run from source; tkinter is included in a typical Windows Python installation
- No accounts, APIs, network access or external Python packages required at runtime

## Getting started

1. Extract the ZIP into a **new folder**; keep your v0.1 folder as a backup.
2. Double-click `run.bat` (or run `py -3.12 app.py` in Command Prompt).
3. Open Command Prompt in this folder and run `py -3.12 make_demo.py`.
4. Click **Choose Folder** and select `_TEST_FOLDER`.
5. Click **Preview Files**. Confirm the destinations are what you expect.
6. Click **Organize Files**, confirm the prompt, then **Undo Last Batch**.
7. Try **Custom Rules**: enter `.pdf` and choose `Documents`, save; preview again.
8. Open **History** to inspect what has happened.

## Build Windows EXE

Double-click `build.bat`. It uses Python 3.12 and installs PyInstaller if needed.
The executable is saved as `dist\NEXUS_FileSort.exe`. Build the EXE **on Windows**.
Test the executable with `_TEST_FOLDER` before using real data. The executable
is unsigned; Windows may show standard security prompts.

## File safety

- Preview is a dry run and does not create output directories.
- Only regular files at the **top level** of the selected folder are processed.
- Symbolic links, directory junctions and subfolders are skipped or refused.
- Destination: `NEXUS_Organized/<category>/` under the selected folder.
- Existing names are handled with `filename (1).ext`, not overwritten.
- Before moving, the app checks that each source file still matches its preview state.
- Undo records are persisted in `%LOCALAPPDATA%\NEXUS_FileSort\history.json`.
- Settings: `%LOCALAPPDATA%\NEXUS_FileSort\settings.json`.
- Undo never overwrites the original path; it refuses if a file has changed.
- The last 30 history batches are retained (oldest entries eventually expire).
- This application is **not a backup**. Test with copies before important files.

## What is not included yet

Native drag-and-drop onto the window, a signed Windows installer, automatic folder
monitoring and paid licensing. The ZIP contains **source code**, not a prebuilt EXE.

## Test command

```bat
py -3.12 -m unittest discover -s tests -v
```

## Source files

- `app.py`: dark GUI
- `core.py`: organization / persisted Undo engine
- `settings.py`: validation and persistent extension rules
- `make_demo.py`: harmless test files
- `tests/test_core.py`: automated tests
- `run.bat`, `build.bat`: Windows launch and build scripts

## License

MIT. See `LICENSE`.
