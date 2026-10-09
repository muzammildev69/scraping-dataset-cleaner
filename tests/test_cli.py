import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dataset_cleaner import __version__
from dataset_cleaner.cli import app

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
MESSY = EXAMPLES_DIR / "messy_dataset.csv"
EXPECTED = EXAMPLES_DIR / "expected_cleaned.csv"


@pytest.fixture
def runner() -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # click < 8.2
    except TypeError:
        return CliRunner()  # click >= 8.2 always separates stderr


def invoke(runner, *args):
    return runner.invoke(app, [str(arg) for arg in args])


def test_help_lists_every_option(runner):
    result = invoke(runner, "--help")
    assert result.exit_code == 0
    for option in (
        "--output", "--validate", "--deduplicate-by", "--keep-duplicates", "--drop-columns",
        "--report", "--json", "--remove-invalid-emails", "--remove-invalid-urls",
        "--email-columns", "--url-columns", "--add-missing-scheme", "--strip-url-params",
    ):
        assert option in result.stdout


def test_running_without_arguments_shows_usage(runner):
    assert "Usage" in invoke(runner).output


def test_version_option(runner):
    result = invoke(runner, "--version")
    assert result.exit_code == 0
    assert f"dataset-cleaner {__version__}" in result.stdout


def test_basic_run_writes_cleaned_csv_and_prints_summary(runner, tmp_path):
    output = tmp_path / "cleaned.csv"
    result = invoke(runner, MESSY, "--output", output, "--drop-columns", "notes")
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == EXPECTED.read_text(encoding="utf-8")
    assert "Cleaning summary" in result.stdout
    assert "Duplicate rows removed" in result.stdout
    assert str(output) in result.stdout.replace("\n", "")


def test_json_flag_prints_machine_readable_summary_only(runner, tmp_path):
    output = tmp_path / "cleaned.csv"
    result = invoke(runner, MESSY, "-o", output, "--drop-columns", "notes", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert (data["original_rows"], data["final_rows"]) == (7, 4)
    assert (data["original_columns"], data["final_columns"]) == (5, 4)
    assert data["empty_rows_removed"] == 2 and data["duplicate_rows_removed"] == 1
    assert data["invalid_emails"] == 1 and data["invalid_urls"] == 1
    assert data["columns_removed"] == ["notes"]
    assert data["output_file"] == str(output)
    assert "Cleaning summary" not in result.stdout


def test_report_option_writes_json_file(runner, tmp_path):
    output, report = tmp_path / "cleaned.csv", tmp_path / "report.json"
    result = invoke(runner, MESSY, "-o", output, "--drop-columns", "notes", "--report", report)
    assert result.exit_code == 0, result.output
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["input_file"] == str(MESSY) and data["final_rows"] == 4
    assert "JSON report written" in result.stdout


def test_json_and_report_contain_the_same_data(runner, tmp_path):
    output, report = tmp_path / "cleaned.csv", tmp_path / "report.json"
    result = invoke(runner, MESSY, "-o", output, "--report", report, "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == json.loads(report.read_text(encoding="utf-8"))


def test_validate_adds_invalid_values_to_the_report(runner, tmp_path):
    output = tmp_path / "cleaned.csv"
    result = invoke(runner, MESSY, "-o", output, "--validate", "--json")
    details = json.loads(result.stdout)["invalid_details"]
    assert [(d["row"], d["column"], d["value"]) for d in details] == [
        (5, "email_address", "jane.doe@example"),
        (5, "product_url", "not a url"),
    ]
    assert invoke(runner, MESSY, "-o", output, "--validate").stdout.count("jane.doe@example") == 1


def test_invalid_rows_are_kept_unless_removal_is_requested(runner, tmp_path):
    output = tmp_path / "cleaned.csv"
    kept = json.loads(invoke(runner, MESSY, "-o", output, "--drop-columns", "notes", "--json").stdout)
    removed = json.loads(
        invoke(runner, MESSY, "-o", output, "--drop-columns", "notes", "--json", "--remove-invalid-emails").stdout
    )
    assert kept["invalid_rows_removed"] == 0 and kept["final_rows"] == 4
    assert removed["invalid_rows_removed"] == 1 and removed["final_rows"] == 3
    assert "jane.doe@example" not in output.read_text(encoding="utf-8")


def test_deduplicate_by_option(runner, write_text, tmp_path):
    source = write_text("in.csv", "name,email\nA,x@y.co\nB,x@y.co\nC,z@y.co\n")
    output = tmp_path / "out.csv"
    result = invoke(runner, source, "-o", output, "--deduplicate-by", "email", "--json")
    assert json.loads(result.stdout)["duplicate_rows_removed"] == 1
    assert output.read_text(encoding="utf-8") == "name,email\nA,x@y.co\nC,z@y.co\n"


def test_keep_duplicates_option(runner, write_text, tmp_path):
    source = write_text("in.csv", "a\nx\nx\n")
    output = tmp_path / "out.csv"
    assert invoke(runner, source, "-o", output, "--keep-duplicates").exit_code == 0
    assert output.read_text(encoding="utf-8") == "a\nx\nx\n"


def test_drop_columns_accepts_spaces_around_commas(runner, write_text, tmp_path):
    source = write_text("in.csv", "id,Notes,Temp Field\n1,a,b\n")
    output = tmp_path / "out.csv"
    result = invoke(runner, source, "-o", output, "--drop-columns", "notes, temp field")
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == "id\n1\n"


def test_unknown_drop_column_is_reported_but_not_fatal(runner, write_text, tmp_path):
    source = write_text("in.csv", "id,notes\n1,a\n")
    output = tmp_path / "out.csv"
    result = invoke(runner, source, "-o", output, "--drop-columns", "notes,ghost", "--json")
    assert result.exit_code == 0 and result.stderr == ""
    data = json.loads(result.stdout)
    assert data["columns_not_found"] == ["ghost"]
    assert any("ghost" in warning for warning in data["warnings"])
    assert "Warning" in invoke(runner, source, "-o", output, "--drop-columns", "ghost").stdout


def test_missing_input_goes_to_stderr(runner, tmp_path):
    result = invoke(runner, tmp_path / "nope.csv", "-o", tmp_path / "out.csv", "--json")
    assert result.exit_code == 1
    assert "Input file not found" in result.stderr
    assert result.stdout == ""


def test_output_option_is_required(runner):
    result = invoke(runner, MESSY)
    assert result.exit_code == 2
    assert "--output" in result.output


def test_same_input_and_output_is_refused(runner, write_text):
    source = write_text("in.csv", "a\n 1 \n")
    result = invoke(runner, source, "-o", source)
    assert result.exit_code == 1
    assert "overwrite the input" in result.stderr
    assert source.read_text(encoding="utf-8") == "a\n 1 \n"


def test_unsupported_extension_message(runner, write_text, tmp_path):
    result = invoke(runner, write_text("data.txt", "a\n1\n"), "-o", tmp_path / "out.csv")
    assert result.exit_code == 1 and "Unsupported input file type" in result.stderr


def test_empty_input_message(runner, write_text, tmp_path):
    result = invoke(runner, write_text("empty.csv", ""), "-o", tmp_path / "out.csv")
    assert result.exit_code == 1 and "empty" in result.stderr


def test_malformed_csv_message(runner, write_text, tmp_path):
    result = invoke(runner, write_text("bad.csv", "a,b\n1,2,3\n"), "-o", tmp_path / "out.csv")
    assert result.exit_code == 1 and "Malformed CSV" in result.stderr


def test_invalid_encoding_message_and_no_output(runner, write_text, tmp_path):
    source = write_text("latin1.csv", "name\ncaf\u00e9\n".encode("latin-1"))
    output = tmp_path / "out.csv"
    result = invoke(runner, source, "-o", output)
    assert result.exit_code == 1 and "UTF-8" in result.stderr
    assert not output.exists()


def test_missing_output_directory_message(runner, write_text, tmp_path):
    result = invoke(runner, write_text("in.csv", "a\n1\n"), "-o", tmp_path / "nope" / "out.csv")
    assert result.exit_code == 1 and "Output directory does not exist" in result.stderr


def test_report_path_equal_to_input_is_refused(runner, write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    result = invoke(runner, source, "-o", tmp_path / "out.csv", "--report", source)
    assert result.exit_code == 1 and "report path must differ" in result.stderr
    assert source.read_text(encoding="utf-8") == "a\n1\n"


def test_conflicting_duplicate_options(runner, write_text, tmp_path):
    result = invoke(
        runner, write_text("in.csv", "a\n1\n"), "-o", tmp_path / "out.csv",
        "--keep-duplicates", "--deduplicate-by", "a",
    )
    assert result.exit_code == 1 and "cannot be combined" in result.stderr


def test_unknown_deduplicate_column_lists_available_columns(runner, write_text, tmp_path):
    result = invoke(
        runner, write_text("in.csv", "name,email\nA,b\n"), "-o", tmp_path / "out.csv",
        "--deduplicate-by", "phone",
    )
    assert result.exit_code == 1
    assert "phone" in result.stderr and "name, email" in result.stderr
