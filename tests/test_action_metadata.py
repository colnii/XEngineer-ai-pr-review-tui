from pathlib import Path


def test_action_metadata_runs_xpr_review_publish_comment() -> None:
    metadata = Path("action.yml").read_text(encoding="utf-8")

    assert "using: composite" in metadata
    assert "actions/setup-python@v5" in metadata
    assert 'python -m pip install "${{ github.action_path }}"' in metadata
    assert "--publish-comment" in metadata
    assert "--confirm-publish" in metadata
    assert "github.event.pull_request.html_url" in metadata
    assert "XENGINEER_GITHUB_TOKEN" in metadata
    assert "GITHUB_TOKEN" in metadata
