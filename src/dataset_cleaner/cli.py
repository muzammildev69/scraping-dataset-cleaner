"""Command-line interface for dataset-cleaner."""

from pathlib import Path
from typing import Annotated, NoReturn, Optional

import typer
from rich.console import Console
from rich.text import Text

from dataset_cleaner import __version__
from dataset_cleaner.cleaner import clean_file
from dataset_cleaner.models import CleaningOptions, DatasetCleanerError
from dataset_cleaner.reporter import render_terminal, report_to_json, write_json_report

app = typer.Typer(
    name="dataset-cleaner",
    help=(
        "Clean a CSV dataset collected through web scraping and write the result to OUTPUT. "
        "Example: dataset-cleaner input.csv --output cleaned.csv"
    ),
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

CLEANING = "Cleaning options"
VALIDATION = "Validation options"
REPORTING = "Reporting options"


def _split_names(value: Optional[str]) -> tuple[str, ...]:
    """Split a comma-separated option value into non-empty, trimmed names."""
    if not value:
        return ()
    return tuple(name.strip() for name in value.split(",") if name.strip())


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"dataset-cleaner {__version__}")
        raise typer.Exit()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


@app.command()
def main(
    input_file: Annotated[
        Path, typer.Argument(metavar="INPUT_FILE", help="CSV file to clean (UTF-8, with or without BOM).")
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the cleaned CSV. An existing file is replaced; the input never is.",
            rich_help_panel=REPORTING,
        ),
    ],
    deduplicate_by: Annotated[
        Optional[str],
        typer.Option(
            "--deduplicate-by",
            help="Comma-separated columns that define a duplicate (default: the whole row).",
            rich_help_panel=CLEANING,
        ),
    ] = None,
    keep_duplicates: Annotated[
        bool,
        typer.Option("--keep-duplicates", help="Do not remove duplicate rows.", rich_help_panel=CLEANING),
    ] = False,
    drop_columns: Annotated[
        Optional[str],
        typer.Option(
            "--drop-columns",
            help="Comma-separated columns to remove, e.g. notes,temp_field.",
            rich_help_panel=CLEANING,
        ),
    ] = None,
    add_missing_scheme: Annotated[
        bool,
        typer.Option(
            "--add-missing-scheme",
            help="Prefix URLs that have no scheme with https://.",
            rich_help_panel=CLEANING,
        ),
    ] = False,
    strip_url_params: Annotated[
        bool,
        typer.Option(
            "--strip-url-params",
            help="Remove the query string and fragment from URLs.",
            rich_help_panel=CLEANING,
        ),
    ] = False,
    validate: Annotated[
        bool,
        typer.Option(
            "--validate",
            help="List every invalid email/URL value (row, column, value) in the report.",
            rich_help_panel=VALIDATION,
        ),
    ] = False,
    remove_invalid_emails: Annotated[
        bool,
        typer.Option(
            "--remove-invalid-emails",
            help="Remove rows containing a non-empty, syntactically invalid email.",
            rich_help_panel=VALIDATION,
        ),
    ] = False,
    remove_invalid_urls: Annotated[
        bool,
        typer.Option(
            "--remove-invalid-urls",
            help="Remove rows containing a non-empty, syntactically invalid URL.",
            rich_help_panel=VALIDATION,
        ),
    ] = False,
    email_columns: Annotated[
        Optional[str],
        typer.Option(
            "--email-columns",
            help="Comma-separated email columns (overrides automatic detection).",
            rich_help_panel=VALIDATION,
        ),
    ] = None,
    url_columns: Annotated[
        Optional[str],
        typer.Option(
            "--url-columns",
            help="Comma-separated URL columns (overrides automatic detection).",
            rich_help_panel=VALIDATION,
        ),
    ] = None,
    report: Annotated[
        Optional[Path],
        typer.Option("--report", help="Also write the summary to this JSON file.", rich_help_panel=REPORTING),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print the summary as JSON on stdout instead of a formatted report.",
            rich_help_panel=REPORTING,
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show the version and exit."),
    ] = False,
) -> None:
    """Clean INPUT_FILE and write the cleaned dataset to --output."""
    options = CleaningOptions(
        deduplicate=not keep_duplicates,
        deduplicate_by=_split_names(deduplicate_by),
        drop_columns=_split_names(drop_columns),
        email_columns=_split_names(email_columns),
        url_columns=_split_names(url_columns),
        add_missing_scheme=add_missing_scheme,
        strip_url_params=strip_url_params,
        remove_invalid_emails=remove_invalid_emails,
        remove_invalid_urls=remove_invalid_urls,
        validate=validate,
    )
    try:
        cleaning_report = clean_file(input_file, output, options, report_path=report)
        if report is not None:
            write_json_report(cleaning_report, report)
    except DatasetCleanerError as exc:
        _fail(str(exc))

    if json_output:
        typer.echo(report_to_json(cleaning_report))
        return
    console = Console()
    render_terminal(cleaning_report, console)
    if report is not None:
        console.print(Text(f"JSON report written to {report}"))
