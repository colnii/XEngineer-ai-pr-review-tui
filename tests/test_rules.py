from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.rules import analyze_rules


def test_flags_sensitive_source_change_without_tests() -> None:
    diff_text = """diff --git a/src/auth/config.py b/src/auth/config.py
--- a/src/auth/config.py
+++ b/src/auth/config.py
@@ -10,2 +12,7 @@
 old = True
-TOKEN = "old"
+TOKEN = "x"
+AUTH_MODE = "strict"
+AUDIT = True
+RATE_LIMIT = 10
+SESSION_TTL = 60
+COOKIE_SECURE = True
"""
    files = parse_unified_diff(diff_text)

    findings = analyze_rules(files)

    titles = {finding.title for finding in findings}
    assert "Sensitive path changed" in titles
    assert "Source changed without tests" in titles
    sensitive = next(finding for finding in findings if finding.title == "Sensitive path changed")
    evidence = getattr(sensitive, "evidence", [])
    assert evidence[0].kind == "code"
    assert evidence[0].path == "src/auth/config.py"
    assert evidence[0].line_start == 12
    assert evidence[0].line_end == 18
