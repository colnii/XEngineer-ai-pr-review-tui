from xengineer_pr_review.export import render_markdown
from xengineer_pr_review.models import ReviewFinding, ReviewReport, ReviewSuggestion


def test_render_markdown_contains_report_sections() -> None:
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        repo="owner/repo",
        pr_number=1,
        author="alice",
        additions=3,
        deletions=1,
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
    assert "Add coverage for auth behavior." in markdown


def test_render_markdown_uses_formal_report_structure_without_nested_llm_markdown() -> None:
    report = ReviewReport(
        pr_title="Fix stream detection",
        pr_url="https://github.com/psf/requests/pull/7433",
        repo="psf/requests",
        pr_number=7433,
        author="contributor",
        additions=12,
        deletions=4,
        summary="This PR fixes stream detection for dynamic file wrappers.",
        findings=[
            ReviewFinding(
                severity="low",
                source="ai",
                title="Wrapper edge cases",
                explanation="Unusual wrappers may still need manual review.",
                files=["src/requests/models.py"],
            ),
            ReviewFinding(
                severity="medium",
                source="rule",
                title="Source changed with tests",
                explanation="Core request model behavior changed.",
                files=["src/requests/models.py"],
            ),
        ],
        suggestions=[
            ReviewSuggestion(
                severity="medium",
                suggestion_type="test",
                title="Add wrapper regression coverage",
                body="Exercise a wrapper that provides attributes through __getattr__.",
                files=["tests/test_requests.py"],
                confidence="high",
            )
        ],
        changed_files=["src/requests/models.py", "tests/test_requests.py"],
        omitted_files=[],
        warnings=[],
        llm_status="ok",
    )

    markdown = render_markdown(report)

    assert "## Risk Assessment" in markdown
    assert "### AI-Identified Risks" in markdown
    assert "### Rule-Based Signals" in markdown
    assert "## Review Suggestions" in markdown
    assert "Exercise a wrapper that provides attributes through __getattr__." in markdown
    assert "No AI suggestions were generated" not in markdown
    assert "```markdown" not in markdown
    assert "### Summary" not in markdown
