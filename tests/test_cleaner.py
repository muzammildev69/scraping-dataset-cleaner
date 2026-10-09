import os
from pathlib import Path

import pandas as pd
import pytest

from dataset_cleaner import cleaner
from dataset_cleaner.cleaner import (
    clean_dataframe,
    clean_file,
    normalize_column_name,
    normalize_column_names,
    read_csv,
)
from dataset_cleaner.models import CleaningOptions, InputError, OptionError, OutputError

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def run(header, rows, **options):
    """Clean in-memory rows (lists of strings) with the given options."""
    data = pd.DataFrame(rows, dtype=str)
    return clean_dataframe(header, data, CleaningOptions(**options))


def values(frame):
    return frame.to_numpy().tolist()


# --- column names -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (" First Name ", "first_name"),
        ("Email Address", "email_address"),
        ("Product-URL", "product_url"),
        ("PRICE ($)", "price"),
        ("Price (USD)", "price_usd"),
        ("__Already__Snake__", "already_snake"),
        ("Ünïcode Näme", "ünïcode_näme"),
        ("   ", ""),
    ],
)
def test_normalize_column_name(raw, expected):
    assert normalize_column_name(raw) == expected


def test_duplicate_normalized_names_get_numeric_suffixes():
    assert normalize_column_names(["Email", "EMAIL", " email "]) == ["email", "email_2", "email_3"]


def test_suffixing_never_collides_with_existing_names():
    assert normalize_column_names(["a", "a_2", "a"]) == ["a", "a_2", "a_3"]


def test_unnameable_columns_fall_back_to_position():
    assert normalize_column_names(["$$", "", "x"]) == ["column_1", "column_2", "x"]


def test_colliding_columns_keep_all_data_and_warn():
    frame, report = run(["Email", "email"], [["a@x.com", "b@x.com"]])
    assert list(frame.columns) == ["email", "email_2"]
    assert values(frame) == [["a@x.com", "b@x.com"]]
    assert any("'email'" in warning and "email_2" in warning for warning in report.warnings)


def test_column_renames_only_list_changed_names():
    _, report = run(["id", "First Name"], [["1", "Ann"]])
    assert [(r.original, r.cleaned) for r in report.column_renames] == [("First Name", "first_name")]


# --- whitespace, empty rows, missing values ----------------------------------


def test_trim_whitespace_keeps_inner_spacing_and_number_text():
    frame, report = run(
        ["name", "price", "code"],
        [["  John   Smith  ", " 12.50 ", "007"], ["Ann", "1.10", "0"]],
    )
    assert values(frame) == [["John   Smith", "12.50", "007"], ["Ann", "1.10", "0"]]
    assert report.cells_trimmed == 2


def test_remove_only_completely_empty_rows():
    frame, report = run(
        ["a", "b"],
        [["x", "y"], ["", ""], ["  ", "\t"], ["z", ""], ["", "w"]],
    )
    assert values(frame) == [["x", "y"], ["z", ""], ["", "w"]]
    assert report.empty_rows_removed == 2
    assert report.original_rows == 5 and report.final_rows == 3


def test_missing_values_are_counted_not_replaced():
    frame, report = run(["a", "b"], [["x", ""], ["  ", "NaN"], ["None", "q"]])
    assert values(frame) == [["x", ""], ["", "NaN"], ["None", "q"]]
    assert report.missing_values == 2
    assert report.missing_values_by_column == {"a": 1, "b": 1}


# --- duplicates -------------------------------------------------------------


def test_exact_duplicates_keep_first_occurrence():
    frame, report = run(
        ["name", "email"],
        [["John", "john@example.com"], ["Ann", "ann@example.com"], ["John", "john@example.com"]],
    )
    assert values(frame) == [["John", "john@example.com"], ["Ann", "ann@example.com"]]
    assert report.duplicate_rows_removed == 1


def test_duplicates_are_found_after_normalisation():
    frame, report = run(
        ["name", "email"], [["John", "john@example.com"], [" John ", " JOHN@Example.com"]]
    )
    assert len(frame) == 1 and report.duplicate_rows_removed == 1


def test_keep_duplicates_option_disables_removal():
    frame, report = run(["a"], [["x"], ["x"]], deduplicate=False)
    assert len(frame) == 2 and report.duplicate_rows_removed == 0


def test_deduplicate_by_selected_column_spelled_loosely():
    frame, report = run(
        ["Name", "Email", "Phone"],
        [["A", "a@x.com", "1"], ["B", "a@x.com", "2"], ["C", "c@x.com", "3"]],
        deduplicate_by=("Email",),
    )
    assert values(frame) == [["A", "a@x.com", "1"], ["C", "c@x.com", "3"]]
    assert report.duplicate_rows_removed == 1


def test_deduplicate_by_multiple_columns():
    frame, report = run(
        ["name", "city", "note"],
        [["A", "X", "1"], ["A", "Y", "2"], ["A", "X", "3"]],
        deduplicate_by=("name", "city"),
    )
    assert values(frame) == [["A", "X", "1"], ["A", "Y", "2"]]
    assert report.duplicate_rows_removed == 1


def test_deduplicate_by_never_merges_rows_with_an_empty_key():
    frame, report = run(
        ["name", "email"],
        [["A", ""], ["B", ""], ["C", "x@y.co"], ["D", "x@y.co"]],
        deduplicate_by=("email",),
    )
    assert [row[0] for row in values(frame)] == ["A", "B", "C"]
    assert report.duplicate_rows_removed == 1


def test_deduplicate_by_unknown_column_is_an_error():
    with pytest.raises(OptionError, match="nope"):
        run(["a"], [["x"]], deduplicate_by=("nope",))


def test_deduplicate_by_conflicts_with_keep_duplicates():
    with pytest.raises(OptionError, match="keep-duplicates"):
        run(["a"], [["x"]], deduplicate=False, deduplicate_by=("a",))


# --- emails and URLs --------------------------------------------------------


def test_email_normalisation_in_detected_columns_only():
    frame, report = run(
        ["Email Address", "Note"], [["  John@Example.COM ", "KEEP Case"]]
    )
    assert values(frame) == [["john@example.com", "KEEP Case"]]
    assert report.email_columns == ["email_address"]
    assert report.emails_normalized == 1


def test_explicit_email_columns_override_detection():
    frame, report = run(
        ["contact", "email"],
        [["Bob@X.COM", "Eve@X.COM"]],
        email_columns=("Contact",),
    )
    assert values(frame) == [["bob@x.com", "Eve@X.COM"]]
    assert report.email_columns == ["contact"]


def test_explicit_columns_must_exist():
    with pytest.raises(OptionError, match="--url-columns"):
        run(["a"], [["x"]], url_columns=("missing",))


def test_url_normalisation_preserves_path_query_and_fragment():
    url = "  HTTPS://Example.COM/Path/A?Q=Mixed&b=2#Frag "
    frame, report = run(["Product URL"], [[url]])
    assert values(frame) == [["https://example.com/Path/A?Q=Mixed&b=2#Frag"]]
    assert report.urls_normalized == 1 and report.invalid_urls == 0


def test_url_params_are_stripped_only_on_request():
    rows = [["https://example.com/p?id=1#x"]]
    kept, _ = run(["url"], rows)
    stripped, _ = run(["url"], rows, strip_url_params=True)
    assert values(kept) == rows
    assert values(stripped) == [["https://example.com/p"]]


def test_missing_scheme_is_flagged_by_default_and_fixed_on_request():
    flagged, flagged_report = run(["website"], [["Example.com/a"]])
    fixed, fixed_report = run(["website"], [["Example.com/a"]], add_missing_scheme=True)
    assert values(flagged) == [["Example.com/a"]] and flagged_report.invalid_urls == 1
    assert values(fixed) == [["https://example.com/a"]] and fixed_report.invalid_urls == 0


ROWS_WITH_PROBLEMS = [
    ["ok@example.com", "https://example.com"],
    ["broken@example", "https://example.com/b"],
    ["fine@example.com", "not a url"],
    ["", "https://example.com/c"],
    ["bad@", "also bad"],
]


def test_invalid_values_are_counted_but_rows_survive_by_default():
    frame, report = run(["email", "url"], [list(r) for r in ROWS_WITH_PROBLEMS])
    assert len(frame) == 5
    assert report.invalid_emails == 2 and report.invalid_urls == 2
    assert report.invalid_rows_removed == 0 and report.invalid_details == []


def test_validate_lists_invalid_cells_by_data_row():
    _, report = run(["email", "url"], [list(r) for r in ROWS_WITH_PROBLEMS], validate=True)
    found = [(d.row, d.column, d.kind, d.value) for d in report.invalid_details]
    assert found == [
        (2, "email", "email", "broken@example"),
        (3, "url", "url", "not a url"),
        (5, "email", "email", "bad@"),
        (5, "url", "url", "also bad"),
    ]
    assert report.invalid_details_truncated is False


def test_validate_details_are_capped(monkeypatch):
    monkeypatch.setattr(cleaner, "MAX_INVALID_DETAILS", 2)
    _, report = run(["email"], [["a"], ["b"], ["c"]], validate=True)
    assert report.invalid_emails == 3
    assert len(report.invalid_details) == 2 and report.invalid_details_truncated is True


def test_remove_invalid_emails_keeps_rows_with_missing_email():
    frame, report = run(
        ["email", "url"], [list(r) for r in ROWS_WITH_PROBLEMS], remove_invalid_emails=True
    )
    assert [row[0] for row in values(frame)] == ["ok@example.com", "fine@example.com", ""]
    assert report.invalid_rows_removed == 2
    assert report.invalid_emails == 2 and report.invalid_urls == 2


def test_remove_invalid_urls_does_not_touch_email_problems():
    frame, report = run(
        ["email", "url"], [list(r) for r in ROWS_WITH_PROBLEMS], remove_invalid_urls=True
    )
    assert [row[0] for row in values(frame)] == ["ok@example.com", "broken@example", ""]
    assert report.invalid_rows_removed == 2


def test_both_remove_options_count_each_row_once():
    frame, report = run(
        ["email", "url"],
        [list(r) for r in ROWS_WITH_PROBLEMS],
        remove_invalid_emails=True,
        remove_invalid_urls=True,
    )
    assert [row[0] for row in values(frame)] == ["ok@example.com", ""]
    assert report.invalid_rows_removed == 3


# --- dropping columns -------------------------------------------------------


def test_drop_columns_by_loose_names_and_report_unknown_ones():
    frame, report = run(
        ["id", "Notes", "Temp Field"],
        [["1", "n", "t"]],
        drop_columns=("notes", "Temp Field", "ghost"),
    )
    assert list(frame.columns) == ["id"]
    assert report.columns_removed == ["notes", "temp_field"]
    assert report.columns_not_found == ["ghost"]
    assert report.original_columns == 3 and report.final_columns == 1
    assert any("ghost" in warning for warning in report.warnings)


def test_dropping_every_column_is_refused():
    with pytest.raises(OptionError, match="every column"):
        run(["a", "b"], [["1", "2"]], drop_columns=("a", "b"))


def test_duplicates_are_judged_after_dropping_columns():
    frame, report = run(
        ["name", "scraped_at"],
        [["A", "monday"], ["A", "tuesday"]],
        drop_columns=("scraped_at",),
    )
    assert values(frame) == [["A"]] and report.duplicate_rows_removed == 1


def test_validation_ignores_dropped_columns():
    _, report = run(["email", "keep"], [["bad", "x"]], drop_columns=("email",))
    assert report.invalid_emails == 0 and report.email_columns == []


# --- reading and writing ----------------------------------------------------


def test_read_csv_preserves_text_exactly(write_text):
    path = write_text("in.csv", "id,code,flag\n007,NaN,None\n1.50,,N/A\n")
    header, data = read_csv(path)
    assert header == ["id", "code", "flag"]
    assert values(data) == [["007", "NaN", "None"], ["1.50", "", "N/A"]]


def test_read_csv_handles_utf8_bom(write_text):
    path = write_text("bom.csv", b"\xef\xbb\xbfname,email\nJos\xc3\xa9,a@b.co\n")
    header, data = read_csv(path)
    assert header == ["name", "email"]
    assert values(data) == [["José", "a@b.co"]]


def test_read_csv_pads_short_rows(write_text):
    path = write_text("short.csv", "a,b,c\n1,2\n")
    _, data = read_csv(path)
    assert values(data) == [["1", "2", ""]]


def test_read_csv_keeps_quoted_commas_and_newlines(write_text):
    path = write_text("q.csv", 'name,bio\n"Doe, Jane","line1\nline2"\n')
    _, data = read_csv(path)
    assert values(data) == [["Doe, Jane", "line1\nline2"]]


@pytest.mark.parametrize("content", ["", "\n\n", "   \n  \n"])
def test_read_csv_rejects_empty_files(write_text, content):
    with pytest.raises(InputError, match="empty|no data"):
        read_csv(write_text("empty.csv", content))


def test_read_csv_rejects_rows_longer_than_the_header(write_text):
    with pytest.raises(InputError, match="Malformed CSV"):
        read_csv(write_text("bad.csv", "a,b\n1,2,3\n"))


def test_read_csv_rejects_unterminated_quotes(write_text):
    with pytest.raises(InputError, match="Malformed CSV"):
        read_csv(write_text("bad.csv", 'a,b\n"never closed,2\n3,4\n'))


def test_read_csv_reports_invalid_utf8(write_text):
    path = write_text("latin1.csv", "name\ncaf\u00e9\n".encode("latin-1"))
    with pytest.raises(InputError, match="UTF-8"):
        read_csv(path)


def test_header_only_file_produces_header_only_output(write_text, tmp_path):
    source = write_text("header.csv", "Name,Email\n")
    output = tmp_path / "out.csv"
    report = clean_file(source, output)
    assert output.read_text(encoding="utf-8") == "name,email\n"
    assert report.original_rows == 0 and report.final_rows == 0 and report.final_columns == 2


def test_clean_file_writes_utf8_without_bom_and_lf_endings(write_text, tmp_path):
    source = write_text("in.csv", b"\xef\xbb\xbfName,City\r\nJos\xc3\xa9,Z\xc3\xbcrich\r\n")
    output = tmp_path / "out.csv"
    clean_file(source, output)
    assert output.read_bytes() == "name,city\nJosé,Zürich\n".encode("utf-8")


def test_clean_file_matches_the_bundled_example(tmp_path):
    output = tmp_path / "cleaned.csv"
    report = clean_file(
        EXAMPLES_DIR / "messy_dataset.csv", output, CleaningOptions(drop_columns=("notes",))
    )
    assert output.read_text(encoding="utf-8") == (EXAMPLES_DIR / "expected_cleaned.csv").read_text(
        encoding="utf-8"
    )
    assert (report.original_rows, report.final_rows) == (7, 4)
    assert (report.original_columns, report.final_columns) == (5, 4)
    assert report.empty_rows_removed == 2 and report.duplicate_rows_removed == 1
    assert report.invalid_emails == 1 and report.invalid_urls == 1
    assert report.columns_removed == ["notes"]
    assert report.output_file == str(output)


def test_clean_file_replaces_an_existing_output(write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    output = tmp_path / "out.csv"
    output.write_text("old contents", encoding="utf-8")
    clean_file(source, output)
    assert output.read_text(encoding="utf-8") == "a\n1\n"


def test_large_input_adds_a_memory_warning(write_text, tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner, "LARGE_FILE_WARNING_BYTES", 5)
    report = clean_file(write_text("in.csv", "a,b\n1,2\n"), tmp_path / "out.csv")
    assert report.warnings and "memory" in report.warnings[0]


# --- path safety ------------------------------------------------------------


def test_missing_input_file(tmp_path):
    with pytest.raises(InputError, match="not found"):
        clean_file(tmp_path / "nope.csv", tmp_path / "out.csv")


def test_input_must_be_a_file(tmp_path):
    folder = tmp_path / "folder.csv"
    folder.mkdir()
    with pytest.raises(InputError, match="not a file"):
        clean_file(folder, tmp_path / "out.csv")


@pytest.mark.parametrize("name", ["data.txt", "data.xlsx", "data"])
def test_unsupported_input_extension(write_text, tmp_path, name):
    with pytest.raises(InputError, match="Unsupported input file type"):
        clean_file(write_text(name, "a\n1\n"), tmp_path / "out.csv")


def test_unsupported_output_extension(write_text, tmp_path):
    with pytest.raises(OutputError, match="must end in .csv"):
        clean_file(write_text("in.csv", "a\n1\n"), tmp_path / "out.txt")


def test_same_input_and_output_is_refused_and_input_untouched(write_text):
    source = write_text("in.csv", " A \n 1 \n")
    with pytest.raises(OutputError, match="overwrite the input"):
        clean_file(source, source)
    assert source.read_text(encoding="utf-8") == " A \n 1 \n"


def test_same_file_through_a_different_spelling_is_refused(write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    (tmp_path / "sub").mkdir()
    sneaky = tmp_path / "sub" / ".." / "in.csv"
    with pytest.raises(OutputError, match="overwrite the input"):
        clean_file(source, sneaky)
    assert source.read_text(encoding="utf-8") == "a\n1\n"


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links unavailable")
def test_hard_link_to_the_input_is_refused(write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    link = tmp_path / "link.csv"
    os.link(source, link)
    with pytest.raises(OutputError, match="overwrite the input"):
        clean_file(source, link)


def test_missing_output_directory(write_text, tmp_path):
    with pytest.raises(OutputError, match="directory does not exist"):
        clean_file(write_text("in.csv", "a\n1\n"), tmp_path / "missing" / "out.csv")


def test_output_path_that_is_a_directory(write_text, tmp_path):
    folder = tmp_path / "out.csv"
    folder.mkdir()
    with pytest.raises(OutputError, match="is a directory"):
        clean_file(write_text("in.csv", "a\n1\n"), folder)


def test_report_path_may_not_be_the_input_or_output(write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    output = tmp_path / "out.csv"
    with pytest.raises(OutputError, match="report path must differ"):
        clean_file(source, output, report_path=source)
    with pytest.raises(OutputError, match="report path must differ"):
        clean_file(source, output, report_path=output)
    assert not output.exists()


def test_failed_validation_writes_nothing(write_text, tmp_path):
    source = write_text("in.csv", "a\n1\n")
    output = tmp_path / "out.csv"
    with pytest.raises(OptionError):
        clean_file(source, output, CleaningOptions(deduplicate_by=("nope",)))
    assert not output.exists()
    assert not list(tmp_path.glob(".*.tmp"))
