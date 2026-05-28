from __future__ import annotations

from xengineer_pr_review.models import ChangedFile, ReviewFinding


SENSITIVE_MARKERS = ("auth", "config", "secret", "token", "password", "ci", ".github", "migration")
SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")
TEST_MARKERS = ("test", "tests", "spec")


def analyze_rules(files: tuple[ChangedFile, ...]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    paths = [file.path for file in files]

    for file in files:
        lowered = file.path.lower()
        changed_lines = file.additions + file.deletions
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            findings.append(
                ReviewFinding(
                    severity="high",
                    title="Sensitive path changed",
                    explanation=(
                        "This PR touches configuration, auth, secret, CI, or migration related paths."
                    ),
                    files=[file.path],
                )
            )
        if changed_lines >= 200:
            findings.append(
                ReviewFinding(
                    severity="medium",
                    title="Large file change",
                    explanation=f"{file.path} changes {changed_lines} lines and deserves focused review.",
                    files=[file.path],
                )
            )
        if file.deletions > file.additions * 2 and file.deletions >= 20:
            findings.append(
                ReviewFinding(
                    severity="medium",
                    title="Deletion-heavy change",
                    explanation=(
                        "This file removes much more code than it adds; check behavior compatibility."
                    ),
                    files=[file.path],
                )
            )

    source_changed = any(path.endswith(SOURCE_SUFFIXES) for path in paths)
    tests_changed = any(marker in path.lower() for marker in TEST_MARKERS for path in paths)
    if source_changed and not tests_changed:
        findings.append(
            ReviewFinding(
                severity="medium",
                title="Source changed without tests",
                explanation="Source files changed, but no test file change was detected in this PR.",
                files=[path for path in paths if path.endswith(SOURCE_SUFFIXES)],
            )
        )

    return findings
