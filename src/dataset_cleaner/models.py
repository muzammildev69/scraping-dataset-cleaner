"""Shared data models and exceptions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from dataset_cleaner import __version__


class DatasetCleanerError(Exception):
    """Base class for expected, user-facing errors."""


class InputError(DatasetCleanerError):
    """The input file is missing, unreadable, empty, malformed or unsupported."""


class OutputError(DatasetCleanerError):
    """The output (or report) path is unsafe or cannot be written."""


class OptionError(DatasetCleanerError):
    """The requested cleaning options are inconsistent or refer to unknown columns."""


@dataclass(frozen=True)
class CleaningOptions:
    """Switches that control how a dataset is cleaned.

    Column names in ``deduplicate_by``, ``drop_columns``, ``email_columns`` and
    ``url_columns`` are normalised with the same rules as the dataset's own
    column names, so ``"Email Address"`` and ``"email_address"`` are equivalent.
    """

    deduplicate: bool = True
    deduplicate_by: tuple[str, ...] = ()
    drop_columns: tuple[str, ...] = ()
    email_columns: tuple[str, ...] = ()
    url_columns: tuple[str, ...] = ()
    add_missing_scheme: bool = False
    strip_url_params: bool = False
    remove_invalid_emails: bool = False
    remove_invalid_urls: bool = False
    validate: bool = False


@dataclass
class InvalidValue:
    """One cell that failed syntax validation."""

    row: int
    column: str
    kind: str
    value: str


@dataclass
class ColumnRename:
    """A column whose name changed during normalisation."""

    original: str
    cleaned: str


@dataclass
class CleaningReport:
    """Everything that happened to a dataset, ready for display or JSON export."""

    tool_version: str = __version__
    input_file: str = ""
    output_file: str = ""
    original_rows: int = 0
    final_rows: int = 0
    original_columns: int = 0
    final_columns: int = 0
    empty_rows_removed: int = 0
    duplicate_rows_removed: int = 0
    invalid_rows_removed: int = 0
    invalid_emails: int = 0
    invalid_urls: int = 0
    cells_trimmed: int = 0
    emails_normalized: int = 0
    urls_normalized: int = 0
    missing_values: int = 0
    missing_values_by_column: dict[str, int] = field(default_factory=dict)
    columns_removed: list[str] = field(default_factory=list)
    columns_not_found: list[str] = field(default_factory=list)
    column_renames: list[ColumnRename] = field(default_factory=list)
    email_columns: list[str] = field(default_factory=list)
    url_columns: list[str] = field(default_factory=list)
    invalid_details: list[InvalidValue] = field(default_factory=list)
    invalid_details_truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary."""
        return asdict(self)
