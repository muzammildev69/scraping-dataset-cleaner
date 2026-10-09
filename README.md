# Scraping Dataset Cleaner

[![tests](https://github.com/OWNER/scraping-dataset-cleaner/actions/workflows/tests.yml/badge.svg)](https://github.com/OWNER/scraping-dataset-cleaner/actions/workflows/tests.yml)

A small command-line tool that tidies CSV files produced by web scrapers. It trims
whitespace, normalises column names, removes empty and duplicate rows, normalises
emails and URLs, flags invalid values, and tells you exactly what changed.

```bash
dataset-cleaner input.csv --output cleaned.csv
```

It is a conventional data-cleaning utility: no network access, no AI, no services.
It is built on Python, [pandas](https://pandas.pydata.org/),
[Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

> Replace `OWNER` in the badge URL above with your GitHub user or organisation.

## Features

- Normalises column names (`" First Name "` -> `first_name`, `"PRICE ($)"` -> `price`) and
  never overwrites columns whose names collide.
- Trims leading and trailing whitespace in every cell.
- Removes rows that are completely empty (or whitespace only); never removes a row just
  because one field is missing.
- Removes exact duplicate rows, or duplicates by chosen columns.
- Lowercases and trims emails; lowercases the scheme and host of URLs while preserving
  paths, query strings and fragments.
- Validates email and URL **syntax**, reports how many values are invalid, and keeps those
  rows unless you explicitly ask to remove them.
- Drops unwanted columns and reports any you asked for that do not exist.
- Writes a Rich terminal summary, JSON to stdout (`--json`), and/or a JSON file (`--report`).
- Refuses to overwrite the input file and reports unreadable, empty, malformed or
  non-UTF-8 input with a clear message.

## Installation

Requires Python 3.11 or newer.

```bash
git clone https://github.com/OWNER/scraping-dataset-cleaner.git
cd scraping-dataset-cleaner
python -m pip install -e ".[dev]"
dataset-cleaner --help
```

For use without the test dependencies, `python -m pip install .` is enough.

## Quick start

```bash
# Clean a file
dataset-cleaner input.csv --output cleaned.csv

# Also list every invalid email/URL, and save a JSON report
dataset-cleaner input.csv --output cleaned.csv --validate --report report.json

# Remove duplicates by email only, and drop two columns
dataset-cleaner input.csv --output cleaned.csv --deduplicate-by email --drop-columns notes,temp_field

# Machine-readable summary on stdout (errors still go to stderr)
dataset-cleaner input.csv --output cleaned.csv --json
```

## Example input and output

`examples/messy_dataset.csv`:

```csv
 First Name ,Email Address,Product-URL,PRICE ($),Notes
  John Smith  , John@Example.COM ,  https://Example.com/Shop?id=1#top ,19.99,scraped on monday
John Smith,john@example.com,https://example.com/Shop?id=1#top,19.99,duplicate of row above
,,,,
   ,   ,   ,   ,
Jane Doe,jane.doe@example,not a url,  7.50 ,bad email and url
Ana Pérez,ANA@EXAMPLE.ORG,HTTP://WWW.Example.org/Ana,,missing price
Bob Stone,,https://example.net/bob,12,no email
```

```bash
dataset-cleaner examples/messy_dataset.csv --output cleaned.csv --drop-columns notes
```

`cleaned.csv` (identical to `examples/expected_cleaned.csv`):

```csv
first_name,email_address,product_url,price
John Smith,john@example.com,https://example.com/Shop?id=1#top,19.99
Jane Doe,jane.doe@example,not a url,7.50
Ana Pérez,ana@example.org,http://www.example.org/Ana,
Bob Stone,,https://example.net/bob,12
```

Seven data rows became four: two blank rows were removed, and the first two John Smith
rows became duplicates once the `notes` column was dropped. Jane Doe's invalid email and
URL are **reported but kept**. The summary lists the counts (7 -> 4 rows, 5 -> 4 columns,
2 empty rows, 1 duplicate, 1 invalid email, 1 invalid URL, `notes` removed).

## CLI options

```text
dataset-cleaner INPUT_FILE --output OUTPUT_FILE [options]
```

| Option | Description |
| --- | --- |
| `INPUT_FILE` | CSV file to clean (UTF-8, with or without BOM). Must end in `.csv`. |
| `-o`, `--output PATH` | **Required.** Cleaned CSV destination. Must end in `.csv`; an existing output file is replaced, the input never is. |
| `--deduplicate-by COLS` | Comma-separated columns that define a duplicate. Default: the whole row. |
| `--keep-duplicates` | Do not remove duplicates. Cannot be combined with `--deduplicate-by`. |
| `--drop-columns COLS` | Comma-separated columns to remove. Unknown names are reported and ignored. |
| `--add-missing-scheme` | Prefix URLs that lack a scheme with `https://`. |
| `--strip-url-params` | Remove the query string and fragment from URLs. |
| `--validate` | List every invalid email/URL (data row, column, value) in the report. |
| `--remove-invalid-emails` | Remove rows with a non-empty, syntactically invalid email. |
| `--remove-invalid-urls` | Remove rows with a non-empty, syntactically invalid URL. |
| `--email-columns COLS` | Treat exactly these columns as emails (replaces automatic detection). |
| `--url-columns COLS` | Treat exactly these columns as URLs (replaces automatic detection). |
| `--report PATH` | Also write the summary to a JSON file. |
| `--json` | Print the summary as JSON on stdout instead of the Rich report. |
| `--version` | Show the version and exit. |
| `-h`, `--help` | Show help. |

Column names you pass to any option are normalised like the dataset's own, so
`--drop-columns "Notes, Temp Field"` and `--drop-columns notes,temp_field` are the same.
Errors are printed to **stderr** and exit with status 1 (usage errors exit with 2).

## Cleaning rules

Steps run in this order:

1. **Read** the file as text. Every value stays a string exactly as written, so `007`,
   `1.50` and the words `NaN` or `None` are never converted. Rows shorter than the header
   are padded with empty values; rows longer than the header are rejected as malformed.
2. **Normalise column names**: trim, lowercase, replace every run of non-alphanumeric
   characters with `_`, strip leading/trailing `_`. Unnameable columns become
   `column_<position>`. If two names collide, later ones get `_2`, `_3`, ... and a
   warning is added to the report.
3. **Trim whitespace** around every cell (inner spacing is untouched).
4. **Remove empty rows** — rows where every cell is empty after trimming, judged on the
   original columns (before `--drop-columns`).
5. **Drop columns** from `--drop-columns`.
6. **Normalise emails** in email columns: trim and lowercase the whole address.
   Email columns are detected by name: `email`, `email_address`, `e_mail`, or anything ending
   in `_email` / `_email_address` (such as `contact_email`, `business_email`).
7. **Normalise URLs** in URL columns: trim, lowercase the scheme and host. Paths, query
   strings, fragments, userinfo and ports are preserved. URL columns are detected by name:
   `url`, `website`, `link`, `homepage`, or anything ending in `_url` / `_website` / `_link`
   (such as `product_url`, `linkedin_url`). `--add-missing-scheme` and `--strip-url-params`
   are opt-in.
8. **Validate** email and URL values and count the invalid ones. Empty values are *missing*,
   not invalid. Rows are only removed with `--remove-invalid-emails` / `--remove-invalid-urls`.
9. **Remove duplicates**, keeping the first occurrence. Duplicates are judged on the cleaned,
   post-drop data. With `--deduplicate-by`, rows whose key columns are all empty are never
   treated as duplicates of each other.
10. **Count missing values** (empty or whitespace-only cells) in the final data. Missing values
    are never replaced with `"None"` or `"NaN"`.

Output is written as UTF-8 without a BOM, with `\n` line endings, via a temporary file that
replaces the target only after a successful write.

## Validation limitations

- **Email validation checks syntax only.** It does not verify that a mailbox or domain
  exists or can receive mail. It accepts a single `@`, an ASCII local part (no quoted or
  internationalised local parts) and a domain with at least two labels and an alphabetic
  top-level domain.
- **URL validation does not guarantee the website is online** or that the page exists.
  Only `http` and `https` URLs are valid; a host must be a domain with a dot, `localhost`,
  or an IP address; whitespace anywhere in the value is invalid. Other schemes (`ftp:`,
  `mailto:`, ...) are reported as invalid.
- Lowercasing the whole email address is the common convention, but the local part is
  technically case-sensitive. Use `--email-columns` to restrict which columns are touched.
- Column detection is name-based. Use `--email-columns` / `--url-columns` when your names
  are unusual.

## JSON reporting

`--json` prints the report to stdout; `--report report.json` writes the same document to a
file (atomically). Example:

```json
{
  "tool_version": "0.1.0",
  "input_file": "examples/messy_dataset.csv",
  "output_file": "cleaned.csv",
  "original_rows": 7,
  "final_rows": 4,
  "original_columns": 5,
  "final_columns": 4,
  "empty_rows_removed": 2,
  "duplicate_rows_removed": 1,
  "invalid_rows_removed": 0,
  "invalid_emails": 1,
  "invalid_urls": 1,
  "cells_trimmed": 9,
  "emails_normalized": 2,
  "urls_normalized": 2,
  "missing_values": 2,
  "missing_values_by_column": {"email_address": 1, "price": 1},
  "columns_removed": ["notes"],
  "columns_not_found": [],
  "column_renames": [{"original": " First Name ", "cleaned": "first_name"}],
  "email_columns": ["email_address"],
  "url_columns": ["product_url"],
  "invalid_details": [],
  "invalid_details_truncated": false,
  "warnings": []
}
```

| Field | Meaning |
| --- | --- |
| `original_rows`, `final_rows` | Data rows before and after cleaning (header excluded; blank lines count as rows). |
| `original_columns`, `final_columns` | Columns before and after `--drop-columns`. |
| `empty_rows_removed`, `duplicate_rows_removed` | Rows removed by those steps. |
| `invalid_rows_removed` | Rows removed by `--remove-invalid-emails` / `--remove-invalid-urls` (each row counted once). |
| `invalid_emails`, `invalid_urls` | Invalid **cells** found (after empty-row removal and column dropping, before invalid-row and duplicate removal). |
| `cells_trimmed` | Cells changed by whitespace trimming. |
| `emails_normalized`, `urls_normalized` | Cells changed by email/URL normalisation (beyond trimming). |
| `missing_values`, `missing_values_by_column` | Empty or whitespace-only cells remaining in the output. |
| `columns_removed`, `columns_not_found` | Dropped columns (cleaned names) and requested names that did not exist. |
| `column_renames` | Columns whose name changed, as `{original, cleaned}` pairs. |
| `email_columns`, `url_columns` | Columns that were normalised and validated. |
| `invalid_details` | With `--validate`: `{row, column, kind, value}` per invalid cell, where `row` is the 1-based data row in the input file (header excluded). Capped at 1,000 entries; `invalid_details_truncated` tells you if the cap was hit. Empty without `--validate`. |
| `warnings` | Human-readable notes (column collisions, ignored `--drop-columns` names, large-file notice). |

## Project structure

```text
scraping-dataset-cleaner/
├── src/
│   └── dataset_cleaner/
│       ├── __init__.py      # version
│       ├── cli.py           # Typer command and option parsing
│       ├── cleaner.py       # reading, cleaning pipeline, writing
│       ├── files.py         # path safety checks and atomic writes
│       ├── validators.py    # email/URL validation and normalisation
│       ├── models.py        # options, report and exception types
│       └── reporter.py      # JSON and Rich terminal reports
├── tests/                   # pytest suite (no network access needed)
├── examples/
│   ├── messy_dataset.csv
│   └── expected_cleaned.csv
├── .github/workflows/tests.yml
├── CHANGELOG.md
├── LICENSE
├── README.md
└── pyproject.toml
```

## Running tests

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a branch.
2. Install with `python -m pip install -e ".[dev]"`.
3. Add or update tests for any behaviour change — assert real results, not just that a
   function exists.
4. Run `python -m pytest` and make sure it passes.
5. Update `README.md` and `CHANGELOG.md` when behaviour or options change, then open a pull request.

Please keep dependencies minimal and the tool offline: no network calls in the code or tests.

## Limitations

- The whole file is loaded into memory (pandas typically needs several times the file size).
  A warning is added to the report for inputs over 100 MB. There is no chunked mode, so
  very large files may not fit on small machines.
- Only UTF-8 and UTF-8 with BOM are supported. Other encodings are rejected with an error
  rather than guessed.
- Only `.csv` files with comma separators are supported.
- Validation is syntactic only (see above). The tool cannot guarantee perfect data quality;
  always review the report and spot-check the output.
- Short rows are padded with empty values rather than rejected.
- Whitespace inside values is not collapsed and text is not re-cased, to preserve your data.

## Roadmap

- Chunked processing for very large files.
- Other delimiters (TSV, semicolon) and input encodings.
- Optional text normalisation (collapse inner whitespace, case rules).
- Phone-number and price-field normalisation.
- Configuration file support.

## License

Released under the [MIT License](LICENSE).
