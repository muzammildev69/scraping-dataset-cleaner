"""The cleaning pipeline: read a scraped CSV, tidy it, write it back."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

import pandas as pd

from dataset_cleaner import validators
from dataset_cleaner.files import validate_paths, write_atomically
from dataset_cleaner.models import (
    CleaningOptions,
    CleaningReport,
    ColumnRename,
    InputError,
    InvalidValue,
    OptionError,
)

LARGE_FILE_WARNING_BYTES = 100 * 1024 * 1024
MAX_INVALID_DETAILS = 1000

_NON_ALPHANUMERIC = re.compile(r"[\W_]+")


# --- column names -----------------------------------------------------------


def normalize_column_name(name: str) -> str:
    """Lowercase a column name and join its alphanumeric runs with underscores.

    ``" First Name "`` -> ``"first_name"``, ``"PRICE ($)"`` -> ``"price"``.
    """
    return _NON_ALPHANUMERIC.sub("_", name.strip().lower()).strip("_")


def _base_name(raw_name: str, position: int) -> str:
    return normalize_column_name(raw_name) or f"column_{position}"


def normalize_column_names(names: Sequence[str]) -> list[str]:
    """Normalise names and make them unique by suffixing ``_2``, ``_3``, ...

    No column is ever dropped or overwritten because two names collide.
    """
    used: set[str] = set()
    result: list[str] = []
    for position, raw_name in enumerate(names, start=1):
        base = _base_name(raw_name, position)
        candidate, suffix = base, 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


def _collision_warnings(header: Sequence[str], columns: Sequence[str]) -> list[str]:
    return [
        f"Column {raw!r} (position {position}) normalised to the same name as an earlier "
        f"column and was renamed {cleaned!r} so no data is overwritten."
        for position, (raw, cleaned) in enumerate(zip(header, columns), start=1)
        if cleaned != _base_name(raw, position)
    ]


def _resolve_columns(requested: Sequence[str], columns: Sequence[str], option: str) -> list[str]:
    """Map user-supplied column names onto existing normalised names or fail."""
    normalized = [normalize_column_name(name) for name in requested]
    missing = [name for name, norm in zip(requested, normalized) if norm not in columns]
    if missing:
        raise OptionError(
            f"{option}: column(s) not found: {', '.join(missing)}. "
            f"Available columns: {', '.join(columns)}"
        )
    return list(dict.fromkeys(normalized))


# --- reading and writing ----------------------------------------------------


def read_csv(path: Path) -> tuple[list[str], pd.DataFrame]:
    """Read a UTF-8 (optionally BOM-prefixed) CSV as text, returning header and rows.

    Every value stays a string exactly as written, so ``007`` and ``1.50`` are
    never reinterpreted as numbers and ``NaN`` or ``None`` are not treated as
    missing. Short rows are padded with empty values; rows with more fields
    than the header are rejected as malformed.
    """
    try:
        raw = pd.read_csv(
            path,
            header=None,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8-sig",
            skip_blank_lines=False,
        )
    except pd.errors.EmptyDataError as exc:
        raise InputError(f"The input file is empty: {path}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(
            f"Could not decode {path} as UTF-8 ({exc.reason} at byte {exc.start}). "
            "Re-save the file as UTF-8 and try again."
        ) from exc
    except pd.errors.ParserError as exc:
        raise InputError(f"Malformed CSV in {path}: {exc}") from exc
    except OSError as exc:
        raise InputError(f"Could not read {path}: {exc.strerror or exc}") from exc

    raw = raw.fillna("")
    if raw.empty or all((raw[column].str.strip() == "").all() for column in raw.columns):
        raise InputError(f"The input file contains no data: {path}")
    header = [str(cell) for cell in raw.iloc[0]]
    data = raw.iloc[1:].reset_index(drop=True)
    return header, data


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write UTF-8 CSV (no BOM, ``\\n`` line endings) without an index column."""
    write_atomically(path, lambda handle: frame.to_csv(handle, index=False, lineterminator="\n"))


# --- individual cleaning steps ----------------------------------------------


def _trim_whitespace(frame: pd.DataFrame) -> int:
    """Strip every cell in place and return how many cells changed."""
    changed = 0
    if frame.empty:
        return changed
    for column in frame.columns:
        stripped = frame[column].str.strip()
        changed += int((stripped != frame[column]).sum())
        frame[column] = stripped
    return changed


def _remove_empty_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    blank = (frame == "").all(axis=1)
    return frame.loc[~blank].copy(), int(blank.sum())


def _drop_columns(
    frame: pd.DataFrame, requested: Sequence[str]
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Drop requested columns; return the frame, columns removed and names not found."""
    normalized = [normalize_column_name(name) for name in requested]
    removed = [name for name in dict.fromkeys(normalized) if name in frame.columns]
    not_found = [name for name, norm in zip(requested, normalized) if norm not in frame.columns]
    if removed and len(removed) == len(frame.columns):
        raise OptionError("--drop-columns would remove every column; nothing would be left to write.")
    return frame.drop(columns=removed), removed, not_found


def _select_columns(
    frame: pd.DataFrame,
    explicit: Sequence[str],
    detector: Callable[[str], bool],
    option: str,
) -> list[str]:
    if explicit:
        return _resolve_columns(explicit, list(frame.columns), option)
    return [column for column in frame.columns if detector(column)]


def _normalize_column(frame: pd.DataFrame, column: str, function: Callable[[str], str]) -> int:
    """Apply ``function`` to a column in place and return the number of changed cells."""
    updated = frame[column].map(function)
    changed = int((updated != frame[column]).sum())
    frame[column] = updated
    return changed


def _invalid_mask(
    frame: pd.DataFrame, columns: Sequence[str], is_valid: Callable[[str], bool]
) -> pd.DataFrame:
    """Boolean frame: True where a non-empty value fails validation."""
    return pd.DataFrame(
        {
            column: frame[column].map(lambda value: value != "" and not is_valid(value)).astype(bool)
            for column in columns
        },
        index=frame.index,
    )


def _collect_details(
    frame: pd.DataFrame, masks: dict[str, pd.DataFrame]
) -> tuple[list[InvalidValue], bool]:
    """List invalid cells by 1-based data row (header excluded), capped for report size."""
    details = [
        InvalidValue(row=int(index) + 1, column=column, kind=kind, value=frame.at[index, column])
        for kind, mask in masks.items()
        for column in mask.columns
        for index in mask.index[mask[column]]
    ]
    details.sort(key=lambda item: (item.row, item.column))
    return details[:MAX_INVALID_DETAILS], len(details) > MAX_INVALID_DETAILS


def _remove_duplicates(frame: pd.DataFrame, subset: Sequence[str]) -> tuple[pd.DataFrame, int]:
    """Keep the first occurrence of each duplicate.

    With a ``subset``, rows whose key values are all empty are never treated as
    duplicates of each other, because a missing key says nothing about identity.
    """
    if subset:
        key = list(subset)
        has_key = ~(frame[key] == "").all(axis=1)
        duplicated = frame.duplicated(subset=key, keep="first") & has_key
    else:
        duplicated = frame.duplicated(keep="first")
    return frame.loc[~duplicated], int(duplicated.sum())


def validate_options(options: CleaningOptions) -> None:
    """Reject contradictory option combinations."""
    if options.deduplicate_by and not options.deduplicate:
        raise OptionError("--deduplicate-by cannot be combined with --keep-duplicates.")


# --- public pipeline --------------------------------------------------------


def clean_dataframe(
    header: Sequence[str], data: pd.DataFrame, options: CleaningOptions
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean already-loaded text data and describe exactly what changed.

    Order of operations: normalise column names, trim cells, remove empty rows
    (judged on the original columns), drop requested columns, normalise emails
    and URLs, count invalid values (optionally removing their rows), remove
    duplicates, and finally count remaining missing values.
    """
    validate_options(options)
    report = CleaningReport(original_rows=len(data), original_columns=len(header))

    frame = data.copy()
    columns = normalize_column_names(header)
    frame.columns = columns
    report.column_renames = [
        ColumnRename(original, cleaned) for original, cleaned in zip(header, columns) if original != cleaned
    ]
    report.warnings.extend(_collision_warnings(header, columns))

    report.cells_trimmed = _trim_whitespace(frame)
    frame, report.empty_rows_removed = _remove_empty_rows(frame)
    frame, report.columns_removed, report.columns_not_found = _drop_columns(frame, options.drop_columns)
    report.warnings.extend(
        f"Column {name!r} given to --drop-columns was not found and was ignored."
        for name in report.columns_not_found
    )

    email_columns = _select_columns(frame, options.email_columns, validators.is_email_column, "--email-columns")
    url_columns = _select_columns(frame, options.url_columns, validators.is_url_column, "--url-columns")
    report.email_columns, report.url_columns = email_columns, url_columns
    report.emails_normalized = sum(
        _normalize_column(frame, column, validators.normalize_email) for column in email_columns
    )
    normalize_url = partial(
        validators.normalize_url,
        add_scheme=options.add_missing_scheme,
        strip_params=options.strip_url_params,
    )
    report.urls_normalized = sum(_normalize_column(frame, column, normalize_url) for column in url_columns)

    email_mask = _invalid_mask(frame, email_columns, validators.is_valid_email)
    url_mask = _invalid_mask(frame, url_columns, validators.is_valid_url)
    report.invalid_emails = int(email_mask.to_numpy().sum())
    report.invalid_urls = int(url_mask.to_numpy().sum())
    if options.validate:
        report.invalid_details, report.invalid_details_truncated = _collect_details(
            frame, {"email": email_mask, "url": url_mask}
        )

    remove = pd.Series(False, index=frame.index)
    if options.remove_invalid_emails:
        remove |= email_mask.any(axis=1)
    if options.remove_invalid_urls:
        remove |= url_mask.any(axis=1)
    report.invalid_rows_removed = int(remove.sum())
    frame = frame.loc[~remove]

    if options.deduplicate:
        subset = _resolve_columns(options.deduplicate_by, list(frame.columns), "--deduplicate-by")
        frame, report.duplicate_rows_removed = _remove_duplicates(frame, subset)

    report.missing_values_by_column = {
        column: count for column in frame.columns if (count := int((frame[column] == "").sum()))
    }
    report.missing_values = sum(report.missing_values_by_column.values())
    report.final_rows, report.final_columns = frame.shape
    return frame, report


def clean_file(
    input_path: Path,
    output_path: Path,
    options: CleaningOptions | None = None,
    report_path: Path | None = None,
) -> CleaningReport:
    """Clean ``input_path`` into ``output_path`` and return the report.

    ``report_path`` is only validated here (so a bad report path fails before any
    output is written); writing the report is the caller's job.
    """
    options = options or CleaningOptions()
    validate_options(options)
    validate_paths(input_path, output_path, report_path)

    size = input_path.stat().st_size
    header, data = read_csv(input_path)
    frame, report = clean_dataframe(header, data, options)
    if size > LARGE_FILE_WARNING_BYTES:
        report.warnings.insert(
            0,
            f"The input is {size / 1024 / 1024:.0f} MB. The whole file is loaded into memory, "
            "which typically needs several times the file size in RAM.",
        )
    write_csv(frame, output_path)
    report.input_file, report.output_file = str(input_path), str(output_path)
    return report
