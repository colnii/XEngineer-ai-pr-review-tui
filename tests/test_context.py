from xengineer_pr_review.context import build_llm_context
from xengineer_pr_review.models import ChangedFile, PullRequestData, PullRequestRef


def test_context_includes_all_meaningful_files_without_file_count_limit() -> None:
    pr = PullRequestData(
        ref=PullRequestRef("owner", "repo", 1),
        title="Improve auth",
        author="alice",
        base_branch="main",
        head_branch="feature",
        files=tuple(
            ChangedFile(f"src/module_{index}.py", additions=2, deletions=1, hunks=("+new",))
            for index in range(10)
        ),
        diff_text="",
    )

    context = build_llm_context(pr, findings=[], max_hunk_chars=100)

    assert "Improve auth" in context.prompt
    assert "src/module_0.py" in context.prompt
    assert "src/module_9.py" in context.prompt
    assert "Changed file index:" in context.prompt
    assert "F1: src/module_0.py" in context.prompt
    assert context.file_ids["F1"] == "src/module_0.py"
    assert context.file_ids["F10"] == "src/module_9.py"
    assert context.omitted_files == []


def test_context_omits_low_signal_files() -> None:
    pr = PullRequestData(
        ref=PullRequestRef("owner", "repo", 1),
        title="Update frontend",
        author="alice",
        base_branch="main",
        head_branch="feature",
        files=(
            ChangedFile("src/app.py", additions=2, deletions=1, hunks=("+new",)),
            ChangedFile("package-lock.json", additions=200, deletions=120, hunks=("+lock",)),
            ChangedFile("dist/app.min.js", additions=1, deletions=1, hunks=("+bundle",)),
            ChangedFile("assets/logo.png", additions=0, deletions=0, hunks=()),
        ),
        diff_text="",
    )

    context = build_llm_context(pr, findings=[], max_hunk_chars=100)

    assert "src/app.py" in context.prompt
    assert "package-lock.json" not in context.prompt
    assert "dist/app.min.js" not in context.prompt
    assert "assets/logo.png" not in context.prompt
    assert context.omitted_files == [
        "package-lock.json",
        "dist/app.min.js",
        "assets/logo.png",
    ]
