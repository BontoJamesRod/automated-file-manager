import os
import time

from automated_file_manager import Organizer, undo_last_run
from automated_file_manager.organizer import LOG_NAME


def make(root, rel, data=b"data", age=0):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if age:
        t = time.time() - age
        os.utime(path, (t, t))
    return path


def names(folder):
    return sorted(p.name for p in folder.iterdir() if p.is_file())


def test_sorts_files_into_category_folders(tmp_path):
    make(tmp_path, "a.jpg", b"1")
    make(tmp_path, "b.pdf", b"2")
    make(tmp_path, "c.mp3", b"3")
    make(tmp_path, "d.weird", b"4")
    report = Organizer(tmp_path).run()
    assert len(report.of_kind("move")) == 4
    assert names(tmp_path / "Images") == ["a.jpg"]
    assert names(tmp_path / "Documents") == ["b.pdf"]
    assert names(tmp_path / "Audio") == ["c.mp3"]
    assert names(tmp_path / "Other") == ["d.weird"]


def test_dry_run_changes_nothing(tmp_path):
    make(tmp_path, "a.jpg")
    make(tmp_path, "b.jpg", b"same")
    make(tmp_path, "c.jpg", b"same")
    report = Organizer(tmp_path, dry_run=True).run()
    assert report.dry_run and len(report.actions) == 3
    assert names(tmp_path) == ["a.jpg", "b.jpg", "c.jpg"]
    assert not (tmp_path / LOG_NAME).exists()
    assert not (tmp_path / "Images").exists()


def test_duplicates_moved_and_oldest_kept(tmp_path):
    make(tmp_path, "new copy.jpg", b"same", age=10)
    make(tmp_path, "original.jpg", b"same", age=1000)
    make(tmp_path, "unique.jpg", b"different")
    report = Organizer(tmp_path).run()
    assert names(tmp_path / "Images") == ["original.jpg", "unique.jpg"]
    assert names(tmp_path / "_Duplicates") == ["new copy.jpg"]
    dup = report.of_kind("duplicate")[0]
    assert dup.original == tmp_path.resolve() / "Images" / "original.jpg"
    assert report.duplicate_bytes == 4


def test_duplicate_delete_mode(tmp_path):
    make(tmp_path, "a.txt", b"same", age=100)
    make(tmp_path, "b.txt", b"same", age=10)
    Organizer(tmp_path, duplicates="delete").run()
    assert names(tmp_path / "Documents") == ["a.txt"]
    assert not (tmp_path / "_Duplicates").exists()
    assert not (tmp_path / "b.txt").exists()


def test_duplicate_skip_mode_leaves_file(tmp_path):
    make(tmp_path, "a.txt", b"same", age=100)
    make(tmp_path, "b.txt", b"same", age=10)
    Organizer(tmp_path, duplicates="skip").run()
    assert names(tmp_path / "Documents") == ["a.txt"]
    assert (tmp_path / "b.txt").exists()


def test_same_size_different_content_not_duplicate(tmp_path):
    make(tmp_path, "a.txt", b"aaaa")
    make(tmp_path, "b.txt", b"bbbb")
    report = Organizer(tmp_path).run()
    assert not report.of_kind("duplicate")
    assert names(tmp_path / "Documents") == ["a.txt", "b.txt"]


def test_empty_files_are_not_duplicates(tmp_path):
    make(tmp_path, "a.txt", b"")
    make(tmp_path, "b.txt", b"")
    report = Organizer(tmp_path).run()
    assert not report.of_kind("duplicate")
    assert names(tmp_path / "Documents") == ["a.txt", "b.txt"]


def test_name_collision_gets_suffix(tmp_path):
    make(tmp_path, "report.pdf", b"one")
    Organizer(tmp_path).run()
    make(tmp_path, "report.pdf", b"two - different")
    Organizer(tmp_path).run()
    assert names(tmp_path / "Documents") == ["report (1).pdf", "report.pdf"]


def test_rerun_detects_duplicate_of_already_organized_file(tmp_path):
    make(tmp_path, "a.png", b"pixels")
    Organizer(tmp_path).run()
    make(tmp_path, "a again.png", b"pixels")
    report = Organizer(tmp_path).run()
    assert len(report.of_kind("duplicate")) == 1
    assert names(tmp_path / "Images") == ["a.png"]
    assert names(tmp_path / "_Duplicates") == ["a again.png"]


def test_second_run_is_noop(tmp_path):
    make(tmp_path, "a.png", b"pixels")
    Organizer(tmp_path).run()
    report = Organizer(tmp_path).run()
    assert report.actions == []


def test_skips_hidden_symlinks_and_partial_downloads(tmp_path):
    make(tmp_path, ".hidden.jpg")
    make(tmp_path, "movie.mp4.crdownload")
    make(tmp_path, "real.jpg", b"x")
    (tmp_path / "link.jpg").symlink_to(tmp_path / "real.jpg")
    Organizer(tmp_path).run()
    assert (tmp_path / ".hidden.jpg").exists()
    assert (tmp_path / "movie.mp4.crdownload").exists()
    assert (tmp_path / "link.jpg").is_symlink()
    assert names(tmp_path / "Images") == ["real.jpg"]


def test_non_recursive_leaves_subfolders_alone(tmp_path):
    make(tmp_path, "sub/inner.jpg")
    Organizer(tmp_path).run()
    assert (tmp_path / "sub" / "inner.jpg").exists()


def test_recursive_collects_and_prunes_empty_dirs(tmp_path):
    make(tmp_path, "trip/day1/a.jpg", b"1")
    make(tmp_path, "trip/day2/b.jpg", b"2")
    make(tmp_path, "keep/notes.txt", b"3")
    Organizer(tmp_path, recursive=True).run()
    assert names(tmp_path / "Images") == ["a.jpg", "b.jpg"]
    assert names(tmp_path / "Documents") == ["notes.txt"]
    assert not (tmp_path / "trip").exists()
    assert not (tmp_path / "keep").exists()


def test_by_date_month_and_year(tmp_path):
    f = make(tmp_path, "a.jpg", b"1")
    stamp = time.mktime((2024, 3, 15, 12, 0, 0, 0, 0, -1))
    os.utime(f, (stamp, stamp))
    Organizer(tmp_path, by_date="month").run()
    assert (tmp_path / "Images" / "2024" / "03" / "a.jpg").exists()

    g = make(tmp_path, "b.jpg", b"2")
    os.utime(g, (stamp, stamp))
    Organizer(tmp_path, by_date="year").run()
    assert (tmp_path / "Images" / "2024" / "b.jpg").exists()


def test_undo_restores_everything(tmp_path):
    make(tmp_path, "a.jpg", b"1", age=100)
    make(tmp_path, "dup.jpg", b"1", age=10)
    make(tmp_path, "doc.pdf", b"2")
    Organizer(tmp_path).run()
    result = undo_last_run(tmp_path)
    assert result.restored == 3
    assert names(tmp_path) == ["a.jpg", "doc.pdf", "dup.jpg"]
    assert not (tmp_path / "Images").exists()
    assert not (tmp_path / "_Duplicates").exists()
    assert not (tmp_path / LOG_NAME).exists()


def test_undo_recreates_recursive_subfolders(tmp_path):
    make(tmp_path, "trip/a.jpg", b"1")
    Organizer(tmp_path, recursive=True).run()
    assert not (tmp_path / "trip").exists()
    undo_last_run(tmp_path)
    assert (tmp_path / "trip" / "a.jpg").exists()


def test_undo_only_reverts_last_run(tmp_path):
    make(tmp_path, "a.jpg", b"1")
    Organizer(tmp_path).run()
    make(tmp_path, "b.pdf", b"2")
    Organizer(tmp_path).run()
    undo_last_run(tmp_path)
    assert (tmp_path / "b.pdf").exists()
    assert (tmp_path / "Images" / "a.jpg").exists()


def test_undo_with_no_history(tmp_path):
    assert undo_last_run(tmp_path).had_history is False


def test_undo_reports_unrecoverable_deletes(tmp_path):
    make(tmp_path, "a.txt", b"same", age=100)
    make(tmp_path, "b.txt", b"same", age=10)
    Organizer(tmp_path, duplicates="delete").run()
    result = undo_last_run(tmp_path)
    assert result.deleted_unrecoverable == 1
    assert (tmp_path / "a.txt").exists() and not (tmp_path / "b.txt").exists()


def test_undo_skips_files_the_user_already_moved(tmp_path):
    make(tmp_path, "a.jpg", b"1")
    Organizer(tmp_path).run()
    (tmp_path / "Images" / "a.jpg").unlink()
    result = undo_last_run(tmp_path)
    assert result.restored == 0 and result.skipped == 1


def test_skips_office_lock_files_and_system_files(tmp_path):
    make(tmp_path, "~$report.docx", b"lock")
    make(tmp_path, "desktop.ini", b"[.ShellClassInfo]")
    make(tmp_path, "Thumbs.db", b"thumbs")
    make(tmp_path, "report.docx", b"real")
    Organizer(tmp_path).run()
    assert names(tmp_path / "Documents") == ["report.docx"]
    assert (tmp_path / "~$report.docx").exists()
    assert (tmp_path / "desktop.ini").exists()
    assert (tmp_path / "Thumbs.db").exists()
    assert not (tmp_path / "Other").exists()


def test_windows_hidden_and_system_attributes_detected():
    import stat as stat_mod
    from types import SimpleNamespace

    from automated_file_manager.organizer import _has_hidden_attrs

    assert _has_hidden_attrs(SimpleNamespace(st_file_attributes=stat_mod.FILE_ATTRIBUTE_HIDDEN))
    assert _has_hidden_attrs(SimpleNamespace(st_file_attributes=stat_mod.FILE_ATTRIBUTE_SYSTEM))
    assert not _has_hidden_attrs(SimpleNamespace(st_file_attributes=stat_mod.FILE_ATTRIBUTE_ARCHIVE))
    assert not _has_hidden_attrs(SimpleNamespace())  # non-Windows stat results
