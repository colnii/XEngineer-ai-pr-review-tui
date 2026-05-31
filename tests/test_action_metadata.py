from pathlib import Path


def test_action_metadata_runs_xpr_review_publish_comment() -> None:
    metadata = Path("action.yml").read_text(encoding="utf-8")

    assert "using: composite" in metadata
    assert "branding:" in metadata
    assert "icon: git-pull-request" in metadata
    assert "actions/setup-python@v5" in metadata
    assert 'python -m pip install "${{ github.action_path }}"' in metadata
    assert "--publish-comment" in metadata
    assert "--comment-mode" in metadata
    assert "inputs.comment-mode" in metadata
    assert "--auto-publish" in metadata
    assert "--confirm-publish" not in metadata
    assert "github.event.pull_request.html_url" in metadata
    assert "inputs.github-token || github.token" in metadata
    assert "GITHUB_TOKEN: ${{ inputs.github-token || github.token }}" in metadata
    assert "XENGINEER_GITHUB_TOKEN" not in metadata
    assert "GITHUB_TOKEN" in metadata
    assert "GitHub token is required" in metadata
    assert "python" in metadata
    assert "-m" in metadata
    assert "xengineer_pr_review" in metadata
    assert "xpr-review" not in metadata
