from xengineer_pr_review.context import build_llm_context
from xengineer_pr_review.models import ChangedFile, PullRequestData, PullRequestRef


def test_context_records_omitted_files_when_limit_is_reached() -> None:
    pr = PullRequestData(
        ref=PullRequestRef("owner", "repo", 1),
        title="Improve auth",
        author="alice",
        base_branch="main",
        head_branch="feature",
        files=(
            ChangedFile("src/auth.py", additions=2, deletions=1, hunks=("+new",)),
            ChangedFile("src/extra.py", additions=2, deletions=1, hunks=("+extra",)),
        ),
        diff_text="",
    )

    context = build_llm_context(pr, findings=[], max_files=1, max_hunk_chars=100)

    assert "Improve auth" in context.prompt
    assert "src/auth.py" in context.prompt
    assert context.omitted_files == ["src/extra.py"]
