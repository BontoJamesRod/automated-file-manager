import json

import pytest

from automated_file_manager import Classifier, load_categories


@pytest.mark.parametrize(
    "name,expected",
    [
        ("photo.JPG", "Images"),
        ("report.pdf", "Documents"),
        ("budget.xlsx", "Spreadsheets"),
        ("deck.pptx", "Presentations"),
        ("song.mp3", "Audio"),
        ("clip.mkv", "Videos"),
        ("backup.tar.gz", "Archives"),
        ("script.py", "Code"),
        ("setup.exe", "Installers"),
        ("mystery.zzz", "Other"),
        ("noextension", "Other"),
    ],
)
def test_extension_rules(tmp_path, name, expected):
    f = tmp_path / name
    f.write_bytes(b"plain bytes that match no signature")
    assert Classifier().categorize(f) == expected


def test_sniffs_extensionless_png(tmp_path):
    f = tmp_path / "download"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    assert Classifier().categorize(f) == "Images"


def test_sniffs_pdf_with_unknown_extension(tmp_path):
    f = tmp_path / "invoice.dat"
    f.write_bytes(b"%PDF-1.7\n...")
    assert Classifier().categorize(f) == "Documents"


def test_sniff_can_be_disabled(tmp_path):
    f = tmp_path / "download"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    assert Classifier(sniff=False).categorize(f) == "Other"


def test_mime_fallback_for_uncommon_audio_extension(tmp_path):
    f = tmp_path / "voice.amr"
    f.write_bytes(b"xxxx")
    assert Classifier().categorize(f) in ("Audio", "Other")  # depends on the OS mime table


def test_custom_config_moves_and_adds(tmp_path):
    cfg = tmp_path / "rules.json"
    cfg.write_text(json.dumps({"Ebooks": [".pdf"], "3D": ["stl", ".OBJ"]}))
    cats = load_categories(cfg)
    c = Classifier(cats)
    assert c.categorize(tmp_path / "book.pdf") == "Ebooks"
    assert c.categorize(tmp_path / "part.stl") == "3D"
    assert c.categorize(tmp_path / "mesh.obj") == "3D"
    assert ".pdf" not in cats["Documents"]


def test_bad_config_rejected(tmp_path):
    cfg = tmp_path / "rules.json"
    cfg.write_text(json.dumps({"Images": ".png"}))
    with pytest.raises(ValueError):
        load_categories(cfg)
