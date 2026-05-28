from xengineer_pr_review.export import render_markdown
from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion


def test_render_markdown_contains_report_sections() -> None:
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
        findings=[
            ReviewFinding(
                severity="high",
                title="Sensitive path changed",
                explanation="Auth path changed.",
                files=["src/auth.py"],
            )
        ],
        suggestions=[
            ReviewSuggestion(
                severity="medium",
                title="Check tests",
                body="Add coverage for auth behavior.",
                files=["src/auth.py"],
            )
        ],
        changed_files=["src/auth.py"],
        omitted_files=[],
        warnings=[],
    )

    markdown = render_markdown(report)

    assert "# AI PR Review Report" in markdown
    assert "## Summary" in markdown
    assert "Sensitive path changed" in markdown
    assert "Check tests" in markdown
