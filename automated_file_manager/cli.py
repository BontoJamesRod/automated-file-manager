"""Command line interface: `afm organize` and `afm undo`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .categories import Classifier, load_categories
from .organizer import DATE_MODES, DUPLICATE_MODES, Organizer, undo_last_run


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="afm",
        description="Organize a folder by file type and handle duplicate files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    org = sub.add_parser("organize", help="sort files into category folders")
    org.add_argument("path", type=Path, help="folder to organize")
    org.add_argument("-n", "--dry-run", action="store_true", help="show what would happen, change nothing")
    org.add_argument("-r", "--recursive", action="store_true", help="also organize files in subfolders")
    org.add_argument(
        "--duplicates", choices=DUPLICATE_MODES, default="move",
        help="what to do with byte-identical copies: move to _Duplicates (default), delete, or skip",
    )
    org.add_argument(
        "--by-date", choices=DATE_MODES, default="none",
        help="add year or year/month subfolders (from modified time) inside each category",
    )
    org.add_argument("--config", type=Path, help="JSON file of {category: [extensions]} to customise rules")
    org.add_argument("--no-sniff", action="store_true", help="don't inspect file contents to classify unknown extensions")
    org.add_argument("-q", "--quiet", action="store_true", help="only print the summary")

    undo = sub.add_parser("undo", help="revert the most recent organize run")
    undo.add_argument("path", type=Path, help="the folder that was organized")
    return parser


def _cmd_organize(args: argparse.Namespace) -> int:
    try:
        categories = load_categories(args.config)
    except (OSError, ValueError) as exc:
        print(f"error: could not read config: {exc}", file=sys.stderr)
        return 2

    try:
        organizer = Organizer(
            args.path,
            recursive=args.recursive,
            duplicates=args.duplicates,
            by_date=args.by_date,
            classifier=Classifier(categories, sniff=not args.no_sniff),
            dry_run=args.dry_run,
        )
    except (NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = organizer.run()
    root = organizer.root
    prefix = "[dry run] " if report.dry_run else ""

    if not args.quiet:
        for a in report.actions:
            src = a.src.relative_to(root).as_posix()
            if a.kind == "move":
                print(f"{prefix}move       {src} -> {a.dst.relative_to(root).as_posix()}")
            elif a.kind == "duplicate":
                print(f"{prefix}duplicate  {src} -> {a.dst.relative_to(root).as_posix()}"
                      f"  (same as {a.original.relative_to(root).as_posix()})")
            elif a.kind == "delete":
                print(f"{prefix}delete     {src}  (same as {a.original.relative_to(root).as_posix()})")
            else:
                print(f"{prefix}skip       {src}  (duplicate of {a.original.relative_to(root).as_posix()})")
            if a.error:
                print(f"  ! failed: {a.error}", file=sys.stderr)

    moved = report.of_kind("move")
    parts = [f"{len(moved)} organized"]
    dupes = len(report.of_kind("duplicate")) + len(report.of_kind("delete")) + len(report.of_kind("skip"))
    if dupes:
        verb = {"move": "moved to _Duplicates", "delete": "deleted", "skip": "left in place"}[args.duplicates]
        parts.append(f"{dupes} duplicate(s) {verb} ({_human(report.duplicate_bytes)})")
    if report.errors:
        parts.append(f"{len(report.errors)} error(s)")
    print(f"{prefix}Summary: " + ", ".join(parts) + ".")
    if not report.dry_run and (moved or dupes) and args.duplicates != "delete":
        print("Run `afm undo` on this folder to revert.")
    return 1 if report.errors else 0


def _cmd_undo(args: argparse.Namespace) -> int:
    path = args.path
    if not path.is_dir():
        print(f"error: {path} is not a directory", file=sys.stderr)
        return 2
    result = undo_last_run(path)
    if not result.had_history:
        print("Nothing to undo: no previous run found in this folder.")
        return 1
    print(f"Restored {result.restored} file(s)"
          + (f", skipped {result.skipped} that had moved or been renamed" if result.skipped else "")
          + ".")
    if result.deleted_unrecoverable:
        print(f"Note: {result.deleted_unrecoverable} duplicate(s) deleted in that run cannot be restored.")
    return 0


def _safe_console() -> None:
    # On Windows, output redirected to a file uses a legacy code page; a filename with an
    # emoji or CJK character would otherwise crash the printout. Replace what can't be shown.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _safe_console()
    args = build_parser().parse_args(argv)
    if args.command == "organize":
        return _cmd_organize(args)
    return _cmd_undo(args)


if __name__ == "__main__":
    raise SystemExit(main())
