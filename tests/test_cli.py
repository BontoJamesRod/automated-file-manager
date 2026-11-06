import json

from automated_file_manager.cli import main


def test_organize_and_undo_roundtrip(tmp_path, capsys):
    (tmp_path / "a.jpg").write_bytes(b"1")
    (tmp_path / "b.pdf").write_bytes(b"2")

    assert main(["organize", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "2 organized" in out
    assert (tmp_path / "Images" / "a.jpg").exists()

    assert main(["undo", str(tmp_path)]) == 0
    assert "Restored 2" in capsys.readouterr().out
    assert (tmp_path / "a.jpg").exists()


def test_dry_run_flag(tmp_path, capsys):
    (tmp_path / "a.jpg").write_bytes(b"1")
    assert main(["organize", "--dry-run", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out
    assert (tmp_path / "a.jpg").exists()


def test_reports_duplicates_in_summary(tmp_path, capsys):
    (tmp_path / "a.jpg").write_bytes(b"same")
    (tmp_path / "b.jpg").write_bytes(b"same")
    main(["organize", "-q", str(tmp_path)])
    assert "1 duplicate(s) moved to _Duplicates" in capsys.readouterr().out


def test_config_flag(tmp_path, capsys):
    cfg = tmp_path / "rules.json"
    cfg.write_text(json.dumps({"Ebooks": [".pdf"]}))
    work = tmp_path / "work"
    work.mkdir()
    (work / "x.pdf").write_bytes(b"1")
    assert main(["organize", str(work), "--config", str(cfg)]) == 0
    assert (work / "Ebooks" / "x.pdf").exists()


def test_missing_folder_is_an_error(tmp_path, capsys):
    assert main(["organize", str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_undo_without_history(tmp_path, capsys):
    assert main(["undo", str(tmp_path)]) == 1
    assert "Nothing to undo" in capsys.readouterr().out
