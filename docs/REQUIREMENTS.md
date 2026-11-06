# Requirements: automated-file-manager

| | |
| --- | --- |
| **Version** | 1.0 |
| **Status** | Implemented |
| **Owner** | James Rod Bonto ([@BontoJamesRod](https://github.com/BontoJamesRod)) |

## 1. Problem

Folders like Downloads and Desktop fill up with hundreds of mixed files: photos, PDFs, installers, archives, school and work documents. Many are saved more than once (`report (1).pdf`, `photo (copy).jpg`). Sorting them by hand is slow, and it's easy to miss which files are true copies, since a duplicate can have a completely different name.

## 2. Goal

A command-line tool that sorts a folder into category subfolders by file type and finds byte-identical duplicates. It must be safe enough to run on a real folder: you can preview the result first and undo it afterwards.

## 3. Users and main use case

- **User:** anyone with a cluttered folder who is comfortable running one command in a terminal.
- **Main flow:**
  1. Preview: `afm organize ~/Downloads --dry-run`
  2. Apply: `afm organize ~/Downloads`
  3. If the result isn't wanted: `afm undo ~/Downloads`

## 4. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Sort files into category folders by extension, case-insensitively: Images, Documents, Spreadsheets, Presentations, Ebooks, Videos, Audio, Archives, Code, Installers, Fonts. Anything unrecognized goes to `Other`. |
| FR-2 | When the extension is missing or unknown, fall back to the MIME type, then to the file's contents (magic bytes), so an extensionless PDF or PNG is still classified correctly. Content inspection can be turned off with `--no-sniff`. |
| FR-3 | Let users add categories or move extensions between them with a JSON file (`--config`). Reject a malformed config with a clear error. |
| FR-4 | Detect duplicates by content, not name: compare sizes first, then SHA-256 only where sizes match. Keep the oldest copy (by modified time). Never treat empty files as duplicates. Also catch copies of files that an earlier run already organized. |
| FR-5 | Let the user choose what happens to duplicates: move them to `_Duplicates` (default), delete them, or leave them in place (`--duplicates move\|delete\|skip`). |
| FR-6 | Never overwrite a file. If the destination name is taken, add a suffix: `name (1).ext`. |
| FR-7 | Provide a dry-run mode (`--dry-run`) that prints every planned action and changes nothing on disk. |
| FR-8 | Organize only the top level by default. With `--recursive`, also collect files from subfolders, without re-sorting the category folders, and remove subfolders the run leaves empty. |
| FR-9 | Optionally add date subfolders inside each category based on modified time (`--by-date year\|month`). |
| FR-10 | Record every run in a log inside the organized folder. `afm undo` reverts the most recent run, recreates removed subfolders, and skips files the user has since moved. Deleted duplicates can't be restored, and undo says how many there were. |
| FR-11 | Leave alone files that shouldn't be moved: dotfiles, files with the Windows Hidden or System attribute, `desktop.ini`, `Thumbs.db`, Office lock files (`~$...`), symlinks, and unfinished downloads (`.crdownload`, `.part`, `.partial`, `.tmp`, `.download`). |
| FR-12 | Provide a CLI with `afm organize` and `afm undo`. Print one line per action and a summary line with the space taken by duplicates. Exit with 0 on success, 1 if any file failed or there was nothing to undo, and 2 for bad input. |
| FR-13 | Expose the same features as a Python library (`Organizer`, `Classifier`, `undo_last_run`). |

## 5. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-1 | Python 3.9+, standard library only, with no third-party runtime dependencies. |
| NFR-2 | Works on Windows, macOS and Linux. |
| NFR-3 | Handles large files: hashing streams in 1 MB chunks and only runs when two files have the same size. |
| NFR-4 | Idempotent: running it twice on the same folder does nothing the second time. |
| NFR-5 | Every functional requirement is covered by automated tests that run on all three platforms on every push. |

## 6. Out of scope (v1.0)

- A graphical interface
- Watching a folder in the background or running on a schedule
- Cloud storage (Google Drive, OneDrive, etc.)
- Near-duplicate detection (e.g. resized or re-encoded copies of the same photo)
- Restoring duplicates removed with `--duplicates delete`
- Renaming files based on their contents

## 7. Acceptance criteria

Each requirement is met when the listed tests pass.

| Requirement | Tests |
| --- | --- |
| FR-1 | `test_extension_rules`, `test_sorts_files_into_category_folders` |
| FR-2 | `test_mime_fallback_for_uncommon_audio_extension`, `test_sniffs_extensionless_png`, `test_sniffs_pdf_with_unknown_extension`, `test_sniff_can_be_disabled`, `test_dlls_are_not_installers` |
| FR-3 | `test_custom_config_moves_and_adds`, `test_bad_config_rejected`, `test_config_flag` |
| FR-4 | `test_duplicates_moved_and_oldest_kept`, `test_same_size_different_content_not_duplicate`, `test_empty_files_are_not_duplicates`, `test_rerun_detects_duplicate_of_already_organized_file` |
| FR-5 | `test_duplicate_delete_mode`, `test_duplicate_skip_mode_leaves_file`, `test_reports_duplicates_in_summary` |
| FR-6 | `test_name_collision_gets_suffix` |
| FR-7 | `test_dry_run_changes_nothing`, `test_dry_run_flag` |
| FR-8 | `test_non_recursive_leaves_subfolders_alone`, `test_recursive_collects_and_prunes_empty_dirs` |
| FR-9 | `test_by_date_month_and_year` |
| FR-10 | `test_undo_restores_everything`, `test_undo_recreates_recursive_subfolders`, `test_undo_only_reverts_last_run`, `test_undo_with_no_history`, `test_undo_reports_unrecoverable_deletes`, `test_undo_skips_files_the_user_already_moved` |
| FR-11 | `test_skips_hidden_files_and_partial_downloads`, `test_skips_symlinks`, `test_skips_office_lock_files_and_system_files`, `test_windows_hidden_and_system_attributes_detected` |
| FR-12 | `test_organize_and_undo_roundtrip`, `test_missing_folder_is_an_error`, `test_undo_without_history` |
| FR-13 | All of `tests/test_organizer.py`, which drives the tool through the library API |
| NFR-2 | The CI workflow runs the full suite on Windows, macOS and Linux |
| NFR-4 | `test_second_run_is_noop` |

## 8. Possible next versions

- `--watch` mode that sorts new files as they arrive
- Exclude patterns (`--exclude "*.iso"`)
- An HTML or CSV report of what was moved
