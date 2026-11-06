"""File categorization: extension rules first, then MIME type, then content sniffing."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Dict, Iterable, List, Optional

OTHER = "Other"

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg",
        ".heic", ".heif", ".ico", ".raw", ".cr2", ".nef", ".psd",
    ],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".tex", ".pages"],
    "Spreadsheets": [".xls", ".xlsx", ".xlsm", ".csv", ".tsv", ".ods", ".numbers"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Ebooks": [".epub", ".mobi", ".azw3"],
    "Videos": [
        ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp",
    ],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus", ".aiff"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".iso"],
    "Code": [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs",
        ".rb", ".php", ".sh", ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sql", ".ipynb",
    ],
    "Installers": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".appimage"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
}

# (offset, magic bytes, category). Used only when the extension is missing or unknown.
_SIGNATURES = [
    (0, b"\x89PNG\r\n\x1a\n", "Images"),
    (0, b"\xff\xd8\xff", "Images"),
    (0, b"GIF87a", "Images"),
    (0, b"GIF89a", "Images"),
    (0, b"%PDF-", "Documents"),
    (0, b"PK\x03\x04", "Archives"),
    (0, b"Rar!\x1a\x07", "Archives"),
    (0, b"7z\xbc\xaf\x27\x1c", "Archives"),
    (0, b"\x1f\x8b", "Archives"),
    (0, b"ID3", "Audio"),
    (0, b"OggS", "Audio"),
    (0, b"fLaC", "Audio"),
    (0, b"MZ", "Installers"),
]

_MIME_PREFIX = {
    "image": "Images",
    "audio": "Audio",
    "video": "Videos",
    "text": "Documents",
}


def _normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    return ext if ext.startswith(".") else "." + ext


def load_categories(path: Optional[Path] = None) -> Dict[str, List[str]]:
    """Return the category map, optionally customised by a JSON file.

    The JSON file maps category name -> list of extensions. Extensions listed there are
    moved out of their default category into the one you name, and new categories can be
    added freely.
    """
    categories = {name: list(exts) for name, exts in DEFAULT_CATEGORIES.items()}
    if path is None:
        return categories

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object of {category: [extensions]}")

    for name, exts in data.items():
        if not isinstance(exts, list) or not all(isinstance(e, str) for e in exts):
            raise ValueError(f"category {name!r} must map to a list of extension strings")
        wanted = {_normalize_ext(e) for e in exts}
        for existing in categories.values():
            existing[:] = [e for e in existing if e not in wanted]
        categories.setdefault(name, [])
        categories[name].extend(sorted(wanted))
    return categories


class Classifier:
    """Decides which category folder a file belongs in."""

    def __init__(self, categories: Optional[Dict[str, Iterable[str]]] = None, sniff: bool = True):
        source = categories if categories is not None else DEFAULT_CATEGORIES
        self.categories = {name: [_normalize_ext(e) for e in exts] for name, exts in source.items()}
        self.sniff = sniff
        self._by_ext: Dict[str, str] = {}
        for name, exts in self.categories.items():
            for ext in exts:
                self._by_ext[ext] = name

    @property
    def category_names(self) -> List[str]:
        return list(self.categories) + [OTHER]

    def categorize(self, path: Path) -> str:
        path = Path(path)
        ext = path.suffix.lower()

        if ext in self._by_ext:
            return self._by_ext[ext]

        if ext:
            mime, _ = mimetypes.guess_type(path.name)
            if mime:
                guess = _MIME_PREFIX.get(mime.split("/", 1)[0])
                if guess and guess in self.categories:
                    return guess

        if self.sniff:
            guess = self._sniff(path)
            if guess and guess in self.categories:
                return guess

        return OTHER

    @staticmethod
    def _sniff(path: Path) -> Optional[str]:
        try:
            with open(path, "rb") as fh:
                head = fh.read(32)
        except OSError:
            return None

        for offset, magic, category in _SIGNATURES:
            if head[offset:offset + len(magic)] == magic:
                return category

        # RIFF containers and ISO base media (mp4/m4a/heic) keep their type further in.
        if head[:4] == b"RIFF":
            kind = head[8:12]
            if kind == b"WEBP":
                return "Images"
            if kind == b"WAVE":
                return "Audio"
            if kind == b"AVI ":
                return "Videos"
        if head[4:8] == b"ftyp":
            brand = head[8:12]
            if brand == b"M4A ":
                return "Audio"
            if brand in (b"heic", b"heix", b"mif1", b"msf1"):
                return "Images"
            return "Videos"
        return None
