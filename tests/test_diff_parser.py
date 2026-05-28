from pathlib import Path

from xengineer_pr_review.diff_parser import parse_unified_diff


def test_parse_changed_files_from_unified_diff() -> None:
    diff_text = Path("tests/fixtures/sample.diff").read_text()
    files = parse_unified_diff(diff_text)

    assert [file.path for file in files] == ["src/app.py", "README.md"]
    assert files[0].additions == 3
    assert files[0].deletions == 1
    assert "token = " in files[0].hunks[0]
