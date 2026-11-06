# automated-file-manager

Python automation tool that organizes files by type, with smart categorization and duplicate handling. No dependencies, just the standard library.

```
Downloads/                          Downloads/
  IMG_2041.jpg                        Documents/   invoice, report.pdf, notes.md
  IMG_2041 (copy).jpg        ──►      Images/      IMG_2041.jpg, screenshot
  invoice   (a PDF, no ext)           Code/        tool.py
  report.pdf                          _Duplicates/ IMG_2041 (copy).jpg
  tool.py
```

## Features

- **Sort by type.** Files move into folders such as `Images`, `Documents`, `Spreadsheets`, `Presentations`, `Ebooks`, `Videos`, `Audio`, `Archives`, `Code`, `Installers`, `Fonts`, and `Other`.
- **Smart categorization.** Extension rules come first. For files with a missing or unknown extension, it falls back to the MIME type and then to the file's actual contents (magic bytes), so an extensionless PDF or PNG still lands in the right place.
- **Duplicate handling.** Duplicates are detected by content (size match, then SHA-256), not by name. The oldest copy is kept. Extra copies are moved to `_Duplicates` (default), deleted, or left alone. Duplicates of files you organized in an earlier run are caught too.
- **Safe by default.** `--dry-run` previews every change. Every run is logged, and `afm undo` puts files back where they were. Name clashes become `name (1).ext` instead of overwriting.
- **Skips what it shouldn't touch.** Hidden and system files (dotfiles, Windows Hidden/System attributes, `desktop.ini`, `Thumbs.db`), Office lock files (`~$...`), symlinks, and in-progress downloads (`.crdownload`, `.part`, `.tmp`) are left alone. Empty files are never treated as duplicates.
- **Customizable.** Add or change categories with a small JSON file, and optionally sort into year or year/month subfolders.

## Install

Requires Python 3.9+.

```bash
git clone https://github.com/BontoJamesRod/automated-file-manager
cd automated-file-manager
pip install .
```

You can also run it without installing: `python -m automated_file_manager ...`

## Usage

```bash
# Preview first (changes nothing)
afm organize ~/Downloads --dry-run

# Organize the top level of a folder
afm organize ~/Downloads

# Include subfolders (emptied subfolders are removed)
afm organize ~/Downloads -r

# Revert the most recent run
afm undo ~/Downloads
```

### Options for `afm organize`

| Option | Description |
| --- | --- |
| `-n`, `--dry-run` | Show what would happen without changing anything |
| `-r`, `--recursive` | Also organize files inside subfolders |
| `--duplicates {move,delete,skip}` | Move copies to `_Duplicates` (default), delete them, or leave them in place |
| `--by-date {none,year,month}` | Add `2026/` or `2026/11/` subfolders inside each category (uses modified time) |
| `--config FILE` | JSON file of custom rules (see below) |
| `--no-sniff` | Don't inspect file contents for unknown extensions |
| `-q`, `--quiet` | Only print the summary |

`--duplicates delete` is the one option that can't be undone. Every other action is reversible with `afm undo`.

### Custom categories

`rules.json` maps a category name to a list of extensions. Extensions listed here move out of their default category.

```json
{
  "Ebooks": [".pdf"],
  "3D Models": [".stl", ".obj"]
}
```

```bash
afm organize ~/Downloads --config rules.json
```

## Use as a library

```python
from pathlib import Path
from automated_file_manager import Organizer

report = Organizer(Path.home() / "Downloads", duplicates="move", dry_run=True).run()
for action in report.actions:
    print(action.kind, action.src, "->", action.dst)
print(f"{report.duplicate_bytes} bytes taken by duplicates")
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT, see [LICENSE](LICENSE).
