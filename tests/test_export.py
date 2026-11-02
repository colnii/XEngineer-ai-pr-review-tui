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
                evidence=[
                    {
                        "kind": "code",
                        "path": "src/auth.py",
                        "line_start": 12,
                        "line_end": 16,
                    },
                    {
                        "kind": "web",
                        "label": "W1",
                        "title": "OAuth advisory",
                        "url": "https://example.test/oauth-advisory",
                        "snippet": "Rotate tokens after exposure.",
                    },
                    {
                        "kind": "pr_activity",
                        "label": "A1",
                        "title": "conversation by reviewer at 2026-05-30T10:00:00Z",
                        "url": "https://github.com/owner/repo/pull/1#issuecomment-10",
                        "snippet": "Please rerun after the latest push.",
                    },
                ],
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

    assert "# AI PR 审查报告" in markdown
    assert "## 摘要" in markdown
    assert "敏感路径变更" in markdown
    assert "认证路径发生变更" in markdown
    assert "证据" in markdown
    assert "`src/auth.py:12-16`" in markdown
    assert "[W1] [OAuth advisory](https://example.test/oauth-advisory)" in markdown
    assert (
        "[A1] [conversation by reviewer at 2026-05-30T10:00:00Z]"
        "(https://github.com/owner/repo/pull/1#issuecomment-10)"
        in markdown
    )
    assert "Please rerun after the latest push." in markdown
    assert "Add coverage for auth behavior." in markdown


def test_render_markdown_links_code_evidence_when_permalink_is_available() -> None:
    report = ReviewReport(
        pr_title="Improve auth",
        pr_url="https://github.com/owner/repo/pull/1",
        summary="Summary text",
        findings=[
            ReviewFinding(
                severity="medium",
                source="ai",
                title="Auth behavior changed",
                explanation="Token handling changed.",
                files=["src/auth.py"],
                evidence=[
                    {
                        "kind": "code",
                        "path": "src/auth.py",
                        "line_start": 12,
                        "line_end": 16,
                        "url": "https://github.com/owner/repo/blob/sha/src/auth.py#L12-L16",
                    }
                ],
            )
        ],
    )

    markdown = render_markdown(report, language="en")

    assert (
        "[`src/auth.py:12-16`](https://github.com/owner/repo/blob/sha/src/auth.py#L12-L16)"
        in markdown
    )


def test_render_markdown_can_render_english_report() -> None:
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
        suggestions=[],
        changed_files=["src/auth.py"],
        omitted_files=[],
        warnings=[],
    )

    markdown = render_markdown(report, language="en")

    assert "# AI PR Review Report" in markdown
    assert "## Summary" in markdown
    assert "**Severity:** high" in markdown


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

    markdown = render_markdown(report, language="en")

    assert "## Risk Assessment" in markdown
    assert "### AI-Identified Risks" in markdown
    assert "### Rule-Based Signals" in markdown
    assert "## Review Suggestions" in markdown
    assert "Exercise a wrapper that provides attributes through __getattr__." in markdown
    assert "No AI suggestions were generated" not in markdown
    assert "```markdown" not in markdown
    assert "### Summary" not in markdown
