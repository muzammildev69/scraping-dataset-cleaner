"""Path safety checks and atomic file writing."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from dataset_cleaner.models import InputError, OutputError

SUPPORTED_EXTENSION = ".csv"


def _same_file(first: Path, second: Path) -> bool:
    """Return True if both paths point at the same file (even via links or ``..``)."""
    if first.resolve() == second.resolve():
        return True
    return second.exists() and first.exists() and os.path.samefile(first, second)


def _check_parent_directory(path: Path, label: str) -> None:
    parent = path.parent
    if not parent.exists():
        raise OutputError(f"{label} directory does not exist: {parent}")
    if not parent.is_dir():
        raise OutputError(f"{label} directory is not a directory: {parent}")
    if path.is_dir():
        raise OutputError(f"{label} path is a directory, not a file: {path}")


def validate_paths(input_path: Path, output_path: Path, report_path: Path | None = None) -> None:
    """Raise a helpful error if the paths are missing, unsupported or unsafe.

    The input file is never a valid output or report destination.
    """
    if input_path.suffix.lower() != SUPPORTED_EXTENSION:
        shown = input_path.suffix or "(none)"
        raise InputError(
            f"Unsupported input file type {shown!r}: only {SUPPORTED_EXTENSION} files are supported."
        )
    if not input_path.exists():
        raise InputError(f"Input file not found: {input_path}")
    if not input_path.is_file():
        raise InputError(f"Input path is not a file: {input_path}")

    if output_path.suffix.lower() != SUPPORTED_EXTENSION:
        raise OutputError(f"The output file must end in {SUPPORTED_EXTENSION}: {output_path}")
    _check_parent_directory(output_path, "Output")
    if _same_file(input_path, output_path):
        raise OutputError(
            f"The output path resolves to the input file ({input_path}). "
            "Refusing to overwrite the input; choose a different --output."
        )

    if report_path is not None:
        _check_parent_directory(report_path, "Report")
        if _same_file(report_path, input_path) or _same_file(report_path, output_path):
            raise OutputError(f"The report path must differ from the input and output files: {report_path}")


def write_atomically(path: Path, write: Callable[[TextIO], None]) -> None:
    """Write UTF-8 text via a temporary sibling file, then move it into place.

    A failure part-way through never leaves a truncated file at ``path``.
    """
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            write(handle)
        os.replace(temp_path, path)
    except OSError as exc:
        raise OutputError(f"Could not write {path}: {exc.strerror or exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
