"""Plan and apply file moves: sort by type, detect duplicates, keep an undo log."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .categories import Classifier

LOG_NAME = ".afm_log.json"
DUPLICATES_DIR = "_Duplicates"
PARTIAL_SUFFIXES = {".crdownload", ".part", ".partial", ".tmp", ".download"}

DUPLICATE_MODES = ("move", "delete", "skip")
DATE_MODES = ("none", "year", "month")

# Files the OS or other programs own. Moving them is pointless at best and harmful at worst.
SYSTEM_FILE_NAMES = {"desktop.ini", "thumbs.db"}


def _has_hidden_attrs(st: os.stat_result) -> bool:
    """True for Windows files flagged Hidden or System (always False on other platforms)."""
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def file_hash(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Action:
    """One planned (or applied) operation on a single file.

    kind is one of:
      move       -> relocate into its category folder
      duplicate  -> byte-identical copy, relocate into _Duplicates
      delete     -> byte-identical copy, remove it
      skip       -> byte-identical copy, leave it where it is
    """

    kind: str
    src: Path
    dst: Optional[Path] = None
    category: str = ""
    size: int = 0
    original: Optional[Path] = None  # for duplicates: where the kept copy lives
    error: Optional[str] = None


@dataclass
class Report:
    actions: List[Action] = field(default_factory=list)
    dry_run: bool = False

    def of_kind(self, kind: str) -> List[Action]:
        return [a for a in self.actions if a.kind == kind]

    @property
    def errors(self) -> List[Action]:
        return [a for a in self.actions if a.error]

    @property
    def duplicate_bytes(self) -> int:
        """Space taken by duplicates (reclaimable if you delete them)."""
        return sum(a.size for a in self.actions if a.kind in ("duplicate", "delete", "skip"))


@dataclass
class UndoResult:
    restored: int = 0
    skipped: int = 0
    deleted_unrecoverable: int = 0
    had_history: bool = True


class Organizer:
    def __init__(
        self,
        root: Path,
        *,
        recursive: bool = False,
        duplicates: str = "move",
        by_date: str = "none",
        classifier: Optional[Classifier] = None,
        dry_run: bool = False,
    ):
        if duplicates not in DUPLICATE_MODES:
            raise ValueError(f"duplicates must be one of {DUPLICATE_MODES}")
        if by_date not in DATE_MODES:
            raise ValueError(f"by_date must be one of {DATE_MODES}")
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"{root} is not a directory")
        self.recursive = recursive
        self.duplicates = duplicates
        self.by_date = by_date
        self.classifier = classifier or Classifier()
        self.dry_run = dry_run
        self._managed_dirs: Set[str] = set(self.classifier.category_names) | {DUPLICATES_DIR}

    # ------------------------------------------------------------------ scanning

    def _eligible(self, path: Path) -> bool:
        name = path.name
        if name.startswith((".", "~$")) or name == LOG_NAME or name.lower() in SYSTEM_FILE_NAMES:
            return False
        if path.is_symlink() or not path.is_file():
            return False
        if path.suffix.lower() in PARTIAL_SUFFIXES:
            return False
        try:
            return not _has_hidden_attrs(path.stat())
        except OSError:
            return False

    def _iter_files(self) -> Iterator[Path]:
        if not self.recursive:
            for entry in sorted(self.root.iterdir()):
                if self._eligible(entry):
                    yield entry
            return

        for dirpath, dirnames, filenames in os.walk(self.root):
            current = Path(dirpath)
            dirnames[:] = sorted(
                d for d in dirnames
                if not d.startswith(".") and not (current == self.root and d in self._managed_dirs)
            )
            for name in sorted(filenames):
                entry = current / name
                if self._eligible(entry):
                    yield entry

    def _existing_organized(self) -> List[Path]:
        """Files already sitting in category folders, so reruns don't re-add duplicates."""
        found: List[Path] = []
        for name in self.classifier.category_names:
            folder = self.root / name
            if not folder.is_dir():
                continue
            for dirpath, _dirs, filenames in os.walk(folder):
                for fname in filenames:
                    entry = Path(dirpath) / fname
                    if self._eligible(entry):
                        found.append(entry)
        return found

    # ------------------------------------------------------------------ planning

    def _dest_dir(self, category: str, mtime: float) -> Path:
        base = self.root / category
        if self.by_date == "none":
            return base
        stamp = datetime.fromtimestamp(mtime)
        if self.by_date == "year":
            return base / f"{stamp:%Y}"
        return base / f"{stamp:%Y}" / f"{stamp:%m}"

    @staticmethod
    def _unique(dst: Path, reserved: Set[Path]) -> Path:
        candidate, n = dst, 1
        while candidate.exists() or candidate in reserved:
            candidate = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
            n += 1
        return candidate

    def plan(self) -> List[Action]:
        files = []
        for path in self._iter_files():
            try:
                st = path.stat()
            except OSError:
                continue
            files.append((st.st_mtime, str(path), path, st.st_size))
        # Oldest first, so the earliest copy of a file is the one that is kept.
        files.sort(key=lambda item: (item[0], item[1]))

        # size -> [(path to read from, path where that content will finally live)]
        known: Dict[int, List[Tuple[Path, Path]]] = {}
        for existing in self._existing_organized():
            try:
                known.setdefault(existing.stat().st_size, []).append((existing, existing))
            except OSError:
                continue

        hashes: Dict[Path, str] = {}

        def digest(path: Path) -> str:
            if path not in hashes:
                hashes[path] = file_hash(path)
            return hashes[path]

        reserved: Set[Path] = set()
        actions: List[Action] = []

        for mtime, _key, src, size in files:
            category = self.classifier.categorize(src)

            original: Optional[Path] = None
            if size > 0:  # empty files are all "identical" but not meaningfully duplicates
                candidates = known.get(size, [])
                if candidates:
                    src_hash = digest(src)
                    for read_path, final_path in candidates:
                        if digest(read_path) == src_hash:
                            original = final_path
                            break

            if original is not None:
                actions.append(self._duplicate_action(src, original, category, size, reserved))
                continue

            final = self._unique(self._dest_dir(category, mtime) / src.name, reserved)
            reserved.add(final)
            known.setdefault(size, []).append((src, final))
            actions.append(Action("move", src, final, category, size))

        return actions

    def _duplicate_action(
        self, src: Path, original: Path, category: str, size: int, reserved: Set[Path]
    ) -> Action:
        if self.duplicates == "move":
            dst = self._unique(self.root / DUPLICATES_DIR / src.name, reserved)
            reserved.add(dst)
            return Action("duplicate", src, dst, category, size, original)
        if self.duplicates == "delete":
            return Action("delete", src, None, category, size, original)
        return Action("skip", src, None, category, size, original)

    # ------------------------------------------------------------------ applying

    def run(self) -> Report:
        actions = self.plan()
        report = Report(actions, self.dry_run)
        if self.dry_run:
            return report

        moves: List[dict] = []
        deleted: List[str] = []

        for action in actions:
            try:
                if action.kind in ("move", "duplicate"):
                    assert action.dst is not None
                    action.dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(action.src), str(action.dst))
                    moves.append({
                        "src": self._rel(action.src),
                        "dst": self._rel(action.dst),
                        "kind": action.kind,
                    })
                elif action.kind == "delete":
                    action.src.unlink()
                    deleted.append(self._rel(action.src))
            except OSError as exc:
                action.error = str(exc)

        if moves or deleted:
            self._append_log(moves, deleted)
        if self.recursive:
            self._prune_empty_dirs(Path(self.root / m["src"]).parent for m in moves)
        return report

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _append_log(self, moves: List[dict], deleted: List[str]) -> None:
        log = _read_log(self.root)
        log["runs"].append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "moves": moves,
            "deleted": deleted,
        })
        _write_log(self.root, log)

    def _prune_empty_dirs(self, starts) -> None:
        for start in set(starts):
            _remove_empty_upwards(start, self.root)


# ---------------------------------------------------------------------- undo / log


def _read_log(root: Path) -> dict:
    path = root / LOG_NAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("runs"), list):
                return data
        except (OSError, ValueError):
            pass
    return {"runs": []}


def _write_log(root: Path, log: dict) -> None:
    path = root / LOG_NAME
    if not log["runs"]:
        path.unlink(missing_ok=True)
        return
    tmp = path.with_suffix(".tmp-write")
    tmp.write_text(json.dumps(log, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _remove_empty_upwards(directory: Path, root: Path) -> None:
    directory = Path(directory)
    while directory != root and root in directory.parents:
        try:
            directory.rmdir()  # only succeeds when empty
        except OSError:
            return
        directory = directory.parent


def undo_last_run(root: Path) -> UndoResult:
    """Move every file from the most recent run back to where it came from."""
    root = Path(root).resolve()
    log = _read_log(root)
    if not log["runs"]:
        return UndoResult(had_history=False)

    run = log["runs"].pop()
    result = UndoResult(deleted_unrecoverable=len(run.get("deleted", [])))

    for entry in reversed(run.get("moves", [])):
        src, dst = root / entry["src"], root / entry["dst"]
        if dst.exists() and not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            result.restored += 1
            _remove_empty_upwards(dst.parent, root)
        else:
            result.skipped += 1

    _write_log(root, log)
    return result
