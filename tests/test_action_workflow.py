from pathlib import Path

import pytest

from xengineer_pr_review.action_workflow import (
    DEFAULT_ACTION_USES,
    WORKFLOW_RELATIVE_PATH,
    init_action_workflow,
    render_action_workflow,
)


def test_render_action_workflow_uses_opened_pr_events_without_synchronize() -> None:
    workflow = render_action_workflow(
        action_uses="owner/xengineer@v1",
        comment_mode="review",
        review_action="approve",
        language="en",
    )

    assert "types: [opened, reopened, ready_for_review]" in workflow
    assert "synchronize" not in workflow
    assert "Use /xengineer review to rerun after new commits" in workflow
    assert "uses: owner/xengineer@v1" in workflow
    assert "github-token: ${{ github.token }}" in workflow
    assert "comment-mode: review" in workflow
    assert "review-action: approve" in workflow
    assert "language: en" in workflow
    assert "issues: read" in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" in workflow


def test_render_action_workflow_supports_manual_pr_comment_command() -> None:
    workflow = render_action_workflow(action_uses="owner/xengineer@v1", language="en")

    assert "issue_comment:" in workflow
    assert "types: [created]" in workflow
    assert "github.event_name == 'issue_comment'" in workflow
    assert "github.event.issue.pull_request" in workflow
    assert "github.event.comment.author_association == 'OWNER'" in workflow
    assert "github.event.comment.author_association == 'MEMBER'" in workflow
    assert "github.event.comment.author_association == 'COLLABORATOR'" in workflow
    assert "contains(github.event.comment.body, '/xengineer review')" in workflow
    assert "format('https://github.com/{0}/pull/{1}', github.repository, github.event.issue.number)" in workflow
    assert "issues: write" in workflow
    assert "pull-requests: write" in workflow


def test_default_action_reference_uses_stable_major_version() -> None:
    assert DEFAULT_ACTION_USES == "colnii/XEngineer-ai-pr-review-tui@v1"


def test_init_action_workflow_writes_workflow_under_repo_path(tmp_path: Path) -> None:
    written_path = init_action_workflow(
        repo_path=tmp_path,
        action_uses="owner/xengineer@v1",
        comment_mode="review",
        review_action="request-changes",
        language="zh",
    )

    assert written_path == tmp_path / WORKFLOW_RELATIVE_PATH
    assert written_path.exists()
    workflow = written_path.read_text(encoding="utf-8")
    assert "uses: owner/xengineer@v1" in workflow
    assert "comment-mode: review" in workflow
    assert "review-action: request-changes" in workflow
    assert "language: zh" in workflow


def test_init_action_workflow_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    workflow_path = tmp_path / WORKFLOW_RELATIVE_PATH
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("existing workflow\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        init_action_workflow(repo_path=tmp_path)

    assert workflow_path.read_text(encoding="utf-8") == "existing workflow\n"


def test_init_action_workflow_can_overwrite_existing_file(tmp_path: Path) -> None:
    workflow_path = tmp_path / WORKFLOW_RELATIVE_PATH
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("existing workflow\n", encoding="utf-8")

    written_path = init_action_workflow(repo_path=tmp_path, overwrite=True)

    assert written_path == workflow_path
    assert DEFAULT_ACTION_USES in workflow_path.read_text(encoding="utf-8")


def test_repository_installs_pr_review_workflow() -> None:
    workflow_path = WORKFLOW_RELATIVE_PATH

    workflow = workflow_path.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "issue_comment:" in workflow
    assert f"uses: {DEFAULT_ACTION_USES}" in workflow
    assert "github-token: ${{ github.token }}" in workflow
    assert "deepseek-api-key: ${{ secrets.DEEPSEEK_API_KEY }}" in workflow
    assert "openai-api-key: ${{ secrets.OPENAI_API_KEY }}" in workflow
    assert "tavily-api-key: ${{ secrets.TAVILY_API_KEY }}" in workflow
    assert "review-action: comment" in workflow
    assert "language: zh" in workflow
    assert "comment-mode: conversation" in workflow
    assert "issues: write" in workflow
    assert "pull-requests: write" in workflow
    assert "Use /xengineer review to rerun after new commits" in workflow
