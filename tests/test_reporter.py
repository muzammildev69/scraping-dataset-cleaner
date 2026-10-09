import io
import json

import pytest
from rich.console import Console

from dataset_cleaner.models import CleaningReport, InvalidValue, OutputError
from dataset_cleaner.reporter import render_terminal, report_to_json, write_json_report


def make_report(**overrides) -> CleaningReport:
    fields = dict(
        input_file="in.csv",
        output_file="out.csv",
        original_rows=1000,
        final_rows=920,
        original_columns=8,
        final_columns=7,
        empty_rows_removed=10,
        duplicate_rows_removed=70,
        invalid_emails=12,
        invalid_urls=5,
        columns_removed=["notes"],
    )
    fields.update(overrides)
    return CleaningReport(**fields)


def render(report: CleaningReport) -> str:
    buffer = io.StringIO()
    render_terminal(report, Console(file=buffer, width=200, color_system=None))
    return buffer.getvalue()


def test_json_report_contains_the_documented_summary_fields():
    data = json.loads(report_to_json(make_report()))
    assert data["input_file"] == "in.csv"
    assert data["output_file"] == "out.csv"
    assert (data["original_rows"], data["final_rows"]) == (1000, 920)
    assert (data["original_columns"], data["final_columns"]) == (8, 7)
    assert data["empty_rows_removed"] == 10 and data["duplicate_rows_removed"] == 70
    assert data["invalid_emails"] == 12 and data["invalid_urls"] == 5
    assert data["columns_removed"] == ["notes"]
    assert data["tool_version"]


def test_json_report_serialises_nested_objects_and_keeps_unicode():
    report = make_report(
        invalid_details=[InvalidValue(row=3, column="email", kind="email", value="josé@")],
        missing_values_by_column={"price": 2},
    )
    text = report_to_json(report)
    data = json.loads(text)
    assert data["invalid_details"] == [{"row": 3, "column": "email", "kind": "email", "value": "josé@"}]
    assert data["missing_values_by_column"] == {"price": 2}
    assert "josé@" in text


def test_write_json_report_creates_valid_json_and_no_temp_files(tmp_path):
    target = tmp_path / "report.json"
    write_json_report(make_report(), target)
    assert json.loads(target.read_text(encoding="utf-8"))["final_rows"] == 920
    assert target.read_text(encoding="utf-8").endswith("}\n")
    assert [p.name for p in tmp_path.iterdir()] == ["report.json"]


def test_write_json_report_replaces_an_existing_file(tmp_path):
    target = tmp_path / "report.json"
    target.write_text("stale", encoding="utf-8")
    write_json_report(make_report(final_rows=1), target)
    assert json.loads(target.read_text(encoding="utf-8"))["final_rows"] == 1


def test_write_json_report_to_missing_directory_raises_output_error(tmp_path):
    with pytest.raises(OutputError, match="Could not write"):
        write_json_report(make_report(), tmp_path / "missing" / "report.json")


def test_terminal_summary_shows_every_required_figure():
    text = render(make_report())
    for expected in (
        "Original rows", "1,000", "Final rows", "920",
        "Original columns", "Final columns",
        "Empty rows removed", "Duplicate rows removed", "70",
        "Invalid email values detected", "12",
        "Invalid URL values detected", "5",
        "Columns removed", "notes",
        "Output file", "out.csv",
    ):
        assert expected in text


def test_terminal_summary_says_none_when_no_columns_removed():
    assert "none" in render(make_report(columns_removed=[]))


def test_terminal_output_never_interprets_values_as_markup():
    report = make_report(
        warnings=["Column '[bold]x[/bold]' was ignored."],
        invalid_details=[InvalidValue(row=1, column="url", kind="url", value="[red]oops[/red]")],
    )
    text = render(report)
    assert "[bold]x[/bold]" in text and "[red]oops[/red]" in text


def test_terminal_output_lists_warnings_and_invalid_values():
    report = make_report(
        warnings=["something to know"],
        invalid_details=[InvalidValue(row=7, column="email", kind="email", value="bad@")],
    )
    text = render(report)
    assert "Warning: something to know" in text
    assert "Invalid values" in text and "bad@" in text and "7" in text


def test_terminal_output_limits_long_invalid_lists():
    details = [InvalidValue(row=i, column="email", kind="email", value=f"bad{i}") for i in range(1, 31)]
    text = render(make_report(invalid_details=details))
    assert "bad20" in text and "bad21" not in text
    assert "--report" in text
