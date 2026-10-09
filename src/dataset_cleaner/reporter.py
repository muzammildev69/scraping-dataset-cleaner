"""Rendering of cleaning reports as JSON and as a Rich terminal summary."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from dataset_cleaner.files import write_atomically
from dataset_cleaner.models import CleaningReport

TERMINAL_DETAIL_LIMIT = 20


def report_to_json(report: CleaningReport) -> str:
    """Serialise a report as indented, UTF-8 friendly JSON."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def write_json_report(report: CleaningReport, path: Path) -> None:
    """Write the JSON report atomically, so a failure never leaves partial JSON."""
    write_atomically(path, lambda handle: handle.write(report_to_json(report) + "\n"))


def _summary_table(report: CleaningReport) -> Table:
    table = Table(title="Cleaning summary", show_header=False, title_justify="left")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    rows = [
        ("Input file", report.input_file),
        ("Output file", report.output_file),
        ("Original rows", f"{report.original_rows:,}"),
        ("Final rows", f"{report.final_rows:,}"),
        ("Original columns", str(report.original_columns)),
        ("Final columns", str(report.final_columns)),
        ("Empty rows removed", f"{report.empty_rows_removed:,}"),
        ("Duplicate rows removed", f"{report.duplicate_rows_removed:,}"),
        ("Rows removed for invalid values", f"{report.invalid_rows_removed:,}"),
        ("Invalid email values detected", f"{report.invalid_emails:,}"),
        ("Invalid URL values detected", f"{report.invalid_urls:,}"),
        ("Missing values remaining", f"{report.missing_values:,}"),
        ("Columns removed", ", ".join(report.columns_removed) or "none"),
    ]
    for label, value in rows:
        table.add_row(label, Text(value))
    return table


def _details_table(report: CleaningReport) -> Table:
    table = Table(title="Invalid values", title_justify="left")
    for heading in ("Row", "Column", "Type", "Value"):
        table.add_column(heading)
    for item in report.invalid_details[:TERMINAL_DETAIL_LIMIT]:
        table.add_row(str(item.row), Text(item.column), item.kind, Text(item.value))
    return table


def render_terminal(report: CleaningReport, console: Console) -> None:
    """Print a human-readable summary. Values are never parsed as Rich markup."""
    console.print(_summary_table(report))
    for warning in report.warnings:
        console.print(Text(f"Warning: {warning}", style="yellow"))
    if report.invalid_details:
        console.print(_details_table(report))
        hidden = len(report.invalid_details) - TERMINAL_DETAIL_LIMIT
        if hidden > 0 or report.invalid_details_truncated:
            console.print(Text("More invalid values are listed in the JSON report (--report).", style="dim"))
