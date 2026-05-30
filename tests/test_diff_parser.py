from pathlib import Path

from xengineer_pr_review.diff_parser import parse_unified_diff


def test_parse_changed_files_from_unified_diff() -> None:
    diff_text = Path("tests/fixtures/sample.diff").read_text()
    files = parse_unified_diff(diff_text)

    assert [file.path for file in files] == ["src/app.py", "README.md"]
    assert files[0].additions == 3
    assert files[0].deletions == 1
    assert "token = " in files[0].hunks[0]


def test_parse_changed_files_tracks_new_file_line_ranges() -> None:
    diff_text = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -10,2 +20,3 @@
 context = True
-old = True
+new = True
+extra = True
@@ -30 +41 @@
-before = True
+after = True
"""

    files = parse_unified_diff(diff_text)

    assert getattr(files[0], "line_ranges", None) == ((20, 22), (41, 41))
