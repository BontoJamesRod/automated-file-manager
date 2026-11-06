"""automated-file-manager: sort files into folders by type and handle duplicates."""

from .categories import DEFAULT_CATEGORIES, Classifier, load_categories
from .organizer import (
    DUPLICATES_DIR,
    Action,
    Organizer,
    Report,
    UndoResult,
    file_hash,
    undo_last_run,
)

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_CATEGORIES",
    "DUPLICATES_DIR",
    "Action",
    "Classifier",
    "Organizer",
    "Report",
    "UndoResult",
    "file_hash",
    "load_categories",
    "undo_last_run",
]
