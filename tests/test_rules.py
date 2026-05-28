from xengineer_pr_review.models import ChangedFile
from xengineer_pr_review.rules import analyze_rules


def test_flags_sensitive_source_change_without_tests() -> None:
    files = (
        ChangedFile(path="src/auth/config.py", additions=20, deletions=2, hunks=("TOKEN = 'x'",)),
    )

    findings = analyze_rules(files)

    titles = {finding.title for finding in findings}
    assert "Sensitive path changed" in titles
    assert "Source changed without tests" in titles
